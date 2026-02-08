"""
Embedding and ChromaDB storage for RAG ingestion.
Generates OpenAI embeddings and stores them in ChromaDB.
"""

import logging
import time
import hashlib
import requests
from typing import List, Dict
import chromadb
from openai import OpenAI, RateLimitError, APIError
import config
from ingestion.scraper import scrape_all_sources
from ingestion.chunker import chunk_documents

logger = logging.getLogger(__name__)

# Initialize OpenAI client (only if using OpenAI backend)
openai_client = None
if config.LLM_BACKEND == "openai":
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

# ChromaDB client and collection (initialized lazily)
_chroma_client = None
_collection = None

COLLECTION_NAME = "rag_sources"
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI model
BATCH_SIZE = 100  # Max texts per API call


def get_chroma_client():
    """Get or create ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=config.CHROMADB_PATH)
        logger.info(f"ChromaDB client initialized at {config.CHROMADB_PATH}")
    return _chroma_client


def get_collection():
    """Get or create ChromaDB collection."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "RAG source documents with embeddings"}
        )
        logger.info(f"ChromaDB collection '{COLLECTION_NAME}' ready")
    return _collection


def generate_chunk_id(source_url: str, chunk_index: int) -> str:
    """
    Generate deterministic ID for a chunk.
    Uses SHA-256 hash of source_url + chunk_index for idempotent re-ingestion.

    Args:
        source_url: The source URL
        chunk_index: The chunk index

    Returns:
        Deterministic hex string ID
    """
    content = f"{source_url}::{chunk_index}"
    return hashlib.sha256(content.encode()).hexdigest()


def embed_texts_ollama(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings using Ollama.

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors (list of floats)
    """
    if not texts:
        return []

    embeddings = []
    logger.info(f"Embedding {len(texts)} texts with Ollama ({config.OLLAMA_EMBEDDING_MODEL})...")

    for i, text in enumerate(texts):
        try:
            response = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/embeddings",
                json={
                    "model": config.OLLAMA_EMBEDDING_MODEL,
                    "prompt": text
                },
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            embeddings.append(result['embedding'])

            if (i + 1) % 50 == 0:
                logger.info(f"  Embedded {i + 1}/{len(texts)} texts")

        except Exception as e:
            logger.error(f"Error embedding text {i}: {e}")
            raise

    logger.info(f"Successfully generated {len(embeddings)} embeddings with Ollama")
    return embeddings


def embed_texts(texts: List[str], retry_attempts: int = 3) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.
    Routes to appropriate backend (OpenAI or Ollama) based on config.

    Args:
        texts: List of text strings to embed
        retry_attempts: Number of retry attempts on rate limit (OpenAI only, default: 3)

    Returns:
        List of embedding vectors (list of floats)

    Raises:
        APIError: If API call fails after retries
    """
    if not texts:
        return []

    # Route to appropriate backend
    if config.LLM_BACKEND == "ollama":
        return embed_texts_ollama(texts)

    # OpenAI backend
    for attempt in range(retry_attempts):
        try:
            logger.info(f"Embedding {len(texts)} texts with {EMBEDDING_MODEL}...")

            response = openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts
            )

            embeddings = [item.embedding for item in response.data]
            logger.info(f"Successfully generated {len(embeddings)} embeddings")
            return embeddings

        except RateLimitError as e:
            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
            logger.warning(f"Rate limit hit, waiting {wait_time}s before retry (attempt {attempt + 1}/{retry_attempts})")
            if attempt < retry_attempts - 1:
                time.sleep(wait_time)
            else:
                logger.error(f"Rate limit exceeded after {retry_attempts} attempts")
                raise

        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise


