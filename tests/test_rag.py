"""
Tests for RAG query engine.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from rag.engine import query, query_stream, retrieve_context


class TestQueryEngine:
    """Test RAG query functionality."""

    @patch('rag.engine.get_collection')
    def test_query_empty_collection(self, mock_get_collection):
        """Test query returns helpful message when collection is empty."""
        # Mock empty collection
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_get_collection.return_value = mock_collection

        result = query("What is Python?")

        # Should return helpful message
        assert "knowledge base is empty" in result['answer'].lower() or "no documents" in result['answer'].lower()
        assert len(result['sources']) == 0

    @patch('rag.engine.get_collection')
    @patch('rag.engine.embed_texts')
    def test_retrieve_context(self, mock_embed, mock_get_collection):
        """Test context retrieval from ChromaDB."""
        # Mock collection
        mock_collection = MagicMock()
        mock_collection.count.return_value = 100
        mock_collection.query.return_value = {
            'documents': [["Test document content"]],
            'metadatas': [[{'source_url': 'https://example.com/test', 'title': 'Test', 'source_name': 'Test Source'}]],
            'distances': [[0.5]]
        }
        mock_get_collection.return_value = mock_collection
        mock_embed.return_value = [[0.1, 0.2, 0.3]]

        result = retrieve_context("What is Python?")

        # Check structure
        assert 'documents' in result
        assert 'metadatas' in result
        assert len(result['documents'][0]) >= 1

    @patch('rag.engine.get_collection')
    @patch('rag.engine.embed_texts')
    @patch('rag.engine.generate_answer_ollama_stream')
    def test_query_stream(self, mock_stream, mock_embed, mock_get_collection):
        """Test streaming query functionality."""
        # Mock collection
        mock_collection = MagicMock()
        mock_collection.count.return_value = 100
        mock_collection.query.return_value = {
            'documents': [["Test content"]],
            'metadatas': [[{'source_url': 'https://example.com/test', 'title': 'Test', 'source_name': 'Test Source'}]]
        }
        mock_get_collection.return_value = mock_collection
        mock_embed.return_value = [[0.1, 0.2, 0.3]]

        # Mock streaming response
        def mock_generator():
            yield "Test "
            yield "answer"
        mock_stream.return_value = mock_generator()

        answer_stream, sources = query_stream("What is Python?")

        # Collect stream
        answer = "".join(list(answer_stream))

        # Check results
        assert "Test answer" in answer
        assert len(sources) >= 1
        assert sources[0]['url'] == 'https://example.com/test'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
