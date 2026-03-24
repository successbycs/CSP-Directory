"""Python-owned scheduler entrypoint for discovery and weekly digest jobs."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

from services.config.load_config import load_pipeline_config
from services.pipeline.scheduler_config import load_scheduler_config
from services.pipeline.run_mvp_pipeline import run_mvp_pipeline

logger = logging.getLogger(__name__)

STAGE_ORDER = [
    "Sign",
    "Onboard",
    "Activate",
    "Adopt",
    "Support",
    "Expand",
    "Renew",
    "Advocate",
]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_environment() -> None:
    """Load local environment variables from .env."""
    load_dotenv(PROJECT_ROOT / ".env")


def run_discovery_job() -> list[dict[str, str]]:
    """Run the daily discovery pipeline using the configured default queries."""
    queries = _load_scheduled_discovery_queries()
    logger.info("Running scheduled discovery for queries: %s", ", ".join(queries))
    return run_mvp_pipeline(queries)


def run_weekly_digest_job() -> None:
    """Build and post the weekly lifecycle-stage digest."""
    scheduler_config = load_scheduler_config()
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_CHANNEL_ID",
        "GOOGLE_SHEETS_ID",
    ]
    missing_vars = [name for name in required_vars if not os.getenv(name)]
    if missing_vars:
        logger.warning("Skipping weekly digest; missing env vars: %s", ", ".join(missing_vars))
        return

    from supabase import create_client

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    cutoff = (date.today() - timedelta(days=scheduler_config.digest.lookback_days)).isoformat()
    response = (
        supabase.table("cs_vendors")
        .select("name,website,mission,lifecycle_stages,first_seen,is_new")
        .gte("first_seen", cutoff)
        .eq("is_new", True)
        .execute()
    )

    vendors = response.data or []
    grouped = {stage: [] for stage in STAGE_ORDER}
    for vendor in vendors:
        for stage in vendor.get("lifecycle_stages") or []:
            if stage in grouped:
                grouped[stage].append(vendor)

    week_of = date.today().isoformat()
    lines = [
        f"*CS AI Vendor Weekly Digest* — {len(vendors)} new vendors found",
        f"Week of {week_of}",
        "",
    ]
    for stage in STAGE_ORDER:
        lines.append(f"*{stage.upper()}*")
        stage_vendors = grouped[stage]
        if not stage_vendors:
            lines.append("- None")
        else:
            for vendor in stage_vendors:
                name = vendor.get("name") or "Unknown Vendor"
                website = vendor.get("website") or ""
                mission = vendor.get("mission") or "No mission statement captured."
                lines.append(f"- {name} | {website}")
                lines.append(f"  _{mission}_")
        lines.append("")

    lines.append(f"https://docs.google.com/spreadsheets/d/{os.environ['GOOGLE_SHEETS_ID']}")
    message = "\n".join(lines)
    response = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "channel": os.environ["SLACK_CHANNEL_ID"],
            "text": message,
            "mrkdwn": True,
        },
        timeout=scheduler_config.digest.slack_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Slack API error: {payload}")

    for vendor in vendors:
        website = vendor.get("website")
        if website:
            supabase.table("cs_vendors").update({"is_new": False}).eq("website", website).execute()


def build_parser() -> argparse.ArgumentParser:
    """Create the scheduler CLI argument parser."""
    parser = argparse.ArgumentParser(description="Run the Python-owned pipeline scheduler.")
    parser.add_argument(
        "--run-now",
        choices=["discovery", "digest"],
        help="Run a single job immediately instead of starting the scheduler loop.",
    )
    return parser


def _load_scheduled_discovery_queries() -> list[str]:
    """Resolve scheduled discovery queries from env overrides or repo config."""
    env_queries = os.getenv("DISCOVERY_QUERIES")
    if env_queries:
        parsed_queries = [query.strip() for query in env_queries.split(",") if query.strip()]
        if parsed_queries:
            return parsed_queries

    env_query = os.getenv("DISCOVERY_QUERY")
    if env_query:
        return [env_query.strip()]

    config_queries = list(load_pipeline_config().discovery.queries)
    if config_queries:
        return config_queries

    return ["ai customer success platform"]


def main() -> int:
    """Run the scheduler entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_environment()
    args = build_parser().parse_args()

    if args.run_now == "discovery":
        run_discovery_job()
        return 0

    if args.run_now == "digest":
        run_weekly_digest_job()
        return 0

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler_config = load_scheduler_config()
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_discovery_job,
        "cron",
        hour=scheduler_config.discovery.hour,
        minute=scheduler_config.discovery.minute,
    )
    scheduler.add_job(
        run_weekly_digest_job,
        "cron",
        day_of_week=scheduler_config.digest.day_of_week,
        hour=scheduler_config.digest.hour,
        minute=scheduler_config.digest.minute,
    )
    logger.info("Starting Python-owned scheduler")
    scheduler.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
