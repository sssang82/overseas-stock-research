"""등록한 유튜브 채널의 새 영상 중 관심종목 이름이 들어간 것. 자막은 클라우드에서 막혀 받지 않는다."""
import re
import xml.etree.ElementTree as ET

from sources import clean, get, item, parse_date

NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}


def channel_videos(channel_id: str) -> list[dict]:
    root = ET.fromstring(get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id}).content)
    out = []
    for e in root.findall("a:entry", NS):
        out.append({"id": e.findtext("yt:videoId", "", NS), "title": clean(e.findtext("a:title", "", NS)),
                    "date": parse_date(e.findtext("a:published", "", NS)),
                    "description": clean(e.findtext("media:group/media:description", "", NS))[:1500]})
    return out


def channel_feed_title(channel_id: str) -> str | None:
    """채널 번호가 맞는지 확인하고 채널 이름을 돌려준다."""
    root = ET.fromstring(get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id}).content)
    return root.findtext("a:title", None, NS)


def patterns(ticker: str, keywords: str) -> list[re.Pattern]:
    words = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    pats = [re.compile(rf"\b{re.escape(w)}\b", re.I) for w in words]
    if len(ticker) >= 4:  # MU 처럼 짧은 티커는 다른 단어와 헷갈려서 쓰지 않는다
        pats.append(re.compile(rf"\b\$?{re.escape(ticker)}\b"))
    return pats


def match(videos: list[dict], channel_name: str, pats: list[re.Pattern]) -> list[dict]:
    rows = []
    for v in videos:
        if not any(p.search(v["title"]) or p.search(v["description"]) for p in pats):
            continue
        rows.append(item("video", "youtube", v["title"], f"https://www.youtube.com/watch?v={v['id']}", v["date"],
                         f"yt:{v['id']}", publisher=channel_name, tier="영상",
                         extra={"summary": v["description"][:600]}))
    return rows
