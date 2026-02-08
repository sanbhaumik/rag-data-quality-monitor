"""
Web scraper for RAG source sites.
Fetches and parses HTML content from configured source websites.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# User agent to avoid being blocked
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def create_session() -> requests.Session:
    """
    Create a requests session with retry logic.
    Retries 3 times with exponential backoff on connection errors and 5xx responses.
    """
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,  # Wait 1s, 2s, 4s between retries
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def scrape_single_page(url: str, timeout: int = 10) -> Optional[dict]:
    """
    Scrape a single web page and extract its content.

    Args:
        url: The URL to scrape
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Dictionary with keys: url, title, text, fetched_at
        Returns None if scraping fails
    """
    session = create_session()

    try:
        logger.info(f"Fetching: {url}")

        response = session.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract title
        title = soup.title.string if soup.title else url

        # Remove unwanted elements
        for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            element.decompose()

        # Extract main content based on common selectors
        content = None

        # Try site-specific selectors
        # Python docs
        content_div = soup.find('div', class_='body') or soup.find('div', role='main')
        if content_div:
            content = content_div

        # MDN
        if not content:
            content_div = soup.find('article') or soup.find('main')
            if content_div:
                content = content_div

        # Wikipedia
        if not content:
            content_div = soup.find('div', id='mw-content-text')
            if content_div:
                content = content_div

        # Fallback to body if no specific content area found
        if not content:
            content = soup.find('body')

        # Extract text
        if content:
            text = content.get_text(separator='\n', strip=True)
        else:
            text = soup.get_text(separator='\n', strip=True)

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        result = {
            'url': url,
            'title': title.strip() if title else '',
            'text': text,
            'fetched_at': datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Successfully scraped: {url} ({len(text)} chars)")
        return result

    except requests.Timeout:
        logger.warning(f"Timeout while fetching {url}")
        return None
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error scraping {url}: {e}")
        return None
    finally:
        session.close()


def scrape_all_sources(source_sites: dict) -> list[dict]:
    """
    Scrape all configured source sites.

    Args:
        source_sites: Dictionary of source site configurations from config.py

    Returns:
        List of dictionaries with scraped content
        Includes metadata: source_key, source_name for each page
    """
    all_documents = []

    for source_key, source_config in source_sites.items():
        base_url = source_config['base_url']
        source_name = source_config['name']
        pages = source_config['pages']

        logger.info(f"Scraping source: {source_name} ({len(pages)} pages)")

        for page_path in pages:
            # Construct full URL
            url = base_url + page_path

            # Scrape the page
            result = scrape_single_page(url)

            if result:
                # Add source metadata
                result['source_key'] = source_key
                result['source_name'] = source_name
                all_documents.append(result)

            # Be polite - small delay between requests to same domain
            time.sleep(0.5)

        logger.info(f"Completed scraping {source_name}: {len([d for d in all_documents if d.get('source_key') == source_key])} pages")

    logger.info(f"Total documents scraped: {len(all_documents)}")
    return all_documents


if __name__ == "__main__":
    # Test the scraper
    import config

    logger.info("Starting scraper test...")
    documents = scrape_all_sources(config.SOURCE_SITES)

    print(f"\nScraped {len(documents)} documents")
    for doc in documents[:3]:  # Show first 3
        print(f"\n- {doc['title']}")
        print(f"  Source: {doc['source_name']}")
        print(f"  URL: {doc['url']}")
        print(f"  Length: {len(doc['text'])} chars")
        print(f"  Preview: {doc['text'][:100]}...")
