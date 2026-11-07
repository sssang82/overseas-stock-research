"""자료원별 수집. 각 함수는 core.collect 가 저장할 자료(dict) 목록을 돌려준다."""
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def get(url, headers=None, **kw) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": BROWSER, **(headers or {})}, timeout=25, **kw)
    r.raise_for_status()
    return r


def item(kind, source, title, url, published_at, uid, *, publisher=None, tier=None, title_ko=None, extra=None):
    """저장할 자료 한 건. 모든 자료원이 같은 열을 갖도록 여기서만 만든다."""
    return {"kind": kind, "source": source, "publisher": publisher, "tier": tier, "title": title,
            "title_ko": title_ko, "url": url, "published_at": published_at, "uid": uid[:200],
            "extra": extra or {}}


def clean(text: str | None) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
