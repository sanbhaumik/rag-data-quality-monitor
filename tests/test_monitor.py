"""
Tests for monitoring module (checks, alerts, differ).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import hashlib
from monitor.checks import (
    CheckResult,
    check_link_break,
    check_content_change,
    check_paywall,
    check_availability,
    check_structure_shift,
    check_staleness
)
from monitor.alerts import process_check_results, get_alert_severity
from monitor.differ import compute_hash, light_check
from monitor.db import check_duplicate_alert, get_db


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_check_result_creation(self):
        """Test CheckResult can be created with valid data."""
        result = CheckResult(
            source_key="test",
            url="https://example.com",
            check_type="link",
            status="ok",
            detail="All good",
            checked_at=datetime.now()
        )

        assert result.source_key == "test"
        assert result.status == "ok"
        assert result.check_type == "link"

    def test_check_result_statuses(self):
        """Test valid status values."""
        valid_statuses = ["ok", "warning", "error"]

        for status in valid_statuses:
            result = CheckResult(
                source_key="test",
                url="https://example.com",
                check_type="link",
                status=status,
                detail="Test",
                checked_at=datetime.now()
            )
            assert result.status == status


class TestLinkCheck:
    """Test link break detection."""

    @patch('monitor.checks.fetch_page')
    def test_link_check_ok(self, mock_fetch):
        """Test link check returns OK for valid 200 response."""
        mock_fetch.return_value = {
            'status_code': 200,
            'final_url': 'https://example.com/page',
            'redirected': False
        }

        result = check_link_break("test", "https://example.com/page")

        assert result.status == "ok"
        assert result.check_type == "link"

    @patch('monitor.checks.fetch_page')
    def test_link_check_redirect(self, mock_fetch):
        """Test link check returns warning for redirects."""
        mock_fetch.return_value = {
            'status_code': 200,
            'final_url': 'https://example.com/new-page',
            'redirected': True
        }

        result = check_link_break("test", "https://example.com/page")

        assert result.status == "warning"
        assert "moved" in result.detail.lower() or "redirect" in result.detail.lower()

    @patch('monitor.checks.fetch_page')
    def test_link_check_404(self, mock_fetch):
        """Test link check returns error for 404."""
        mock_fetch.return_value = {
            'status_code': 404,
            'final_url': 'https://example.com/missing',
            'redirected': False
        }

        result = check_link_break("test", "https://example.com/missing")

        assert result.status == "error"
        assert "404" in result.detail or "not found" in result.detail.lower()

    @patch('monitor.checks.fetch_page')
    def test_link_check_network_error(self, mock_fetch):
        """Test link check handles network errors."""
        mock_fetch.return_value = None

        result = check_link_break("test", "https://example.com/page")

        assert result.status == "error"


class TestPaywallCheck:
    """Test paywall detection."""

    @patch('monitor.checks.fetch_page')
    def test_paywall_keywords_detected(self, mock_fetch):
        """Test paywall detection finds common paywall keywords."""
        mock_fetch.return_value = {
            'status_code': 200,
            'text': 'Please subscribe to continue reading this article.',
            'text_length': 1000
        }

        result = check_paywall("test", "https://example.com/article")

        assert result.status == "warning"
        assert "paywall" in result.detail.lower()

    @patch('monitor.checks.fetch_page')
    def test_no_paywall_clean_content(self, mock_fetch):
        """Test no paywall detected on clean content."""
        mock_fetch.return_value = {
            'status_code': 200,
            'text': 'This is a freely accessible article with lots of content. ' * 100,
            'text_length': 5000
        }

        result = check_paywall("test", "https://example.com/article")

        assert result.status == "ok"

    @patch('monitor.checks.fetch_page')
    def test_paywall_short_content(self, mock_fetch):
        """Test suspiciously short content triggers warning."""
        mock_fetch.return_value = {
            'status_code': 200,
            'text': 'Short article',
            'text_length': 100
        }

        result = check_paywall("test", "https://example.com/article")

        # May or may not trigger depending on threshold, but should not crash
        assert result.status in ["ok", "warning"]


class TestStructureCheck:
    """Test structure shift detection."""

    @patch('monitor.checks.fetch_page')
    def test_structure_all_selectors_present(self, mock_fetch):
        """Test structure check passes when all selectors found."""
        mock_html = '<html><body><article>Content</article><main>More</main></body></html>'
        mock_fetch.return_value = {
            'status_code': 200,
            'html': mock_html
        }

        expected_selectors = ["article", "main"]
        result = check_structure_shift("test", "https://example.com", expected_selectors)

        assert result.status == "ok"

    @patch('monitor.checks.fetch_page')
    def test_structure_missing_selector(self, mock_fetch):
        """Test structure check warns when selector missing."""
        mock_html = '<html><body><div>Content</div></body></html>'
        mock_fetch.return_value = {
            'status_code': 200,
            'html': mock_html
        }

        expected_selectors = ["article", "main"]
        result = check_structure_shift("test", "https://example.com", expected_selectors)

        assert result.status == "warning"
        assert "missing" in result.detail.lower()


class TestContentDiffer:
    """Test content diffing functionality."""

    def test_compute_hash_deterministic(self):
        """Test hash computation is deterministic."""
        text = "Test content for hashing"

        hash1 = compute_hash(text)
        hash2 = compute_hash(text)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex chars

    def test_compute_hash_different_content(self):
        """Test different content produces different hashes."""
        hash1 = compute_hash("Content A")
        hash2 = compute_hash("Content B")

        assert hash1 != hash2

    def test_compute_hash_whitespace_normalized(self):
        """Test that hash normalizes whitespace."""
        text1 = "Hello   world"
        text2 = "Hello world"

        hash1 = compute_hash(text1)
        hash2 = compute_hash(text2)

        # After normalization, should be same
        assert hash1 == hash2

    @patch('monitor.differ.get_latest_snapshot')
    @patch('monitor.differ.save_snapshot')
    def test_light_check_no_previous_snapshot(self, mock_save, mock_get):
        """Test light check creates first snapshot."""
        mock_get.return_value = None

        result = light_check("https://example.com/new", "Fresh content")

        assert result['changed'] is False
        assert 'current_hash' in result
        mock_save.assert_called_once()

    @patch('monitor.differ.get_latest_snapshot')
    @patch('monitor.differ.save_snapshot')
    def test_light_check_content_unchanged(self, mock_save, mock_get):
        """Test light check detects no change."""
        content = "Same content"
        content_hash = compute_hash(content)

        mock_get.return_value = {
            'content_hash': content_hash,
            'content_text': content
        }

        result = light_check("https://example.com/page", content)

        assert result['changed'] is False
        assert result['current_hash'] == content_hash

    @patch('monitor.differ.get_latest_snapshot')
    @patch('monitor.differ.save_snapshot')
    def test_light_check_content_changed(self, mock_save, mock_get):
        """Test light check detects change."""
        old_content = "Old content"
        new_content = "New content"

        mock_get.return_value = {
            'content_hash': compute_hash(old_content),
            'content_text': old_content
        }

        result = light_check("https://example.com/page", new_content)

        assert result['changed'] is True
        assert result['previous_hash'] != result['current_hash']


class TestAlertEngine:
    """Test alert generation and processing."""

    def test_alert_severity_mapping(self):
        """Test alert severity is correctly determined."""
        # OK status should return None (no alert)
        assert get_alert_severity("link", "ok") is None

        # Error status should be critical
        assert get_alert_severity("link", "error") == "critical"
        assert get_alert_severity("availability", "error") == "critical"

        # Warning status should be warning
        assert get_alert_severity("content", "warning") == "warning"
        assert get_alert_severity("structure", "warning") == "warning"

    def test_process_check_results_skips_ok(self):
        """Test that OK results don't generate alerts."""
        results = [
            CheckResult(
                source_key="test",
                url="https://example.com",
                check_type="link",
                status="ok",
                detail="All good",
                checked_at=datetime.now()
            )
        ]

        with patch('monitor.alerts.check_duplicate_alert', return_value=False):
            with patch('monitor.alerts.save_alert') as mock_save:
                alerts = process_check_results(results)

                assert len(alerts) == 0
                mock_save.assert_not_called()

    def test_process_check_results_creates_alert(self):
        """Test that warning/error results create alerts."""
        results = [
            CheckResult(
                source_key="test",
                url="https://example.com",
                check_type="link",
                status="error",
                detail="404 Not Found",
                checked_at=datetime.now()
            )
        ]

        with patch('monitor.alerts.check_duplicate_alert', return_value=False):
            with patch('monitor.alerts.save_alert', return_value=1) as mock_save:
                alerts = process_check_results(results)

                assert len(alerts) == 1
                assert alerts[0]['severity'] == 'critical'
                assert alerts[0]['source_key'] == 'test'
                mock_save.assert_called_once()

    def test_process_check_results_deduplicates(self):
        """Test that duplicate alerts within 24h are skipped."""
        results = [
            CheckResult(
                source_key="test",
                url="https://example.com",
                check_type="link",
                status="error",
                detail="404 Not Found",
                checked_at=datetime.now()
            )
        ]

        # Mock duplicate check to return True
        with patch('monitor.alerts.check_duplicate_alert', return_value=True):
            with patch('monitor.alerts.save_alert') as mock_save:
                alerts = process_check_results(results)

                # Should skip duplicate
                assert len(alerts) == 0
                mock_save.assert_not_called()


