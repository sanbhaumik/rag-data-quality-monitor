"""
Source Quality Checks using Bright Data SERP API and direct HTTP checks.
Implements 6 check types: link break, content change, paywall, availability, structure shift, staleness.
"""

import logging
import hashlib
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import config
from monitor.db import save_check_result, get_latest_snapshot
from monitor.differ import light_check

logger = logging.getLogger(__name__)

# NOTE: The Bright Data SERP API endpoint format below is illustrative.
# Verify the actual API contract at: https://docs.brightdata.com/scraping-automation/serp-api/introduction


@dataclass
class CheckResult:
    """Result of a source quality check."""
    source_key: str
    url: str
    check_type: str  # "link", "content", "paywall", "availability", "structure", "staleness"
    status: str  # "ok", "warning", "error"
    detail: str  # Human-readable explanation
    checked_at: datetime


def call_bright_data_serp(query: str, timeout: int = 30) -> Optional[Dict]:
    """
    Call Bright Data SERP API.

    NOTE: This is a simplified implementation. Verify actual API format at:
    https://docs.brightdata.com/scraping-automation/serp-api/introduction

    Args:
        query: Search query
        timeout: Request timeout

    Returns:
        SERP results dict or None on failure
    """
    try:
        # NOTE: Adjust endpoint and request format based on actual Bright Data API docs
        response = requests.post(
            "https://api.brightdata.com/serp/req",
            headers={
                "Authorization": f"Bearer {config.BRIGHT_DATA_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "query": query,
                "search_engine": "google",
                "country": "us"
            },
            timeout=timeout
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"SERP API returned status {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error calling Bright Data SERP API: {e}")
        return None


