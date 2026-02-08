"""
Content Differ.
Light check: SHA-256 hash comparison.
Deep diff: Text comparison with change percentage and summary.
"""

import hashlib
import logging
import difflib
from typing import Dict, Optional
from monitor.db import get_latest_snapshot, save_content_snapshot

logger = logging.getLogger(__name__)


def compute_hash(text: str) -> str:
    """
    Compute SHA-256 hash of normalized text.

    Args:
        text: Text to hash

    Returns:
        Hexadecimal hash string
    """
    # Normalize: strip whitespace, lowercase
    normalized = ' '.join(text.lower().split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def light_check(url: str, current_text: str) -> Dict:
    """
    Compare hash to last snapshot (light check).

    Args:
        url: The URL
        current_text: Current page text

    Returns:
        Dict with keys:
        - changed: bool - Whether content changed
        - previous_hash: str or None
        - current_hash: str
    """
    current_hash = compute_hash(current_text)

    # Get last snapshot
    snapshot = get_latest_snapshot(url)

    if not snapshot:
        # First time seeing this URL - save snapshot
        save_content_snapshot(url, current_hash, current_text)
        logger.info(f"Created first snapshot for {url}")
        return {
            'changed': False,
            'previous_hash': None,
            'current_hash': current_hash
        }

    previous_hash = snapshot['content_hash']
    changed = (current_hash != previous_hash)

    if changed:
        # Save new snapshot
        save_content_snapshot(url, current_hash, current_text)
        logger.info(f"Content changed for {url}")

    return {
        'changed': changed,
        'previous_hash': previous_hash,
        'current_hash': current_hash
    }


def deep_diff(url: str, current_text: str) -> Dict:
    """
    Full text diff with change percentage and summary.

    Args:
        url: The URL
        current_text: Current page text

    Returns:
        Dict with keys:
        - changed: bool
        - pct_changed: float - Percentage changed (0-100)
        - diff_summary: str - First 500 chars of unified diff
        - added_lines: int - Number of lines added
        - removed_lines: int - Number of lines removed
        - previous_hash: str or None
        - current_hash: str
    """
    current_hash = compute_hash(current_text)

    # Get last snapshot
    snapshot = get_latest_snapshot(url)

    if not snapshot or not snapshot.get('content_text'):
        # First time or no stored text - save snapshot with full text
        save_content_snapshot(url, current_hash, current_text)
        logger.info(f"Created first deep snapshot for {url}")
        return {
            'changed': False,
            'pct_changed': 0.0,
            'diff_summary': 'First snapshot',
            'added_lines': 0,
            'removed_lines': 0,
            'previous_hash': None,
            'current_hash': current_hash
        }

    previous_text = snapshot['content_text']
    previous_hash = snapshot['content_hash']

    # Check if changed
    if current_hash == previous_hash:
        return {
            'changed': False,
            'pct_changed': 0.0,
            'diff_summary': 'No changes',
            'added_lines': 0,
            'removed_lines': 0,
            'previous_hash': previous_hash,
            'current_hash': current_hash
        }

    # Content changed - compute detailed diff
    previous_lines = previous_text.splitlines()
    current_lines = current_text.splitlines()

    # Use SequenceMatcher to compute similarity
    matcher = difflib.SequenceMatcher(None, previous_lines, current_lines)
    similarity = matcher.ratio()
    pct_changed = (1 - similarity) * 100

    # Generate unified diff
    diff = difflib.unified_diff(
        previous_lines,
        current_lines,
        lineterm='',
        n=1  # Context lines
    )
    diff_lines = list(diff)

    # Count added/removed lines
    added_lines = sum(1 for line in diff_lines if line.startswith('+') and not line.startswith('+++'))
    removed_lines = sum(1 for line in diff_lines if line.startswith('-') and not line.startswith('---'))

    # Create diff summary (first 500 chars)
    diff_text = '\n'.join(diff_lines)
    diff_summary = diff_text[:500]
    if len(diff_text) > 500:
        diff_summary += '...'

    # Save new snapshot with full text
    save_content_snapshot(url, current_hash, current_text)

    logger.info(f"Deep diff for {url}: {pct_changed:.1f}% changed ({added_lines} added, {removed_lines} removed)")

    return {
        'changed': True,
        'pct_changed': pct_changed,
        'diff_summary': diff_summary,
        'added_lines': added_lines,
        'removed_lines': removed_lines,
        'previous_hash': previous_hash,
        'current_hash': current_hash
    }


if __name__ == "__main__":
    # Test the differ
    logger.info("Testing content differ...")

    test_url = "https://example.com/test"

    # Test 1: First snapshot
    text1 = "Hello World\nThis is a test page.\nLine 3"
    result1 = light_check(test_url, text1)
    print(f"\nTest 1 - First snapshot:")
    print(f"  Changed: {result1['changed']}")
    print(f"  Hash: {result1['current_hash'][:16]}...")

    # Test 2: No change
    result2 = light_check(test_url, text1)
    print(f"\nTest 2 - No change:")
    print(f"  Changed: {result2['changed']}")

    # Test 3: Content changed
    text2 = "Hello World\nThis is an updated page.\nLine 3\nNew line 4"
    result3 = light_check(test_url, text2)
    print(f"\nTest 3 - Content changed:")
    print(f"  Changed: {result3['changed']}")
    print(f"  Previous: {result3['previous_hash'][:16]}...")
    print(f"  Current:  {result3['current_hash'][:16]}...")

    # Test 4: Deep diff
    result4 = deep_diff(test_url, text2)
    print(f"\nTest 4 - Deep diff:")
    print(f"  Changed: {result4['changed']}")
    print(f"  Percent changed: {result4['pct_changed']:.1f}%")
    print(f"  Added lines: {result4['added_lines']}")
    print(f"  Removed lines: {result4['removed_lines']}")
    print(f"  Diff summary:\n{result4['diff_summary']}")

    print("\n✓ All differ tests complete!")