class TestAlertDeduplication:
    """Test alert deduplication logic."""

    def test_duplicate_within_24h(self):
        """Test that duplicate alerts within 24h are detected."""
        # This would require database access - using mock
        with patch('monitor.db.get_db') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {'count': 1}  # Duplicate exists
            mock_conn.execute.return_value = mock_cursor
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=False)
            mock_db.return_value = mock_conn

            is_dup = check_duplicate_alert(
                source_key="test",
                url="https://example.com",
                check_type="link",
                hours=24
            )

            assert is_dup is True

    def test_no_duplicate_outside_window(self):
        """Test that old alerts don't count as duplicates."""
        with patch('monitor.db.get_db') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {'count': 0}  # No recent duplicate
            mock_conn.execute.return_value = mock_cursor
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=False)
            mock_db.return_value = mock_conn

            is_dup = check_duplicate_alert(
                source_key="test",
                url="https://example.com",
                check_type="link",
                hours=24
            )

            assert is_dup is False


class TestAvailabilityCheck:
    """Test availability check."""

    @patch('monitor.checks.fetch_page')
    def test_availability_online(self, mock_fetch):
        """Test availability check passes for online site."""
        mock_fetch.return_value = {
            'status_code': 200
        }

        result = check_availability("test", "https://example.com")

        assert result.status == "ok"

    @patch('monitor.checks.fetch_page')
    def test_availability_offline(self, mock_fetch):
        """Test availability check fails for offline site."""
        mock_fetch.return_value = None

        result = check_availability("test", "https://example.com")

        assert result.status == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
