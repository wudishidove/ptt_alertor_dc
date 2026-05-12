from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from ..models import (
    PTT_BASE,
    Article,
    Comment,
    parse_article_id,
    parse_pushsum_text,
)

CST = timezone(timedelta(hours=8))
_PAGE_RE = re.compile(r"index(\d+)")
_IPDATETIME_RE = re.compile(
    r"(?:\d+\.\d+\.\d+\.\d+)?\s*(\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2})"
)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def parse_current_page(html: str) -> int:
    """Look at the paging block, find '上頁' link, parse its index number, +1."""
    s = soup(html)
    paging = s.select_one(".btn-group-paging")
    if not paging:
        return 0
    for a in paging.find_all("a"):
        text = a.get_text(strip=True)
        if "上頁" in text:
            href = a.get("href") or ""
            if not href:
                return 1
            m = _PAGE_RE.search(href)
            if not m:
                return 0
            return int(m.group(1)) + 1
    return 0


def parse_board_articles(html: str, board: str) -> list[Article]:
    """Parse board index page; stop at the .r-list-sep separator (置底開始)."""
    s = soup(html)
    container = s.select_one(".r-list-container") or s
    out: list[Article] = []
    for child in container.children:
        if not isinstance(child, Tag):
            continue
        classes = child.get("class") or []
        if "r-list-sep" in classes:
            break
        if "r-ent" not in classes:
            continue
        out.append(_parse_r_ent(child, board))
    return out


def _parse_r_ent(node: Tag, board: str) -> Article:
    art = Article(board=board)

    nrec = node.select_one(".nrec span")
    art.push_sum = parse_pushsum_text(nrec.get_text(strip=True)) if nrec else 0

    title_div = node.select_one(".title")
    if title_div:
        a = title_div.find("a")
        if a:
            art.title = a.get_text(strip=True)
            href = a.get("href") or ""
            if href:
                art.link = PTT_BASE + href if href.startswith("/") else href
                art.code = _extract_code(art.link)
                art.id = parse_article_id(art.link)
        else:
            art.title = title_div.get_text(strip=True)

    meta = node.select_one(".meta")
    if meta:
        date_div = meta.select_one(".date")
        if date_div:
            art.date = date_div.get_text(strip=True)
        author_div = meta.select_one(".author")
        if author_div:
            art.author = author_div.get_text(strip=True)
    return art


def _extract_code(link: str) -> str:
    m = re.search(r"/([GM]\.\d+\.A\.[A-F0-9]+)\.html", link)
    return m.group(1) if m else ""


def parse_article_page(html: str, board: str, code: str, link: str) -> Article:
    s = soup(html)
    art = Article(board=board, code=code, link=link)

    og = s.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        art.title = og["content"]
    else:
        art.title = "[內文標題已被刪除]"
    art.id = parse_article_id(link)

    art.comments = list(_parse_pushes(s.select(".push")))
    if art.comments:
        last_dt = art.comments[-1].datetime_
        if last_dt:
            art.last_push_datetime = last_dt
    return art


def _parse_pushes(nodes: Iterable[Tag]) -> Iterable[Comment]:
    for n in nodes:
        ipdate = n.select_one(".push-ipdatetime")
        if not ipdate:
            continue
        ipdate_text = ipdate.get_text(strip=True)
        if not ipdate_text:
            continue
        dt = _parse_push_datetime(ipdate_text)
        if dt is None:
            continue

        c = Comment(datetime_=dt, ip_datetime=ipdate_text)
        tag = n.select_one(".push-tag")
        if tag:
            c.tag = tag.get_text(strip=True)
        userid = n.select_one(".push-userid")
        if userid:
            c.user_id = userid.get_text(strip=True)
        content = n.select_one(".push-content")
        if content:
            c.content = content.get_text(strip=True).lstrip(":").strip()
        yield c


def _parse_push_datetime(text: str) -> datetime | None:
    m = _IPDATETIME_RE.search(text)
    if not m:
        return None
    dt_str = m.group(1).strip()
    try:
        dt = datetime.strptime(dt_str, "%m/%d %H:%M")
    except ValueError:
        try:
            dt = datetime.strptime(dt_str, "%m/%d %H:%M:%S")
        except ValueError:
            return None
    now = datetime.now(CST)
    candidate = dt.replace(year=now.year, tzinfo=CST)
    if candidate > now + timedelta(days=1):
        candidate = candidate.replace(year=now.year - 1)
    return candidate
