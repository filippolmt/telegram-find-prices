"""
Scheduler for periodic tasks (daily summary).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient

from models import User, PriceHistory, Product
from translations import t, DEFAULT_LANGUAGE

log = logging.getLogger(__name__)


class DailySummaryScheduler:
    """Sends a daily summary of matches found."""

    def __init__(
        self,
        bot_client: TelegramClient,
        db_session_factory: sessionmaker,
        hour: int = 21,
        tz_name: str = "UTC",
    ):
        self.bot_client = bot_client
        self._session_factory = db_session_factory
        self.hour = hour
        self.tz = ZoneInfo(tz_name)
        self._task = None

    def start(self):
        """Start the scheduler loop."""
        self._task = asyncio.ensure_future(self._loop())
        log.info("Daily summary scheduler started (at %d:00 %s)", self.hour, self.tz)

    async def _loop(self):
        while True:
            now = datetime.now(self.tz)
            target = now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            log.info("Next summary in %.0f seconds (%s)", wait_seconds, target.strftime("%Y-%m-%d %H:%M %Z"))
            await asyncio.sleep(wait_seconds)

            await self._send_summaries()

    async def _send_summaries(self):
        today_start = datetime.now(self.tz).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        with self._session_factory() as session:
            users = session.query(User).filter(User.paused == False).all()  # noqa: E712
            user_data = [(u.user_id, u.lang_code or DEFAULT_LANGUAGE) for u in users]

        for uid, lang in user_data:
            with self._session_factory() as session:
                entries = (
                    session.query(PriceHistory)
                    .filter(
                        PriceHistory.user_id == uid,
                        PriceHistory.found_at >= today_start,
                    )
                    .order_by(PriceHistory.found_at.desc())
                    .all()
                )

                if not entries:
                    continue

                # Group by product
                by_product = {}
                for e in entries:
                    product = session.query(Product).filter_by(id=e.product_id).first()
                    name = product.name if product else "???"
                    by_product.setdefault(name, []).append(e)

                lines = [t("summary_header", lang, count=len(entries))]
                for name, matches in by_product.items():
                    lines.append(t("summary_product", lang, name=name, count=len(matches)))
                    for m in matches[:5]:
                        price_str = f"{m.price:.2f}" if m.price else "N/A"
                        link_str = f" " if m.message_link else ""
                        lines.append(f"  {price_str} in {m.channel}{link_str}")
                    if len(matches) > 5:
                        lines.append(t("summary_more", lang, count=len(matches) - 5))

            try:
                await self.bot_client.send_message(uid, "\n".join(lines))
                log.info("Summary sent to user_id=%s (%d matches)", uid, len(entries))
            except Exception as e:
                log.error("Error sending summary to %s: %s", uid, e)
