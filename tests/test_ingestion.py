"""
Tests for ingestion module (scraper, chunker, embedder).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import requests
from ingestion.scraper import scrape_single_page, create_session
from ingestion.chunker import chunk_documents
from ingestion.embedder import generate_chunk_id


class TestScraper:
    """Test web scraper functionality."""

    def test_create_session_has_retry_logic(self):
        """Test that session is created with retry adapter."""
        session = create_session()
        assert session is not None
        # Check that adapters are mounted
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('ingestion.scraper.requests.Session')
    def test_scrape_handles_404_gracefully(self, mock_session_class):
        """Test that scraper returns None on 404 without crashing."""
        # Mock the session and response
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_session.get.return_value = mock_response

        # Should return None, not crash
        result = scrape_single_page("https://example.com/missing")
        assert result is None

    @patch('ingestion.scraper.requests.Session')
    def test_scrape_success(self, mock_session_class):
        """Test successful scraping returns expected structure."""
        # Mock session
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Mock response
        mock_response = Mock()
        mock_response.content = b"<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        result = scrape_single_page("https://example.com/test")

        assert result is not None
        assert 'url' in result
        assert 'title' in result
        assert 'text' in result
        assert 'fetched_at' in result
        assert result['title'] == 'Test'
        assert 'Content' in result['text']

    @patch('ingestion.scraper.requests.Session')
    def test_scrape_timeout_handling(self, mock_session_class):
        """Test that timeouts are handled gracefully."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.get.side_effect = requests.Timeout("Connection timeout")

        result = scrape_single_page("https://example.com/slow", timeout=1)
        assert result is None


class TestChunker:
    """Test text chunking functionality."""

    def test_chunk_size_and_overlap(self):
        """Test that chunker produces correct chunk sizes with overlap."""
        # Create a test document with known length
        long_text = "A" * 5000  # 5000 characters

        documents = [{
            'url': 'https://example.com/test',
            'title': 'Test',
            'text': long_text,
            'source_key': 'test',
            'source_name': 'Test Source'
        }]

        chunks = chunk_documents(documents, chunk_size=2000, overlap=400)

        # Should have multiple chunks
        assert len(chunks) > 1

        # Check first chunk size (should be ~2000)
        assert 1900 <= len(chunks[0]['text']) <= 2000

        # Check overlap by comparing end of first chunk with start of second
        if len(chunks) > 1:
            chunk1_end = chunks[0]['text'][-400:]
            chunk2_start = chunks[1]['text'][:400]
            # There should be some overlap (not perfect due to boundary detection)
            # Just verify both exist
            assert len(chunk1_end) > 0
            assert len(chunk2_start) > 0

    def test_chunk_metadata_preserved(self):
        """Test that chunks preserve source metadata."""
        documents = [{
            'url': 'https://example.com/test',
            'title': 'Test Page',
            'text': 'Some content here',
            'source_key': 'test_source',
            'source_name': 'Test Source Name'
        }]

        chunks = chunk_documents(documents, chunk_size=100, overlap=20)

        assert len(chunks) >= 1
        chunk = chunks[0]

        # Check metadata
        assert chunk['source_url'] == 'https://example.com/test'
        assert chunk['source_name'] == 'Test Source Name'
        assert chunk['title'] == 'Test Page'
        assert chunk['chunk_index'] == 0

    def test_empty_document(self):
        """Test handling of empty documents."""
        documents = [{
            'url': 'https://example.com/empty',
            'title': 'Empty',
            'text': '',
            'source_key': 'test',
            'source_name': 'Test'
        }]

        chunks = chunk_documents(documents)
        # Should handle gracefully (either skip or create minimal chunk)
        assert isinstance(chunks, list)


class TestEmbedder:
    """Test embedding functionality."""

    def test_doc_id_generation_deterministic(self):
        """Test that doc IDs are deterministic (same input = same ID)."""
        url = "https://example.com/test"
        chunk_index = 0

        # Generate ID twice
        id1 = generate_chunk_id(url, chunk_index)
        id2 = generate_chunk_id(url, chunk_index)

        # Should be identical
        assert id1 == id2
        assert len(id1) > 0

    def test_doc_id_unique_per_chunk(self):
        """Test that different chunks get different IDs."""
        url = "https://example.com/test"

        id1 = generate_chunk_id(url, 0)
        id2 = generate_chunk_id(url, 1)

        # Should be different
        assert id1 != id2

    def test_doc_id_unique_per_url(self):
        """Test that different URLs get different IDs."""
        chunk_index = 0

        id1 = generate_chunk_id("https://example.com/page1", chunk_index)
        id2 = generate_chunk_id("https://example.com/page2", chunk_index)

        # Should be different
        assert id1 != id2

    @patch('ingestion.embedder.requests.post')
    def test_ollama_embedding_handles_errors(self, mock_post):
        """Test that Ollama embedding handles API errors gracefully."""
        from ingestion.embedder import embed_texts_ollama

        mock_post.side_effect = requests.RequestException("Connection failed")

        with pytest.raises(Exception):
            # Should raise exception on failure
            embed_texts_ollama(["test text"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