def fetch_page_with_session(url: str, timeout: int = 10) -> Optional[requests.Response]:
    """
    Fetch a page with proper headers.

    Args:
        url: The URL to fetch
        timeout: Request timeout

    Returns:
        Response object or None on failure
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
            allow_redirects=True
        )
        return response

    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return None


# === Check 1: Link Break Detection ===

def check_link_break(source_key: str, url: str, source_config: Dict) -> CheckResult:
    """
    Check if a link is broken (404, 410) or has excessive redirects.

    Args:
        source_key: Source identifier
        url: URL to check
        source_config: Source configuration dict

    Returns:
        CheckResult
    """
    checked_at = datetime.now(timezone.utc)

    try:
        # Use HEAD request first (faster)
        response = requests.head(
            url,
            timeout=10,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        status_code = response.status_code

        # Check for broken links
        if status_code in [404, 410]:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="link",
                status="error",
                detail=f"Link broken: HTTP {status_code}",
                checked_at=checked_at
            )

        # Check redirect count
        if len(response.history) > 2:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="link",
                status="warning",
                detail=f"Excessive redirects: {len(response.history)} hops",
                checked_at=checked_at
            )

        # Check if final URL differs significantly
        final_url = response.url
        if final_url != url and final_url.rstrip('/') != url.rstrip('/'):
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="link",
                status="warning",
                detail=f"URL moved to: {final_url}",
                checked_at=checked_at
            )

        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="link",
            status="ok",
            detail="Link is accessible",
            checked_at=checked_at
        )

    except requests.Timeout:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="link",
            status="error",
            detail="Request timed out",
            checked_at=checked_at
        )

    except Exception as e:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="link",
            status="error",
            detail=f"Check failed: {str(e)}",
            checked_at=checked_at
        )


# === Check 2: Content Change Detection ===

def check_content_change(source_key: str, url: str, source_config: Dict, deep_diff: bool = False) -> CheckResult:
    """
    Check if content has changed using hash comparison.

    Args:
        source_key: Source identifier
        url: URL to check
        source_config: Source configuration dict
        deep_diff: If True, store full text for deep diff

    Returns:
        CheckResult
    """
    checked_at = datetime.now(timezone.utc)

    try:
        # Fetch page content
        response = fetch_page_with_session(url)
        if not response or response.status_code != 200:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="content",
                status="error",
                detail=f"Failed to fetch content: {response.status_code if response else 'No response'}",
                checked_at=checked_at
            )

        # Parse and extract text
        soup = BeautifulSoup(response.content, 'html.parser')
        # Remove scripts, styles
        for element in soup.find_all(['script', 'style']):
            element.decompose()
        text = soup.get_text(separator='\n', strip=True)

        # Use the differ module to check for changes
        from monitor.differ import light_check as check_hash_change
        result = check_hash_change(url, text)

        if result['changed']:
            detail = f"Content changed (previous: {result['previous_hash'][:8]}..., current: {result['current_hash'][:8]}...)"
            status = "warning"
        else:
            detail = "Content unchanged"
            status = "ok"

        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="content",
            status=status,
            detail=detail,
            checked_at=checked_at
        )

    except Exception as e:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="content",
            status="error",
            detail=f"Check failed: {str(e)}",
            checked_at=checked_at
        )


# === Check 3: Paywall Detection ===

def check_paywall(source_key: str, url: str, source_config: Dict) -> CheckResult:
    """
    Check if content is behind a paywall.

    Args:
        source_key: Source identifier
        url: URL to check
        source_config: Source configuration dict

    Returns:
        CheckResult
    """
    checked_at = datetime.now(timezone.utc)

    try:
        response = fetch_page_with_session(url)
        if not response:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="paywall",
                status="error",
                detail="Failed to fetch page",
                checked_at=checked_at
            )

        # Check HTTP status codes
        if response.status_code in [401, 403]:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="paywall",
                status="error",
                detail=f"Access denied: HTTP {response.status_code}",
                checked_at=checked_at
            )

        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        html_lower = str(soup).lower()

        # Check for common paywall indicators
        paywall_indicators = [
            'paywall', 'subscribe', 'subscription', 'premium',
            'login-required', 'access-denied', 'members-only',
            'paid-content'
        ]

        found_indicators = [ind for ind in paywall_indicators if ind in html_lower]

        if found_indicators:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="paywall",
                status="warning",
                detail=f"Possible paywall detected: {', '.join(found_indicators[:3])}",
                checked_at=checked_at
            )

        # Check content length compared to last snapshot
        text = soup.get_text()
        current_length = len(text)

        snapshot = get_latest_snapshot(url)
        if snapshot and snapshot.get('content_text'):
            previous_length = len(snapshot['content_text'])
            if current_length < previous_length * 0.5:
                return CheckResult(
                    source_key=source_key,
                    url=url,
                    check_type="paywall",
                    status="warning",
                    detail=f"Content length reduced by {((previous_length - current_length) / previous_length * 100):.0f}%",
                    checked_at=checked_at
                )

        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="paywall",
            status="ok",
            detail="No paywall detected",
            checked_at=checked_at
        )

    except Exception as e:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="paywall",
            status="error",
            detail=f"Check failed: {str(e)}",
            checked_at=checked_at
        )


# === Check 4: Availability Check ===

def check_availability(source_key: str, url: str, source_config: Dict) -> CheckResult:
    """
    Check if a page is available (HTTP 200).

    Args:
        source_key: Source identifier
        url: URL to check
        source_config: Source configuration dict

    Returns:
        CheckResult
    """
    checked_at = datetime.now(timezone.utc)

    try:
        response = fetch_page_with_session(url, timeout=10)

        if not response:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="availability",
                status="error",
                detail="Page is offline or unreachable",
                checked_at=checked_at
            )

        if response.status_code >= 500:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="availability",
                status="error",
                detail=f"Server error: HTTP {response.status_code}",
                checked_at=checked_at
            )

        if response.status_code == 200:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="availability",
                status="ok",
                detail="Page is available",
                checked_at=checked_at
            )

        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="availability",
            status="warning",
            detail=f"Unexpected status: HTTP {response.status_code}",
            checked_at=checked_at
        )

    except requests.Timeout:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="availability",
            status="error",
            detail="Request timed out - page may be offline",
            checked_at=checked_at
        )

    except Exception as e:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="availability",
            status="error",
            detail=f"Check failed: {str(e)}",
            checked_at=checked_at
        )


# === Check 5: Structure Shift Detection ===

def check_structure_shift(source_key: str, url: str, source_config: Dict) -> CheckResult:
    """
    Check if page structure has changed (expected selectors missing).

    Args:
        source_key: Source identifier
        url: URL to check
        source_config: Source configuration dict

    Returns:
        CheckResult
    """
    checked_at = datetime.now(timezone.utc)

    try:
        response = fetch_page_with_session(url)
        if not response or response.status_code != 200:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="structure",
                status="error",
                detail="Failed to fetch page for structure check",
                checked_at=checked_at
            )

        soup = BeautifulSoup(response.content, 'html.parser')

        # Get expected selectors from config
        expected_selectors = source_config.get('expected_selectors', [])

        if not expected_selectors:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="structure",
                status="ok",
                detail="No expected selectors configured",
                checked_at=checked_at
            )

        # Check each expected selector
        found_selectors = []
        missing_selectors = []

        for selector in expected_selectors:
            if soup.select(selector):
                found_selectors.append(selector)
            else:
                missing_selectors.append(selector)

        if missing_selectors:
            # All selectors missing = major shift
            if len(missing_selectors) == len(expected_selectors):
                return CheckResult(
                    source_key=source_key,
                    url=url,
                    check_type="structure",
                    status="error",
                    detail=f"All expected selectors missing: {', '.join(missing_selectors)}",
                    checked_at=checked_at
                )
            # Some selectors missing = minor shift
            else:
                return CheckResult(
                    source_key=source_key,
                    url=url,
                    check_type="structure",
                    status="warning",
                    detail=f"Some selectors missing: {', '.join(missing_selectors)}",
                    checked_at=checked_at
                )

        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="structure",
            status="ok",
            detail=f"All {len(found_selectors)} expected selectors found",
            checked_at=checked_at
        )

    except Exception as e:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="structure",
            status="error",
            detail=f"Check failed: {str(e)}",
            checked_at=checked_at
        )


# === Check 6: Staleness Check ===

def check_staleness(source_key: str, url: str, source_config: Dict) -> CheckResult:
    """
    Check if content is stale (not updated in a long time).

    Args:
        source_key: Source identifier
        url: URL to check
        source_config: Source configuration dict

    Returns:
        CheckResult
    """
    checked_at = datetime.now(timezone.utc)

    try:
        response = fetch_page_with_session(url)
        if not response or response.status_code != 200:
            return CheckResult(
                source_key=source_key,
                url=url,
                check_type="staleness",
                status="error",
                detail="Failed to fetch page for staleness check",
                checked_at=checked_at
            )

        # Check Last-Modified header
        last_modified_str = response.headers.get('Last-Modified')
        if last_modified_str:
            from email.utils import parsedate_to_datetime
            last_modified = parsedate_to_datetime(last_modified_str)
            days_old = (checked_at - last_modified).days

            threshold = source_config.get('staleness_days', 365)

            if days_old > threshold:
                return CheckResult(
                    source_key=source_key,
                    url=url,
                    check_type="staleness",
                    status="warning",
                    detail=f"Content not updated in {days_old} days (threshold: {threshold})",
                    checked_at=checked_at
                )
            else:
                return CheckResult(
                    source_key=source_key,
                    url=url,
                    check_type="staleness",
                    status="ok",
                    detail=f"Content updated {days_old} days ago",
                    checked_at=checked_at
                )

        # Check for meta tags
        soup = BeautifulSoup(response.content, 'html.parser')
        meta_modified = soup.find('meta', attrs={'property': 'article:modified_time'})
        if not meta_modified:
            meta_modified = soup.find('meta', attrs={'name': 'last-modified'})

        if meta_modified and meta_modified.get('content'):
            # Try to parse the date
            from dateutil import parser
            try:
                last_modified = parser.parse(meta_modified['content'])
                days_old = (checked_at - last_modified).days

                threshold = source_config.get('staleness_days', 365)

                if days_old > threshold:
                    return CheckResult(
                        source_key=source_key,
                        url=url,
                        check_type="staleness",
                        status="warning",
                        detail=f"Content not updated in {days_old} days (threshold: {threshold})",
                        checked_at=checked_at
                    )
            except:
                pass

        # No reliable date info
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="staleness",
            status="ok",
            detail="No staleness indicators found (unable to determine age)",
            checked_at=checked_at
        )

    except Exception as e:
        return CheckResult(
            source_key=source_key,
            url=url,
            check_type="staleness",
            status="error",
            detail=f"Check failed: {str(e)}",
            checked_at=checked_at
        )


# === Orchestration Functions ===

def check_single_source(
    source_key: str,
    source_config: Dict,
    deep_diff: bool = False
) -> List[CheckResult]:
    """
    Run all checks for a single source.

    Args:
        source_key: Source identifier
        source_config: Source configuration dict
        deep_diff: Enable deep diff for content checks

    Returns:
        List of CheckResults
    """
    results = []
    base_url = source_config['base_url']
    pages = source_config['pages']

    logger.info(f"Running checks for {source_key} ({len(pages)} pages)...")

    for page_path in pages:
        url = base_url + page_path

        # Run each check type
        try:
            results.append(check_link_break(source_key, url, source_config))
        except Exception as e:
            logger.error(f"Link break check failed for {url}: {e}")

        try:
            results.append(check_content_change(source_key, url, source_config, deep_diff))
        except Exception as e:
            logger.error(f"Content change check failed for {url}: {e}")

        try:
            results.append(check_paywall(source_key, url, source_config))
        except Exception as e:
            logger.error(f"Paywall check failed for {url}: {e}")

        try:
            results.append(check_availability(source_key, url, source_config))
        except Exception as e:
            logger.error(f"Availability check failed for {url}: {e}")

        try:
            results.append(check_structure_shift(source_key, url, source_config))
        except Exception as e:
            logger.error(f"Structure shift check failed for {url}: {e}")

        try:
            results.append(check_staleness(source_key, url, source_config))
        except Exception as e:
            logger.error(f"Staleness check failed for {url}: {e}")

    logger.info(f"Completed checks for {source_key}: {len(results)} results")
    return results


def run_all_checks(source_sites: Dict, deep_diff: bool = False) -> List[CheckResult]:
    """
    Run all checks for all configured sources.

    Args:
        source_sites: Dict of source configurations
        deep_diff: Enable deep diff for content checks

    Returns:
        List of all CheckResults
    """
    all_results = []

    logger.info(f"Starting checks for {len(source_sites)} sources...")

    for source_key, source_config in source_sites.items():
        try:
            results = check_single_source(source_key, source_config, deep_diff)
            all_results.extend(results)

            # Save results to database
            for result in results:
                save_check_result(
                    source_key=result.source_key,
                    url=result.url,
                    check_type=result.check_type,
                    status=result.status,
                    detail=result.detail
                )

        except Exception as e:
            logger.error(f"Failed to check source {source_key}: {e}")

    logger.info(f"All checks complete: {len(all_results)} total results")
    return all_results


if __name__ == "__main__":
    # Test the checks
    import config

    logger.info("Testing source quality checks...")

    # Test on first page of each source
    test_sources = {}
    for key, cfg in config.SOURCE_SITES.items():
        test_sources[key] = {
            **cfg,
            'pages': [cfg['pages'][0]]  # Only first page
        }

    print(f"\nRunning checks on {len(test_sources)} sources (1 page each)...\n")

    results = run_all_checks(test_sources, deep_diff=False)

    # Display results by check type
    from collections import defaultdict
    by_type = defaultdict(list)
    for r in results:
        by_type[r.check_type].append(r)

    for check_type, type_results in sorted(by_type.items()):
        print(f"\n{check_type.upper()} Checks:")
        for r in type_results:
            symbol = "✓" if r.status == "ok" else "⚠" if r.status == "warning" else "✗"
            print(f"  {symbol} [{r.status:7}] {r.source_key:15} - {r.detail[:60]}")

    # Summary
    status_counts = defaultdict(int)
    for r in results:
        status_counts[r.status] += 1

    print(f"\n{'='*70}")
    print(f"Summary: {len(results)} checks")
    print(f"  OK: {status_counts['ok']}")
    print(f"  Warnings: {status_counts['warning']}")
    print(f"  Errors: {status_counts['error']}")
