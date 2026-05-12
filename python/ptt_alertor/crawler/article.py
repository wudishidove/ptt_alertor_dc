from __future__ import annotations

from ..logger import get_logger
from ..models import Article
from .board import make_article_url
from .client import PTTClient, URLNotFound
from .parser import parse_article_page

log = get_logger(__name__)


async def fetch_article(client: PTTClient, board: str, code: str) -> Article:
    url = make_article_url(board, code)
    html = await client.get_html(url)
    return parse_article_page(html, board, code, url)


async def article_exists(client: PTTClient, board: str, code: str) -> bool:
    try:
        await client.get_html(make_article_url(board, code))
        return True
    except URLNotFound:
        return False
    except Exception as exc:  # pragma: no cover
        log.warning("Article exist check failed for %s/%s: %s", board, code, exc)
        return False
