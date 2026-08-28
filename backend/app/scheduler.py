"""
Background scheduler for periodic tasks using APScheduler.
Currently handles transaction syncing for all Plaid items every 6 hours.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def sync_all_items():
    """
    Sync transactions for all linked Plaid items (new/modified/removed),
    refresh balances, and take today's snapshot. Called periodically by
    the scheduler; shares app.sync_engine.sync_item with the manual
    "Sync now" endpoint so both paths behave identically.
    """
    try:
        from app.budgets_db import BudgetsSessionLocal
        from app.database import SessionLocal
        from app.notifications import notify_new_alerts
        from app.sync_engine import get_real_items, sync_item

        db = SessionLocal()
        try:
            items = get_real_items(db)

            for item in items:
                try:
                    stats = sync_item(db, item)
                    logger.info(f"Synced item {item.id}: {stats['synced']} new, {stats['removed']} removed")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Error syncing item {item.id}: {str(e)}")
                    continue

            try:
                from app.crypto_sync import sync_crypto_wallets
                crypto_stats = sync_crypto_wallets(db)
                if not crypto_stats.get("skipped"):
                    logger.info(
                        "Crypto wallets synced: %s ok, %s failed",
                        crypto_stats.get("synced"),
                        crypto_stats.get("failed"),
                    )
            except Exception as e:
                db.rollback()
                logger.error(f"Crypto wallet sync failed: {str(e)}")

            # Freshly-synced data may have tripped a budget or large-transaction
            # alert; deliver any new ones to ALERT_WEBHOOK_URL (no-op if unset).
            bdb = BudgetsSessionLocal()
            try:
                notify_new_alerts(db, bdb)
            except Exception as e:
                db.rollback()
                logger.error(f"Alert webhook check failed: {str(e)}")
            finally:
                bdb.close()
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Scheduler sync_all_items failed: {str(e)}")


def send_weekly_email_job():
    """
    Compute and send the weekly spending-vs-budget summary email. No-op unless
    RESEND_API_KEY and WEEKLY_EMAIL_TO are set (see app.weekly_summary). Runs
    on its own weekly cron, independent of the 6-hour sync loop.
    """
    try:
        from app.budgets_db import BudgetsSessionLocal
        from app.database import SessionLocal
        from app.weekly_summary import send_weekly_summary

        db = SessionLocal()
        bdb = BudgetsSessionLocal()
        try:
            send_weekly_summary(db, bdb)
        finally:
            bdb.close()
            db.close()
    except Exception as e:
        logger.error(f"Weekly email job failed: {str(e)}")


def expire_stale_proposals():
    """
    Sweep AI advisor proposals: mark pending ones older than PROPOSAL_TTL_DAYS
    (default 7) as 'expired' so the Advisor queue never accumulates stale
    suggestions. Applied/dismissed/undone rows are kept for history.
    """
    import os
    from datetime import datetime, timedelta

    try:
        from app.budgets_db import BudgetsSessionLocal, Proposal

        try:
            ttl_days = int(os.getenv("PROPOSAL_TTL_DAYS", "7"))
        except ValueError:
            ttl_days = 7
        cutoff = datetime.utcnow() - timedelta(days=ttl_days)

        pdb = BudgetsSessionLocal()
        try:
            stale = (
                pdb.query(Proposal)
                .filter(Proposal.status == "pending", Proposal.created_at < cutoff)
                .all()
            )
            for p in stale:
                p.status = "expired"
            if stale:
                pdb.commit()
                logger.info(f"Expired {len(stale)} stale proposal(s)")
        finally:
            pdb.close()
    except Exception as e:
        logger.error(f"Proposal expiry sweep failed: {str(e)}")


def sync_market_data_job():
    """
    Refresh daily price history (app.services.price_sync_service) for every
    held + benchmark ticker, and the cached risk-free rate (app.risk_free_rate)
    used by Sharpe-ratio calculations. Runs nightly, independent of the Plaid
    sync loop — market data comes from yfinance/FRED, not Plaid.
    """
    try:
        from app.database import SessionLocal
        from app.risk_free_rate import get_cached_risk_free_rate
        from app.services.price_sync_service import sync_market_prices

        db = SessionLocal()
        try:
            price_stats = sync_market_prices(db)
            logger.info(
                "Market prices synced: %s tickers, %s rows",
                price_stats.get("tickers_synced"),
                price_stats.get("rows_upserted"),
            )
            rate = get_cached_risk_free_rate(db)
            logger.info(f"Risk-free rate refreshed: {rate}%")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Market data sync job failed: {str(e)}")


def sync_sector_data_job():
    """
    Refresh cached sector/asset-class/AUM classifications
    (app.services.sector_sync_service) for every held ticker that's missing
    or stale. Runs weekly, independent of the nightly market-data sync —
    sector/AUM composition barely moves day to day, unlike prices.
    """
    try:
        from app.database import SessionLocal
        from app.services.sector_sync_service import sync_sector_classifications

        db = SessionLocal()
        try:
            result = sync_sector_classifications(db)
            logger.info(
                "Sector classifications synced: %s tickers, %s errors",
                result.get("tickers_synced"),
                result.get("errors"),
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Sector sync job failed: {str(e)}")


def _current_sync_frequency_hours() -> int:
    """Read the persisted sync frequency (app_config), defaulting to 6h."""
    from app import app_config
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return app_config.get_sync_frequency_hours(db)
    except Exception as e:
        logger.error(f"Failed to read sync frequency setting, defaulting to 6h: {str(e)}")
        return app_config.DEFAULT_SYNC_FREQUENCY_HOURS
    finally:
        db.close()


def _add_sync_job(hours: int):
    """Add the sync_transactions job at the given interval. No-op if hours == 0 (manual)."""
    if hours <= 0:
        return
    scheduler.add_job(
        sync_all_items,
        IntervalTrigger(hours=hours),
        id="sync_transactions",
        name="Sync all Plaid transactions",
        replace_existing=True
    )


def reschedule_sync(hours: int):
    """
    Reschedule (or remove) the sync_transactions job at runtime, so a change
    to the sync frequency setting takes effect immediately without a restart.
    `hours == 0` means manual (no auto-sync) - the job is removed if present.
    """
    if not scheduler.running:
        logger.info("Scheduler not running; sync frequency will apply on next start")
        return

    try:
        scheduler.remove_job("sync_transactions")
    except Exception:
        pass  # job didn't exist - nothing to remove

    if hours > 0:
        _add_sync_job(hours)
        logger.info(f"Rescheduled sync_transactions to run every {hours}h")
    else:
        logger.info("Sync frequency set to manual; sync_transactions job removed")


def init_scheduler():
    """Initialize and start the background scheduler."""
    if scheduler.running:
        return

    # Sync transactions at the persisted frequency (default 6h; 0 = manual).
    _add_sync_job(_current_sync_frequency_hours())

    # Weekly spending summary email, Monday 08:00 (server local time).
    # Configurable via WEEKLY_EMAIL_DOW / WEEKLY_EMAIL_HOUR; no-op unless
    # RESEND_API_KEY + WEEKLY_EMAIL_TO are set.
    import os
    dow = os.getenv("WEEKLY_EMAIL_DOW", "mon").strip() or "mon"
    try:
        hour = int(os.getenv("WEEKLY_EMAIL_HOUR", "8"))
    except ValueError:
        hour = 8
    scheduler.add_job(
        send_weekly_email_job,
        CronTrigger(day_of_week=dow, hour=hour, minute=0),
        id="weekly_summary_email",
        name="Weekly spending summary email",
        replace_existing=True
    )

    # Expire stale AI advisor proposals daily at 03:00 (server local time).
    scheduler.add_job(
        expire_stale_proposals,
        CronTrigger(hour=3, minute=0),
        id="expire_proposals",
        name="Expire stale advisor proposals",
        replace_existing=True
    )

    # Refresh market prices + risk-free rate nightly at 04:00 (server local
    # time, after US market close data settles), independent of the Plaid
    # sync loop.
    scheduler.add_job(
        sync_market_data_job,
        CronTrigger(hour=4, minute=0),
        id="sync_market_data",
        name="Sync market prices + risk-free rate",
        replace_existing=True
    )

    # Refresh sector/asset-class/AUM classifications weekly, Sunday 05:00
    # (server local time, after the nightly price sync), independent of the
    # Plaid sync loop — sector data changes far less often than prices.
    scheduler.add_job(
        sync_sector_data_job,
        CronTrigger(day_of_week="sun", hour=5, minute=0),
        id="sync_sector_data",
        name="Sync sector/asset-class classifications",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Background scheduler started")


def shutdown_scheduler():
    """Gracefully shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler shut down")
