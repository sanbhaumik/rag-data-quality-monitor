"""
Alert Engine (SMTP).
Evaluates check results, generates alerts, and sends email notifications.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from datetime import datetime
import config
from monitor.db import (
    save_alert,
    mark_alert_emailed,
    check_duplicate_alert
)

logger = logging.getLogger(__name__)


# Alert severity mapping
SEVERITY_MAP = {
    # status="warning" → severity "warning"
    'warning': {
        'content': 'warning',      # Content changed
        'structure': 'warning',    # Structure shifted
        'staleness': 'warning',    # Content is stale
        'paywall': 'warning',      # Possible paywall
        'link': 'warning',         # Link moved/redirected
    },
    # status="error" → severity "critical"
    'critical': {
        'link': 'critical',        # Link broken
        'availability': 'critical', # Site offline
        'paywall': 'critical',     # Access denied (401/403)
    }
}


def get_alert_severity(check_type: str, status: str) -> str:
    """
    Determine alert severity based on check type and status.

    Args:
        check_type: Type of check
        status: Check status ("ok", "warning", "error")

    Returns:
        "warning" or "critical"
    """
    if status == "ok":
        return None  # No alert needed

    if status == "error":
        return "critical"

    # status == "warning"
    return "warning"


def process_check_results(results: List) -> List[Dict]:
    """
    Evaluate check results and create alerts for issues.
    Deduplicates alerts (won't re-alert for same issue within 24h).

    Args:
        results: List of CheckResult objects

    Returns:
        List of newly created alert dicts
    """
    new_alerts = []

    for result in results:
        # Skip if check passed
        if result.status == "ok":
            continue

        # Determine severity
        severity = get_alert_severity(result.check_type, result.status)

        if not severity:
            continue

        # Check for duplicate
        is_duplicate = check_duplicate_alert(
            source_key=result.source_key,
            url=result.url,
            check_type=result.check_type,
            hours=24
        )

        if is_duplicate:
            logger.debug(f"Skipping duplicate alert: {result.source_key}/{result.check_type}")
            continue

        # Create alert message
        message = f"{result.source_key} - {result.check_type}: {result.detail}"

        # Save alert to database
        alert_id = save_alert(
            source_key=result.source_key,
            url=result.url,
            check_type=result.check_type,
            severity=severity,
            message=message
        )

        alert = {
            'id': alert_id,
            'source_key': result.source_key,
            'url': result.url,
            'check_type': result.check_type,
            'severity': severity,
            'message': message,
            'created_at': result.checked_at
        }

        new_alerts.append(alert)
        logger.info(f"Created {severity} alert: {message[:60]}...")

    logger.info(f"Processed {len(results)} check results → {len(new_alerts)} new alerts")
    return new_alerts


def create_email_html(alerts: List[Dict]) -> str:
    """
    Create HTML email body for alerts.

    Args:
        alerts: List of alert dicts

    Returns:
        HTML string
    """
    if not alerts:
        return "<html><body><p>No alerts to report.</p></body></html>"

    # Group by severity
    critical_alerts = [a for a in alerts if a['severity'] == 'critical']
    warning_alerts = [a for a in alerts if a['severity'] == 'warning']

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #f44336; color: white; padding: 20px; }}
            .summary {{ background-color: #f5f5f5; padding: 15px; margin: 20px 0; }}
            .alert-section {{ margin: 20px 0; }}
            .alert-critical {{
                border-left: 4px solid #f44336;
                background-color: #ffebee;
                padding: 12px;
                margin: 10px 0;
            }}
            .alert-warning {{
                border-left: 4px solid #ff9800;
                background-color: #fff3e0;
                padding: 12px;
                margin: 10px 0;
            }}
            .alert-title {{ font-weight: bold; margin-bottom: 5px; }}
            .alert-detail {{ color: #666; font-size: 14px; }}
            .alert-url {{ color: #1976d2; font-size: 12px; word-break: break-all; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚨 RAG Source Monitor Alert</h1>
        </div>

        <div class="summary">
            <h2>Alert Summary</h2>
            <p><strong>Total Alerts:</strong> {len(alerts)}</p>
            <p><strong>Critical:</strong> {len(critical_alerts)} | <strong>Warnings:</strong> {len(warning_alerts)}</p>
            <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
    """

    # Critical alerts section
    if critical_alerts:
        html += """
        <div class="alert-section">
            <h2>🔴 Critical Alerts</h2>
        """
        for alert in critical_alerts:
            html += f"""
            <div class="alert-critical">
                <div class="alert-title">{alert['source_key']} - {alert['check_type'].upper()}</div>
                <div class="alert-detail">{alert['message']}</div>
                <div class="alert-url">{alert['url']}</div>
            </div>
            """
        html += "</div>"

    # Warning alerts section
    if warning_alerts:
        html += """
        <div class="alert-section">
            <h2>⚠️ Warnings</h2>
        """
        for alert in warning_alerts:
            html += f"""
            <div class="alert-warning">
                <div class="alert-title">{alert['source_key']} - {alert['check_type'].upper()}</div>
                <div class="alert-detail">{alert['message']}</div>
                <div class="alert-url">{alert['url']}</div>
            </div>
            """
        html += "</div>"

    html += """
        <div class="footer">
            <p>This is an automated alert from the RAG Source Monitor.</p>
            <p>To view the health dashboard, access the Streamlit application.</p>
        </div>
    </body>
    </html>
    """

    return html


def send_alert_email(alert: Dict) -> bool:
    """
    Send a single alert email via SMTP.

    Args:
        alert: Alert dict

    Returns:
        True on success, False on failure
    """
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[{alert['severity'].upper()}] RAG Monitor: {alert['source_key']}"
        msg['From'] = config.SMTP_USER
        msg['To'] = config.ALERT_RECIPIENT

        # Create HTML content
        html = create_email_html([alert])
        msg.attach(MIMEText(html, 'html'))

        # Send email
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Sent alert email for {alert['source_key']}/{alert['check_type']}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed - check credentials")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending alert: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
        return False


def send_digest_email(alerts: List[Dict]) -> bool:
    """
    Send a batch digest email with all alerts.

    Args:
        alerts: List of alert dicts

    Returns:
        True on success, False on failure
    """
    if not alerts:
        logger.info("No alerts to send")
        return True

    try:
        # Count by severity
        critical_count = sum(1 for a in alerts if a['severity'] == 'critical')
        warning_count = sum(1 for a in alerts if a['severity'] == 'warning')

        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"RAG Monitor Digest: {critical_count} Critical, {warning_count} Warnings"
        msg['From'] = config.SMTP_USER
        msg['To'] = config.ALERT_RECIPIENT

        # Create HTML content
        html = create_email_html(alerts)
        msg.attach(MIMEText(html, 'html'))

        # Send email
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Sent digest email with {len(alerts)} alerts")

        # Mark all alerts as emailed
        for alert in alerts:
            if 'id' in alert:
                mark_alert_emailed(alert['id'])

        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed - check credentials")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending digest: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to send digest email: {e}")
        return False


if __name__ == "__main__":
    # Test the alert engine
    import config
    from monitor.checks import run_all_checks

    logger.info("Testing alert engine...")

    # Run checks on sample pages
    test_sources = {}
    for key, cfg in config.SOURCE_SITES.items():
        test_sources[key] = {
            **cfg,
            'pages': [cfg['pages'][0]]  # Only first page
        }

    print("\nRunning source checks...")
    results = run_all_checks(test_sources)

    print(f"\nProcessing {len(results)} check results...")
    alerts = process_check_results(results)

    print(f"\n{'='*60}")
    print(f"Generated {len(alerts)} new alerts:")
    for alert in alerts:
        symbol = "🔴" if alert['severity'] == 'critical' else "⚠️"
        print(f"  {symbol} [{alert['severity']:8}] {alert['source_key']:15} - {alert['message'][:50]}...")

    if alerts:
        print(f"\n{'='*60}")
        print("Attempting to send digest email...")
        success = send_digest_email(alerts)
        if success:
            print("✓ Digest email sent successfully!")
        else:
            print("✗ Failed to send digest email (check logs)")
    else:
        print("\n✓ No alerts to send - all checks passed!")

    print(f"\n{'='*60}")
    print("Alert engine test complete!")
