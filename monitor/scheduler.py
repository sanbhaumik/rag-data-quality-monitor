"""
Monitor Scheduler.
Schedules periodic monitoring checks using APScheduler.
Defaults to on-demand execution (scheduler not started automatically).
"""

import logging
from typing import Optional, List, Dict
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import config
from monitor.checks import run_all_checks
from monitor.alerts import process_check_results, send_digest_email

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def _run_scheduled_check(deep_diff: bool = False):
    """
    Internal function that runs the monitoring workflow.
    Called by scheduler or on-demand.

    Args:
        deep_diff: Enable deep diff for content checks
    """
    logger.info("="*60)
    logger.info("Starting scheduled monitoring check")
    logger.info("="*60)

    try:
        # Step 1: Run all checks
        logger.info("Running source quality checks...")
        results = run_all_checks(config.SOURCE_SITES, deep_diff=deep_diff)
        logger.info(f"Completed {len(results)} checks")

        # Step 2: Process results and create alerts
        logger.info("Processing check results...")
        alerts = process_check_results(results)
        logger.info(f"Generated {len(alerts)} new alerts")

        # Step 3: Send digest email if there are alerts
        if alerts:
            logger.info("Sending alert digest email...")
            success = send_digest_email(alerts)
            if success:
                logger.info("Digest email sent successfully")
            else:
                logger.error("Failed to send digest email")
        else:
            logger.info("No alerts to send - all checks passed")

        logger.info("="*60)
        logger.info("Scheduled monitoring check complete")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"Error in scheduled check: {e}", exc_info=True)


def run_monitor_now(deep_diff: bool = False) -> Dict:
    """
    Run monitoring checks immediately (on-demand).

    Args:
        deep_diff: Enable deep diff for content checks

    Returns:
        Dict with results summary: {
            'total_checks': int,
            'alerts': list,
            'email_sent': bool
        }
    """
    logger.info("Running on-demand monitoring check...")

    try:
        # Run all checks
        results = run_all_checks(config.SOURCE_SITES, deep_diff=deep_diff)

        # Process results and create alerts
        alerts = process_check_results(results)

        # Send digest email if there are alerts
        email_sent = False
        if alerts:
            email_sent = send_digest_email(alerts)

        return {
            'total_checks': len(results),
            'alerts': alerts,
            'email_sent': email_sent,
            'timestamp': datetime.now()
        }

    except Exception as e:
        logger.error(f"Error in on-demand check: {e}", exc_info=True)
        raise


def start_scheduler(interval_hours: Optional[int] = None) -> BackgroundScheduler:
    """
    Start the background scheduler for periodic checks.

    Args:
        interval_hours: Check interval in hours (default: from config)

    Returns:
        BackgroundScheduler instance
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.warning("Scheduler is already running")
        return _scheduler

    if interval_hours is None:
        interval_hours = config.MONITOR_SCHEDULE_HOURS

    logger.info(f"Starting monitoring scheduler (interval: {interval_hours} hours)")

    _scheduler = BackgroundScheduler()

    # Add job with interval trigger
    _scheduler.add_job(
        func=_run_scheduled_check,
        trigger=IntervalTrigger(hours=interval_hours),
        id='monitor_checks',
        name='Source Quality Monitoring',
        replace_existing=True
    )

    _scheduler.start()
    logger.info("Scheduler started successfully")

    return _scheduler


def stop_scheduler():
    """
    Stop the background scheduler gracefully.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Stopping monitoring scheduler...")
        _scheduler.shutdown(wait=True)
        _scheduler = None
        logger.info("Scheduler stopped")
    else:
        logger.info("Scheduler is not running")


def is_scheduler_running() -> bool:
    """
    Check if the scheduler is currently running.

    Returns:
        True if running, False otherwise
    """
    return _scheduler is not None and _scheduler.running


def get_scheduler_status() -> Dict:
    """
    Get scheduler status information.

    Returns:
        Dict with scheduler status: {
            'running': bool,
            'interval_hours': int,
            'next_run': datetime or None,
            'job_count': int
        }
    """
    if not _scheduler or not _scheduler.running:
        return {
            'running': False,
            'interval_hours': config.MONITOR_SCHEDULE_HOURS,
            'next_run': None,
            'job_count': 0
        }

    jobs = _scheduler.get_jobs()
    next_run = None

    if jobs:
        job = jobs[0]
        next_run = job.next_run_time

    return {
        'running': True,
        'interval_hours': config.MONITOR_SCHEDULE_HOURS,
        'next_run': next_run,
        'job_count': len(jobs)
    }


def get_scheduler_instance() -> Optional[BackgroundScheduler]:
    """
    Get the scheduler instance (for advanced usage).

    Returns:
        BackgroundScheduler instance or None
    """
    return _scheduler


if __name__ == "__main__":
    # Test the scheduler
    import time

    logger.info("Testing monitor scheduler...")

    print("\n" + "="*60)
    print("Test 1: On-Demand Execution")
    print("="*60)

    result = run_monitor_now(deep_diff=False)
    print(f"\n✓ On-demand check complete:")
    print(f"  Total checks: {result['total_checks']}")
    print(f"  New alerts: {len(result['alerts'])}")
    print(f"  Email sent: {result['email_sent']}")

    for alert in result['alerts']:
        symbol = "🔴" if alert['severity'] == 'critical' else "⚠️"
        print(f"    {symbol} {alert['source_key']}: {alert['message'][:60]}...")

    print("\n" + "="*60)
    print("Test 2: Scheduler Status (Not Started)")
    print("="*60)

    status = get_scheduler_status()
    print(f"\n✓ Scheduler status:")
    print(f"  Running: {status['running']}")
    print(f"  Interval: {status['interval_hours']} hours")
    print(f"  Next run: {status['next_run']}")

    print("\n" + "="*60)
    print("Test 3: Start Scheduler (5 second interval for testing)")
    print("="*60)

    # Use very short interval for testing
    scheduler = start_scheduler(interval_hours=1/720)  # ~5 seconds
    print(f"\n✓ Scheduler started")

    status = get_scheduler_status()
    print(f"  Running: {status['running']}")
    print(f"  Next run: {status['next_run']}")

    print("\nWaiting 8 seconds to see if scheduled job runs...")
    time.sleep(8)

    print("\n" + "="*60)
    print("Test 4: Stop Scheduler")
    print("="*60)

    stop_scheduler()
    print("\n✓ Scheduler stopped")

    status = get_scheduler_status()
    print(f"  Running: {status['running']}")

    print("\n" + "="*60)
    print("✓ All scheduler tests complete!")
    print("="*60)
