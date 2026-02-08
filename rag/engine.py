"""
RAG Query Engine.
Handles query embedding, retrieval from ChromaDB, and answer generation.
"""

import logging
import requests
from typing import Dict, List, Iterator
from openai import OpenAI
import config
from ingestion.embedder import get_collection, embed_texts

logger = logging.getLogger(__name__)

# Initialize OpenAI client if using OpenAI backend
openai_client = None
if config.LLM_BACKEND == "openai":
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

SYSTEM_PROMPT = """You are a helpful assistant. Answer the user's question based ONLY on the provided context.
If the context doesn't contain enough information, say so clearly.
Always cite which source(s) you used by mentioning the document title or source name."""


def generate_answer_ollama(prompt: str, context: str, timeout: int = 60) -> str:
    """
    Generate answer using Ollama.

    Args:
        prompt: User's question
        context: Retrieved context from ChromaDB
        timeout: Request timeout in seconds

    Returns:
        Generated answer text
    """
    full_prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context}\n\nQuestion: {prompt}\n\nAnswer:"

    try:
        response = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": config.OLLAMA_CHAT_MODEL,
                "prompt": full_prompt,
                "stream": False
            },
            timeout=timeout
        )
        response.raise_for_status()
        result = response.json()
        return result.get('response', '').strip()

    except requests.Timeout:
        logger.error(f"Ollama request timed out after {timeout}s")
        return "Error: Request timed out. Please try again."
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        return f"Error generating answer: {str(e)}"


def generate_answer_ollama_stream(prompt: str, context: str, timeout: int = 60) -> Iterator[str]:
    """
    Generate answer using Ollama with streaming.

    Args:
        prompt: User's question
        context: Retrieved context from ChromaDB
        timeout: Request timeout in seconds

    Yields:
        Chunks of generated text
    """
    full_prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context}\n\nQuestion: {prompt}\n\nAnswer:"

    try:
        response = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": config.OLLAMA_CHAT_MODEL,
                "prompt": full_prompt,
                "stream": True
            },
            timeout=timeout,
            stream=True
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                import json
                data = json.loads(line)
                if 'response' in data:
                    yield data['response']

    except requests.Timeout:
        logger.error(f"Ollama request timed out after {timeout}s")
        yield "Error: Request timed out. Please try again."
    except Exception as e:
        logger.error(f"Error calling Ollama stream: {e}")
        yield f"Error generating answer: {str(e)}"


