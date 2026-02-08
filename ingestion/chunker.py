"""
Text chunker for RAG ingestion.
Splits scraped documents into overlapping chunks suitable for embedding.
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def split_text_into_chunks(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 400
) -> List[str]:
    """
    Split text into overlapping chunks with smart boundary detection.

    Prioritizes splitting on:
    1. Paragraph boundaries (\\n\\n)
    2. Sentence boundaries (. )
    3. Hard character split as last resort

    Args:
        text: The text to split
        chunk_size: Target chunk size in characters (default: 2000 ~= 500 tokens)
        overlap: Overlap size in characters (default: 400 ~= 100 tokens)

    Returns:
        List of text chunks
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        # Determine end position for this chunk
        end = start + chunk_size

        if end >= len(text):
            # Last chunk - take everything remaining
            chunks.append(text[start:].strip())
            break

        # Try to find a good breaking point
        chunk_end = end

        # Look for paragraph break in the last 20% of the chunk
        search_start = max(start + int(chunk_size * 0.8), start)
        paragraph_break = text.rfind('\n\n', search_start, end + 100)

        if paragraph_break != -1 and paragraph_break > start:
            chunk_end = paragraph_break
        else:
            # Look for sentence break (. followed by space or newline)
            sentence_break = -1
            for i in range(end, search_start - 1, -1):
                if i < len(text) and text[i] == '.' and (
                    i + 1 >= len(text) or
                    text[i + 1] in ' \n\t'
                ):
                    sentence_break = i + 1
                    break

            if sentence_break != -1:
                chunk_end = sentence_break
            else:
                # Look for any whitespace
                space_break = text.rfind(' ', search_start, end + 50)
                if space_break != -1 and space_break > start:
                    chunk_end = space_break
                else:
                    # Hard split at chunk_size
                    chunk_end = end

        # Extract chunk and add to list
        chunk = text[start:chunk_end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start position with overlap
        # Make sure we don't go backwards
        next_start = chunk_end - overlap
        if next_start <= start:
            next_start = chunk_end
        start = next_start

    return chunks


def chunk_documents(
    documents: List[Dict],
    chunk_size: int = 2000,
    overlap: int = 400
) -> List[Dict]:
    """
    Chunk a list of scraped documents into smaller pieces with metadata.

    Args:
        documents: List of document dicts from scraper (with keys: url, title, text, source_name, source_key)
        chunk_size: Target chunk size in characters (default: 2000)
        overlap: Overlap size in characters (default: 400)

    Returns:
        List of dicts with keys:
        - text: The chunk text
        - metadata: Dict with source_url, source_name, source_key, title, chunk_index
    """
    all_chunks = []

    for doc in documents:
        text = doc.get('text', '')

        if not text:
            logger.warning(f"Skipping document with no text: {doc.get('url', 'unknown')}")
            continue

        # Split the document into chunks
        text_chunks = split_text_into_chunks(text, chunk_size, overlap)

        # Create chunk objects with metadata
        for idx, chunk_text in enumerate(text_chunks):
            chunk = {
                'text': chunk_text,
                'metadata': {
                    'source_url': doc.get('url', ''),
                    'source_name': doc.get('source_name', ''),
                    'source_key': doc.get('source_key', ''),
                    'title': doc.get('title', ''),
                    'chunk_index': idx,
                    'total_chunks': len(text_chunks)
                }
            }
            all_chunks.append(chunk)

        logger.info(
            f"Chunked '{doc.get('title', 'Unknown')}': "
            f"{len(text)} chars -> {len(text_chunks)} chunks"
        )

    logger.info(f"Total chunks created: {len(all_chunks)}")
    return all_chunks


if __name__ == "__main__":
    # Test the chunker
    import config
    from ingestion.scraper import scrape_all_sources

    logger.info("Testing chunker...")

    # Scrape documents
    logger.info("Scraping documents...")
    documents = scrape_all_sources(config.SOURCE_SITES)

    # Chunk documents
    logger.info("Chunking documents...")
    chunks = chunk_documents(documents)

    # Display statistics
    print(f"\n=== Chunking Results ===")
    print(f"Total documents: {len(documents)}")
    print(f"Total chunks: {len(chunks)}")
    print(f"Average chunks per document: {len(chunks) / len(documents):.1f}")

    # Show sample chunks
    print(f"\n=== Sample Chunks ===")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\nChunk {i + 1}:")
        print(f"  Source: {chunk['metadata']['source_name']}")
        print(f"  Title: {chunk['metadata']['title']}")
        print(f"  Chunk {chunk['metadata']['chunk_index'] + 1}/{chunk['metadata']['total_chunks']}")
        print(f"  Length: {len(chunk['text'])} chars")
        print(f"  Preview: {chunk['text'][:150]}...")

    # Verify chunk sizes
    chunk_sizes = [len(c['text']) for c in chunks]
    print(f"\n=== Chunk Size Statistics ===")
    print(f"  Min size: {min(chunk_sizes)} chars")
    print(f"  Max size: {max(chunk_sizes)} chars")
    print(f"  Average size: {sum(chunk_sizes) / len(chunk_sizes):.0f} chars")
