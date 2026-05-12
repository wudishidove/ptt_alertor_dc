from __future__ import annotations

from ..logger import get_logger
from ..models import Article
from .client import PTT_BASE, PTTClient, URLNotFound
from .parser import parse_board_articles, parse_current_page

log = get_logger(__name__)


def make_board_url(board: str, page: int = -1) -> str:
    suffix = "" if page < 0 else str(page)
    return f"{PTT_BASE}/bbs/{board}/index{suffix}.html"


def make_article_url(board: str, code: str) -> str:
    return f"{PTT_BASE}/bbs/{board}/{code}.html"


async def current_page(client: PTTClient, board: str) -> int:
    html = await client.get_html(make_board_url(board, -1))
    return parse_current_page(html)


async def fetch_articles(client: PTTClient, board: str, page: int = -1) -> list[Article]:
    html = await client.get_html(make_board_url(board, page))
    return parse_board_articles(html, board)


async def board_exists(client: PTTClient, board: str) -> bool:
    try:
        await client.get_html(make_board_url(board, -1))
        return True
    except URLNotFound:
        return False
    except Exception as exc:  # pragma: no cover - network noise
        log.warning("Board exist check failed for %s: %s", board, exc)
        return False