def generate_answer_openai(prompt: str, context: str, timeout: int = 30) -> str:
    """
    Generate answer using OpenAI.

    Args:
        prompt: User's question
        context: Retrieved context from ChromaDB
        timeout: Request timeout in seconds

    Returns:
        Generated answer text
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {prompt}"}
            ],
            timeout=timeout
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Error calling OpenAI: {e}")
        return f"Error generating answer: {str(e)}"


def generate_answer_openai_stream(prompt: str, context: str, timeout: int = 30) -> Iterator[str]:
    """
    Generate answer using OpenAI with streaming.

    Args:
        prompt: User's question
        context: Retrieved context from ChromaDB
        timeout: Request timeout in seconds

    Yields:
        Chunks of generated text
    """
    try:
        stream = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {prompt}"}
            ],
            timeout=timeout,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        logger.error(f"Error calling OpenAI stream: {e}")
        yield f"Error generating answer: {str(e)}"


def retrieve_context(question: str, n_results: int = 5) -> Dict:
    """
    Retrieve relevant context from ChromaDB.

    Args:
        question: User's question
        n_results: Number of chunks to retrieve (default: 5)

    Returns:
        Dict with 'documents', 'metadatas', and 'ids' from ChromaDB
    """
    # Get collection
    collection = get_collection()

    # Check if collection is empty
    if collection.count() == 0:
        logger.warning("ChromaDB collection is empty")
        return None

    # Embed the question
    logger.info(f"Embedding question: {question[:50]}...")
    query_embedding = embed_texts([question])[0]

    # Query ChromaDB
    logger.info(f"Querying ChromaDB for {n_results} most relevant chunks...")
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=['documents', 'metadatas']
    )

    logger.info(f"Retrieved {len(results['documents'][0])} relevant chunks")
    return results


def query(user_question: str) -> Dict:
    """
    Process a user query and generate an answer with sources.

    Args:
        user_question: The user's question

    Returns:
        Dict with keys:
        - answer: Generated answer text
        - sources: List of dicts with 'url', 'title', 'source_name'
    """
    logger.info(f"Processing query: {user_question}")

    # Retrieve context
    results = retrieve_context(user_question)

    if results is None:
        return {
            "answer": "The knowledge base is empty. Please run ingestion first using the 'Re-ingest Sources' button.",
            "sources": []
        }

    # Extract documents and metadata
    documents = results['documents'][0]
    metadatas = results['metadatas'][0]

    if not documents:
        return {
            "answer": "I couldn't find any relevant information to answer your question.",
            "sources": []
        }

    # Build context string
    context_parts = []
    sources = []
    seen_urls = set()

    for doc, meta in zip(documents, metadatas):
        # Add document to context
        source_ref = f"[{meta['source_name']} - {meta['title']}]"
        context_parts.append(f"{source_ref}\n{doc}\n")

        # Track unique sources
        if meta['source_url'] not in seen_urls:
            seen_urls.add(meta['source_url'])
            sources.append({
                'url': meta['source_url'],
                'title': meta['title'],
                'source_name': meta['source_name']
            })

    context = "\n---\n".join(context_parts)

    # Generate answer
    logger.info("Generating answer...")
    if config.LLM_BACKEND == "ollama":
        answer = generate_answer_ollama(user_question, context)
    else:
        answer = generate_answer_openai(user_question, context)

    logger.info("Query complete")
    return {
        "answer": answer,
        "sources": sources
    }


def query_stream(user_question: str) -> tuple[Iterator[str], List[Dict]]:
    """
    Process a user query and generate a streaming answer with sources.

    Args:
        user_question: The user's question

    Returns:
        Tuple of (answer_stream, sources) where:
        - answer_stream: Iterator yielding answer text chunks
        - sources: List of dicts with 'url', 'title', 'source_name'
    """
    logger.info(f"Processing streaming query: {user_question}")

    # Retrieve context
    results = retrieve_context(user_question)

    if results is None:
        def empty_stream():
            yield "The knowledge base is empty. Please run ingestion first using the 'Re-ingest Sources' button."
        return empty_stream(), []

    # Extract documents and metadata
    documents = results['documents'][0]
    metadatas = results['metadatas'][0]

    if not documents:
        def no_results_stream():
            yield "I couldn't find any relevant information to answer your question."
        return no_results_stream(), []

    # Build context string
    context_parts = []
    sources = []
    seen_urls = set()

    for doc, meta in zip(documents, metadatas):
        # Add document to context
        source_ref = f"[{meta['source_name']} - {meta['title']}]"
        context_parts.append(f"{source_ref}\n{doc}\n")

        # Track unique sources
        if meta['source_url'] not in seen_urls:
            seen_urls.add(meta['source_url'])
            sources.append({
                'url': meta['source_url'],
                'title': meta['title'],
                'source_name': meta['source_name']
            })

    context = "\n---\n".join(context_parts)

    # Generate streaming answer
    logger.info("Generating streaming answer...")
    if config.LLM_BACKEND == "ollama":
        answer_stream = generate_answer_ollama_stream(user_question, context)
    else:
        answer_stream = generate_answer_openai_stream(user_question, context)

    return answer_stream, sources


if __name__ == "__main__":
    # Test the query engine
    import sys

    logger.info("Testing RAG query engine...")

    # Test questions
    test_questions = [
        "What is Python?",
        "How does machine learning work?",
        "What are JavaScript arrow functions?",
    ]

    for i, question in enumerate(test_questions, 1):
        print(f"\n{'='*60}")
        print(f"Question {i}: {question}")
        print('='*60)

        result = query(question)

        print(f"\nAnswer:\n{result['answer']}")

        print(f"\nSources ({len(result['sources'])}):")
        for source in result['sources']:
            print(f"  - {source['title']}")
            print(f"    {source['url']}")

        if i < len(test_questions):
            print("\n" + "-"*60)

    # Test streaming
    print(f"\n\n{'='*60}")
    print("Testing streaming query...")
    print('='*60)
    print(f"\nQuestion: {test_questions[0]}")
    print("\nStreaming answer:")

    answer_stream, sources = query_stream(test_questions[0])
    for chunk in answer_stream:
        print(chunk, end='', flush=True)

    print(f"\n\nSources: {len(sources)}")
