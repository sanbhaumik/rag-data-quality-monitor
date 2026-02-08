"""
Monitor Database (SQLite).
Persists monitoring state: check history, content snapshots, and alerts.
"""

import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Dict
import config

logger = logging.getLogger(__name__)


# SQL Schema
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS check_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    url TEXT NOT NULL,
    check_type TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_text TEXT,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    url TEXT NOT NULL,
    check_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    email_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_check_history_source ON check_history(source_key, checked_at);
CREATE INDEX IF NOT EXISTS idx_check_history_url ON check_history(url, checked_at);
CREATE INDEX IF NOT EXISTS idx_content_snapshots_url ON content_snapshots(url, snapshot_at);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(resolved_at) WHERE resolved_at IS NULL;
"""


@contextmanager
def get_db():
    """
    Context manager for database connections.
    Automatically creates tables on first use.

    Usage:
        with get_db() as conn:
            conn.execute("INSERT INTO ...")
            conn.commit()
    """
    conn = sqlite3.connect(config.MONITOR_DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dicts

    try:
        # Create tables if they don't exist
        conn.executescript(CREATE_TABLES_SQL)
        conn.commit()
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database and create tables."""
    logger.info(f"Initializing monitor database at {config.MONITOR_DB_PATH}")
    with get_db() as conn:
        conn.executescript(CREATE_TABLES_SQL)
        conn.commit()
    logger.info("Monitor database initialized successfully")


# === Check History Functions ===

def save_check_result(
    source_key: str,
    url: str,
    check_type: str,
    status: str,
    detail: Optional[str] = None
) -> int:
    """
    Save a check result to history.

    Args:
        source_key: Source identifier (e.g., "python_docs")
        url: The URL that was checked
        check_type: Type of check ("link", "content", "paywall", "availability", "structure", "staleness")
        status: Check status ("ok", "warning", "error")
        detail: Human-readable description

    Returns:
        The ID of the inserted row
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO check_history (source_key, url, check_type, status, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_key, url, check_type, status, detail)
        )
        conn.commit()
        row_id = cursor.lastrowid

    logger.debug(f"Saved check result: {source_key}/{check_type} - {status}")
    return row_id


def get_check_history(
    source_key: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """
    Get check history, optionally filtered by source.

    Args:
        source_key: Optional source filter
        limit: Maximum number of results (default: 100)

    Returns:
        List of check history dicts
    """
    with get_db() as conn:
        if source_key:
            cursor = conn.execute(
                """
                SELECT * FROM check_history
                WHERE source_key = ?
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (source_key, limit)
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM check_history
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (limit,)
            )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_latest_check_by_source() -> Dict[str, Dict]:
    """
    Get the most recent check for each source.

    Returns:
        Dict mapping source_key to latest check dict
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT source_key, MAX(checked_at) as last_check, status
            FROM check_history
            GROUP BY source_key
            """
        )

        rows = cursor.fetchall()
        return {row['source_key']: dict(row) for row in rows}


# === Content Snapshot Functions ===

def save_content_snapshot(
    url: str,
    content_hash: str,
    content_text: Optional[str] = None
) -> int:
    """
    Save a content snapshot.

    Args:
        url: The URL
        content_hash: SHA-256 hash of the content
        content_text: Full text content (optional, for deep diff)

    Returns:
        The ID of the inserted row
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO content_snapshots (url, content_hash, content_text)
            VALUES (?, ?, ?)
            """,
            (url, content_hash, content_text)
        )
        conn.commit()
        row_id = cursor.lastrowid

    logger.debug(f"Saved content snapshot for {url}")
    return row_id


def get_latest_snapshot(url: str) -> Optional[Dict]:
    """
    Get the most recent content snapshot for a URL.

    Args:
        url: The URL to look up

    Returns:
        Snapshot dict or None if not found
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM content_snapshots
            WHERE url = ?
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            (url,)
        )

        row = cursor.fetchone()
        return dict(row) if row else None


def get_snapshot_history(url: str, limit: int = 10) -> List[Dict]:
    """
    Get snapshot history for a URL.

    Args:
        url: The URL
        limit: Maximum number of results (default: 10)

    Returns:
        List of snapshot dicts
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM content_snapshots
            WHERE url = ?
            ORDER BY snapshot_at DESC
            LIMIT ?
            """,
            (url, limit)
        )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# === Alert Functions ===

def save_alert(
    source_key: str,
    url: str,
    check_type: str,
    severity: str,
    message: str
) -> int:
    """
    Save an alert.

    Args:
        source_key: Source identifier
        url: The URL
        check_type: Type of check that triggered the alert
        severity: "warning" or "critical"
        message: Alert message

    Returns:
        The ID of the inserted alert
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO alerts (source_key, url, check_type, severity, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_key, url, check_type, severity, message)
        )
        conn.commit()
        alert_id = cursor.lastrowid

    logger.info(f"Created alert: {severity} - {message[:50]}...")
    return alert_id