def store_embeddings(chunks: List[Dict]) -> int:
    """
    Store chunks with embeddings in ChromaDB.
    Processes in batches and generates embeddings on the fly.

    Args:
        chunks: List of chunk dicts with 'text' and 'metadata' keys

    Returns:
        Number of chunks stored
    """
    if not chunks:
        logger.warning("No chunks to store")
        return 0

    collection = get_collection()
    total_stored = 0

    # Process in batches
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)")

        # Extract texts and metadata
        texts = [chunk['text'] for chunk in batch]
        metadatas = [chunk['metadata'] for chunk in batch]

        # Generate embeddings for this batch
        embeddings = embed_texts(texts)

        # Generate deterministic IDs
        ids = [
            generate_chunk_id(
                meta['source_url'],
                meta['chunk_index']
            )
            for meta in metadatas
        ]

        # Store in ChromaDB
        # Need to convert all metadata values to strings or numbers for ChromaDB
        cleaned_metadatas = []
        for meta in metadatas:
            cleaned_meta = {
                'source_url': str(meta['source_url']),
                'source_name': str(meta['source_name']),
                'source_key': str(meta['source_key']),
                'title': str(meta['title']),
                'chunk_index': int(meta['chunk_index']),
                'total_chunks': int(meta['total_chunks'])
            }
            cleaned_metadatas.append(cleaned_meta)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=cleaned_metadatas
        )

        total_stored += len(batch)
        logger.info(f"Stored batch {batch_num}/{total_batches} - Total: {total_stored}/{len(chunks)}")

    logger.info(f"Successfully stored {total_stored} chunks in ChromaDB")
    return total_stored


def is_collection_empty() -> bool:
    """
    Check if the ChromaDB collection is empty.

    Returns:
        True if collection has no documents, False otherwise
    """
    try:
        collection = get_collection()
        count = collection.count()
        return count == 0
    except Exception as e:
        logger.error(f"Error checking collection: {e}")
        return True


def run_ingestion(source_sites: dict = None) -> int:
    """
    Run the full ingestion pipeline: scrape -> chunk -> embed -> store.

    Args:
        source_sites: Dict of source configurations (uses config.SOURCE_SITES if None)

    Returns:
        Number of chunks stored
    """
    if source_sites is None:
        source_sites = config.SOURCE_SITES

    logger.info("=" * 60)
    logger.info("Starting full ingestion pipeline")
    logger.info("=" * 60)

    # Step 1: Scrape
    logger.info("Step 1: Scraping source websites...")
    documents = scrape_all_sources(source_sites)
    if not documents:
        logger.error("No documents scraped, aborting ingestion")
        return 0

    # Step 2: Chunk
    logger.info("Step 2: Chunking documents...")
    chunks = chunk_documents(documents)
    if not chunks:
        logger.error("No chunks created, aborting ingestion")
        return 0

    # Step 3: Embed and Store
    logger.info("Step 3: Generating embeddings and storing in ChromaDB...")
    count = store_embeddings(chunks)

    logger.info("=" * 60)
    logger.info(f"Ingestion complete: {count} chunks stored")
    logger.info("=" * 60)

    return count


if __name__ == "__main__":
    # Test the embedder
    logger.info("Testing embedder and full ingestion pipeline...")

    # Check if collection is empty
    if is_collection_empty():
        logger.info("Collection is empty, running full ingestion...")
        count = run_ingestion()
        print(f"\n✓ Ingestion complete: {count} chunks stored in ChromaDB")
    else:
        collection = get_collection()
        count = collection.count()
        print(f"\n✓ Collection already has {count} documents")
        print("To re-ingest, delete the data/chromadb directory first")

    # Show collection stats
    collection = get_collection()
    print(f"\nCollection stats:")
    print(f"  Name: {collection.name}")
    print(f"  Total documents: {collection.count()}")

    # Show sample documents
    if collection.count() > 0:
        results = collection.get(limit=3, include=['documents', 'metadatas'])
        print(f"\nSample documents:")
        for i, (doc, meta) in enumerate(zip(results['documents'], results['metadatas'])):
            print(f"\n  {i + 1}. {meta['title']}")
            print(f"     Source: {meta['source_name']}")
            print(f"     Chunk: {meta['chunk_index'] + 1}/{meta['total_chunks']}")
            print(f"     Preview: {doc[:100]}...")
