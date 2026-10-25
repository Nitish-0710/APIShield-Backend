import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set
from sqlalchemy import or_, select, update

from app.core.config import settings
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.api import ApiEndpoint
from app.services.test_service import TestService


class MonitoringService:
    def __init__(self, session_factory=None) -> None:
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._active_tasks: Set[asyncio.Task] = set()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._session_factory = session_factory

    def set_session_factory(self, factory) -> None:
        """Allow configuring a custom session factory (e.g. for testing with shared SQLite)."""
        self._session_factory = factory

    def _get_session(self):
        return self._session_factory() if self._session_factory else SessionLocal()

    def start(self) -> None:
        """Start the background monitoring loop if enabled."""
        if not settings.MONITORING_ENABLED or self._running:
            return
        self._running = True
        self._semaphore = asyncio.Semaphore(settings.MONITORING_MAX_CONCURRENCY)
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("APIShield MonitoringService started.")

    async def stop(self) -> None:
        """Gracefully stop background monitoring and clean up running probes."""
        if not self._running:
            return
        self._running = False

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):
                pass
            self._loop_task = None

        if self._active_tasks:
            done, pending = await asyncio.wait(list(self._active_tasks), timeout=10.0)
            for t in pending:
                t.cancel()

        # Reset any stuck probing flags in the database
        try:
            with self._get_session() as db:
                db.execute(
                    update(ApiEndpoint)
                    .where(ApiEndpoint.is_probing == True)
                    .values(is_probing=False)
                )
                db.commit()
        except Exception as exc:
            logger.error(f"Error resetting is_probing flags on shutdown: {exc}")

        logger.info("APIShield MonitoringService stopped cleanly.")

    async def tick(self) -> int:
        """Run a single monitoring scheduler tick.

        - Queries APIs with monitoring enabled whose next_run_at <= now.
        - Atomically claims candidates with is_probing=True and sets next_run_at to now + interval_sec.
        - Skips APIs already claimed by another worker (preventing duplicate jobs across instances).
        - Dispatches probe execution bounded by the concurrency semaphore.
        - Returns the number of successfully claimed APIs.
        """
        now = datetime.now(timezone.utc)
        claimed_ids: List[str] = []

        with self._get_session() as db:
            stmt = (
                select(ApiEndpoint.id, ApiEndpoint.interval_sec)
                .where(
                    ApiEndpoint.monitoring == True,
                    ApiEndpoint.is_probing == False,
                    or_(ApiEndpoint.next_run_at == None, ApiEndpoint.next_run_at <= now),
                )
                .limit(settings.MONITORING_MAX_CONCURRENCY)
            )
            candidates = db.execute(stmt).all()

            for api_id, interval_sec in candidates:
                next_run = now + timedelta(seconds=interval_sec)
                # Atomic update claim ensures only one worker proceeds if multiple race for the same record
                claim_stmt = (
                    update(ApiEndpoint)
                    .where(
                        ApiEndpoint.id == api_id,
                        ApiEndpoint.monitoring == True,
                        ApiEndpoint.is_probing == False,
                        or_(ApiEndpoint.next_run_at == None, ApiEndpoint.next_run_at <= now),
                    )
                    .values(is_probing=True, next_run_at=next_run)
                )
                res = db.execute(claim_stmt)
                if res.rowcount == 1:
                    claimed_ids.append(api_id)
            db.commit()

        if not claimed_ids:
            return 0

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.MONITORING_MAX_CONCURRENCY)

        for api_id in claimed_ids:
            task = asyncio.create_task(self._run_probe(api_id))
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

        return len(claimed_ids)

    async def wait_for_active_probes(self, timeout: float = 10.0) -> None:
        """Helper to wait for in-flight probe tasks to finish."""
        if self._active_tasks:
            await asyncio.wait(list(self._active_tasks), timeout=timeout)

    async def _run_probe(self, api_id: str) -> None:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.MONITORING_MAX_CONCURRENCY)

        async with self._semaphore:
            try:
                await asyncio.to_thread(self._execute_probe_in_thread, api_id)
            except Exception as exc:
                logger.error(f"Error in probe task for API {api_id}: {exc}")
            finally:
                self._release_probe(api_id)

    def _execute_probe_in_thread(self, api_id: str) -> None:
        with self._get_session() as db:
            try:
                TestService.run_saved_api_test(
                    db=db,
                    user=None,
                    api_id=api_id,
                    is_automated=True,
                )
            except Exception as exc:
                logger.error(f"Automated probe execution failed for API {api_id}: {exc}")

    def _release_probe(self, api_id: str) -> None:
        try:
            with self._get_session() as db:
                db.execute(
                    update(ApiEndpoint)
                    .where(ApiEndpoint.id == api_id)
                    .values(is_probing=False)
                )
                db.commit()
        except Exception as exc:
            logger.error(f"Error resetting is_probing for API {api_id}: {exc}")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except Exception as exc:
                logger.error(f"Unexpected error in monitoring tick loop: {exc}")

            try:
                await asyncio.sleep(settings.MONITORING_TICK_SECONDS)
            except asyncio.CancelledError:
                break


# Global singleton instance
monitoring_service = MonitoringService()