def mark_alert_emailed(alert_id: int):
    """
    Mark an alert as emailed.

    Args:
        alert_id: The alert ID
    """
    with get_db() as conn:
        conn.execute(
            """
            UPDATE alerts
            SET email_sent = TRUE
            WHERE id = ?
            """,
            (alert_id,)
        )
        conn.commit()

    logger.debug(f"Marked alert {alert_id} as emailed")


def mark_alert_resolved(alert_id: int):
    """
    Mark an alert as resolved.

    Args:
        alert_id: The alert ID
    """
    with get_db() as conn:
        conn.execute(
            """
            UPDATE alerts
            SET resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (alert_id,)
        )
        conn.commit()

    logger.info(f"Resolved alert {alert_id}")


def get_active_alerts() -> List[Dict]:
    """
    Get all active (unresolved) alerts.

    Returns:
        List of alert dicts
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM alerts
            WHERE resolved_at IS NULL
            ORDER BY created_at DESC
            """
        )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_recent_alerts(limit: int = 50) -> List[Dict]:
    """
    Get recent alerts (both active and resolved).

    Args:
        limit: Maximum number of results (default: 50)

    Returns:
        List of alert dicts
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM alerts
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_alert_summary() -> Dict:
    """
    Get alert summary statistics for dashboard.

    Returns:
        Dict with alert counts by severity and status
    """
    with get_db() as conn:
        # Count by severity
        cursor = conn.execute(
            """
            SELECT severity, COUNT(*) as count
            FROM alerts
            WHERE resolved_at IS NULL
            GROUP BY severity
            """
        )
        severity_counts = {row['severity']: row['count'] for row in cursor.fetchall()}

        # Count total active
        cursor = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM alerts
            WHERE resolved_at IS NULL
            """
        )
        total_active = cursor.fetchone()['count']

        # Count total resolved (last 7 days)
        cursor = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM alerts
            WHERE resolved_at IS NOT NULL
            AND resolved_at > datetime('now', '-7 days')
            """
        )
        total_resolved_week = cursor.fetchone()['count']

        return {
            'total_active': total_active,
            'warning_count': severity_counts.get('warning', 0),
            'critical_count': severity_counts.get('critical', 0),
            'resolved_this_week': total_resolved_week
        }


def check_duplicate_alert(
    source_key: str,
    url: str,
    check_type: str,
    hours: int = 24
) -> bool:
    """
    Check if a similar alert already exists in the last N hours.

    Args:
        source_key: Source identifier
        url: The URL
        check_type: Type of check
        hours: Time window in hours (default: 24)

    Returns:
        True if duplicate exists, False otherwise
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM alerts
            WHERE source_key = ?
            AND url = ?
            AND check_type = ?
            AND created_at > datetime('now', ? || ' hours')
            AND resolved_at IS NULL
            """,
            (source_key, url, check_type, f'-{hours}')
        )

        count = cursor.fetchone()['count']
        return count > 0


if __name__ == "__main__":
    # Test the database
    logger.info("Testing monitor database...")

    # Initialize
    init_db()
    print("✓ Database initialized")

    # Test check history
    check_id = save_check_result(
        source_key="python_docs",
        url="https://docs.python.org/3/tutorial/index.html",
        check_type="availability",
        status="ok",
        detail="Page is accessible"
    )
    print(f"✓ Saved check result (ID: {check_id})")

    # Test content snapshot
    snapshot_id = save_content_snapshot(
        url="https://docs.python.org/3/tutorial/index.html",
        content_hash="abc123def456",
        content_text="Sample content for testing"
    )
    print(f"✓ Saved content snapshot (ID: {snapshot_id})")

    # Test alerts
    alert_id = save_alert(
        source_key="python_docs",
        url="https://docs.python.org/3/tutorial/index.html",
        check_type="content",
        severity="warning",
        message="Content has changed significantly"
    )
    print(f"✓ Saved alert (ID: {alert_id})")

    # Test retrieval
    history = get_check_history(limit=5)
    print(f"✓ Retrieved {len(history)} check history records")

    snapshot = get_latest_snapshot("https://docs.python.org/3/tutorial/index.html")
    print(f"✓ Retrieved latest snapshot: {snapshot['content_hash']}")

    alerts = get_active_alerts()
    print(f"✓ Retrieved {len(alerts)} active alerts")

    summary = get_alert_summary()
    print(f"✓ Alert summary: {summary}")

    # Test duplicate check
    is_dup = check_duplicate_alert(
        source_key="python_docs",
        url="https://docs.python.org/3/tutorial/index.html",
        check_type="content"
    )
    print(f"✓ Duplicate check: {is_dup}")

    # Mark alert as emailed
    mark_alert_emailed(alert_id)
    print(f"✓ Marked alert {alert_id} as emailed")

    print("\n✓ All database operations successful!")
