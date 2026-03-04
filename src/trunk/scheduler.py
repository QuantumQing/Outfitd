"""APScheduler — monthly trunk generation + daily 30-day retention check."""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def monthly_trunk_job():
    """Generate a new trunk on the 1st of each month."""
    from src.trunk.service import generate_trunk
    logger.info("Monthly trunk generation triggered by scheduler")
    try:
        trunk = await generate_trunk()
        logger.info(f"Monthly trunk #{trunk.id} generated successfully")
    except Exception as e:
        logger.error(f"Monthly trunk generation failed: {e}")


async def retention_check_job():
    """Check for items purchased 30+ days ago and auto-mark as 'kept'."""
    from src.database import get_db
    from src.feedback.service import record_keep

    logger.info("Running 30-day retention check...")
    with get_db() as conn:
        # Find purchased items older than 30 days that haven't been returned
        rows = conn.execute("""
            SELECT ti.id FROM trunk_item ti
            JOIN trunk t ON ti.trunk_id = t.id
            LEFT JOIN feedback f ON ti.id = f.trunk_item_id AND f.action = 'keep'
            WHERE ti.decision = 'purchase'
              AND ti.returned = 0
              AND julianday('now') - julianday(t.generated_at) >= 30
              AND f.id IS NULL
        """).fetchall()

        for row in rows:
            record_keep(row["id"])

    logger.info(f"Retention check complete: {len(rows)} items marked as kept")


def start_scheduler():
    """Configure and start the scheduler."""
    # Monthly trunk generation — 1st of each month at 9 AM
    scheduler.add_job(
        monthly_trunk_job,
        CronTrigger(day=1, hour=9, minute=0),
        id="monthly_trunk",
        replace_existing=True,
    )

    # Daily retention check — every day at midnight
    scheduler.add_job(
        retention_check_job,
        CronTrigger(hour=0, minute=0),
        id="retention_check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: monthly trunk (1st @ 9am), retention check (daily @ midnight)")
