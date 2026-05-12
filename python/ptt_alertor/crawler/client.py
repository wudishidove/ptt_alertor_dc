from __future__ import annotations

import asyncio
import ssl
from typing import Any

import aiohttp
import certifi
from yarl import URL

from ..logger import get_logger

log = get_logger(__name__)

PTT_BASE = "https://www.ptt.cc"
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


class URLNotFound(Exception):
    pass


class PTTClient:
    """Lightweight async HTTP client for PTT with over18 cookie pre-set."""

    def __init__(self, *, timeout: aiohttp.ClientTimeout | None = None) -> None:
        self._timeout = timeout or DEFAULT_TIMEOUT
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "PTTClient":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def start(self) -> None:
        async with self._lock:
            if self._session is not None and not self._session.closed:
                return
            jar = aiohttp.CookieJar(unsafe=False)
            jar.update_cookies(
                {"over18": "1"}, response_url=URL("https://www.ptt.cc/")
            )
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit=20)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                timeout=self._timeout,
                headers=DEFAULT_HEADERS,
                connector=connector,
            )

    async def close(self) -> None:
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("PTTClient.start() not called")
        return self._session

    async def get_html(self, url: str) -> str:
        async with self.session.get(url, allow_redirects=True) as resp:
            if resp.status == 404:
                raise URLNotFound(url)
            resp.raise_for_status()
            return await resp.text()

    async def url_exists(self, url: str) -> bool:
        try:
            async with self.session.get(url, allow_redirects=True) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False
