from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress

import certifi

# Set SSL cert path before discord.py / aiohttp create their default contexts.
# (Mac python.org Python doesn't ship root CAs.)
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from .bot import PTTAlertorBot  # noqa: E402
from .context import AppContext
from .crawler import PTTClient
from .jobs import (
    CommentChecker,
    KeywordChecker,
    PushsumChecker,
    recover_from_last_heartbeat,
    run_heartbeat,
)
from .logger import get_logger, setup_logging
from .notify import Deduper, DiscordSender
from .settings import Settings, ensure_dirs, load_settings
from .storage import (
    ArticleSubsRepo,
    BoardRepo,
    HeartbeatStore,
    PushsumSubsRepo,
    SubscriptionIndex,
    UserRepo,
)
from .web import start_web_server, stop_web_server


async def _build_context(settings: Settings) -> AppContext:
    log = get_logger(__name__)
    log.info("Loading storage repos...")

    user_repo = UserRepo(settings.data_dir)
    board_repo = BoardRepo(settings.data_dir)
    article_subs = ArticleSubsRepo(settings.data_dir)
    pushsum_subs = PushsumSubsRepo(settings.data_dir)
    heartbeat = HeartbeatStore(settings.data_dir)

    await user_repo.load_all()
    await board_repo.load_all()
    await article_subs.load()
    await pushsum_subs.load()
    await heartbeat.load()

    sub_index = SubscriptionIndex(user_repo)
    sub_index.rebuild()

    deduper = Deduper(ttl_seconds=settings.dedup_ttl_seconds)
    sender = DiscordSender(deduper)
    crawler = PTTClient()
    await crawler.start()

    return AppContext(
        settings=settings,
        user_repo=user_repo,
        board_repo=board_repo,
        article_subs=article_subs,
        pushsum_subs=pushsum_subs,
        heartbeat=heartbeat,
        sub_index=sub_index,
        deduper=deduper,
        sender=sender,
        crawler=crawler,
    )


async def _run_async(settings: Settings) -> None:
    log = get_logger(__name__)
    ctx = await _build_context(settings)

    log.info("Running recovery (catch up since last heartbeat)...")
    try:
        await recover_from_last_heartbeat(ctx)
    except Exception:
        log.exception("Recovery failed (continuing anyway)")

    bot = PTTAlertorBot(ctx)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        if not stop.is_set():
            log.info("Stop signal received")
            stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    web_runner, _ = await start_web_server(ctx)

    keyword_checker = KeywordChecker(ctx)
    pushsum_checker = PushsumChecker(ctx)
    comment_checker = CommentChecker(ctx)

    background_tasks: list[asyncio.Task] = [
        asyncio.create_task(run_heartbeat(ctx, stop), name="heartbeat"),
        asyncio.create_task(keyword_checker.run(stop), name="keyword_checker"),
        asyncio.create_task(pushsum_checker.run(stop), name="pushsum_checker"),
        asyncio.create_task(comment_checker.run(stop), name="comment_checker"),
    ]

    async def _run_bot() -> None:
        try:
            await bot.start(settings.discord_token)
        except Exception as exc:
            log.exception("Discord bot exited with error: %s", exc)
        finally:
            stop.set()

    bot_task = asyncio.create_task(_run_bot(), name="discord")

    try:
        await stop.wait()
    finally:
        log.info("Shutting down...")

        # Stop bot first to prevent more events firing
        if not bot.is_closed():
            try:
                await bot.close()
            except Exception:
                log.exception("Bot close failed")

        with suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(bot_task, timeout=5.0)

        # Wait for background tasks (they should exit cleanly when stop is set)
        for t in background_tasks:
            with suppress(asyncio.CancelledError, Exception):
                try:
                    await asyncio.wait_for(t, timeout=10.0)
                except asyncio.TimeoutError:
                    t.cancel()

        await stop_web_server(web_runner)

        try:
            await ctx.user_repo.flush()
        except Exception:
            log.exception("User flush failed")

        try:
            await ctx.crawler.close()
        except Exception:
            log.exception("Crawler close failed")
        log.info("Shutdown complete")


def run() -> int:
    settings = load_settings()
    ensure_dirs(settings)
    setup_logging(settings.log_dir)
    log = get_logger(__name__)
    log.info("PTT Alertor starting (Python)")
    try:
        asyncio.run(_run_async(settings))
    except KeyboardInterrupt:
        log.info("Interrupted")
    return 0
