"""[지금 업데이트] 처리: 종목마다 자료원을 차례로 받아 새 자료만 저장하고 결과를 기록한다."""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from core import config, db
from sources import grades, news, sec, youtube

WORKERS = 4  # 동시에 받는 종목 수


def _run_source(run_at, ticker, name, fn, is_initial) -> tuple[list[dict], dict]:
    start = time.time()
    try:
        rows = fn()
        for r in rows:
            r.update(ticker=ticker, fetched_at=run_at, is_initial=is_initial)
        log = {"status": "ok", "found": len(rows), "message": None}
    except Exception as e:  # 한 자료원이 실패해도 나머지는 계속 받는다
        rows = []
        code = getattr(getattr(e, "response", None), "status_code", None)
        log = {"status": "error", "found": 0, "message": f"{type(e).__name__}{f' {code}' if code else ''}: {e}"[:500]}
    log.update(run_at=run_at, ticker=ticker, source=name, seconds=round(time.time() - start, 1))
    return rows, log


def _mentions(rows: list[dict], pats) -> list[dict]:
    """Yahoo·Google·Nasdaq 은 종목과 무관한 시장 기사도 섞어 주므로, 제목이나 요약에 회사 이름이 있는 것만 남긴다."""
    return [r for r in rows if any(p.search(r["title"]) or p.search(r["extra"].get("summary", "")) for p in pats)]


def _update_ticker(run_at, w: dict, videos: dict) -> list[dict]:
    ticker = w["ticker"]
    is_initial = not db.has_history(ticker)
    since = run_at - timedelta(days=config.SEC_HISTORY_DAYS)
    pats = youtube.patterns(ticker, w["keywords"])
    jobs = [
        ("sec", lambda: sec.fetch(ticker, int(w["cik"]), since, db.known_uids(ticker, "sec")) if w["cik"] else []),
        ("yahoo", lambda: _mentions(news.yahoo(ticker), pats)),
        ("google", lambda: _mentions(news.google(ticker), pats)),
        ("nasdaq", lambda: _mentions(news.nasdaq(ticker), pats)),
        ("seekingalpha", lambda: news.seeking_alpha(ticker)),
        ("yfinance", lambda: grades.fetch(ticker, since)),
        ("youtube", lambda: [r for name, vids in videos.items() for r in youtube.match(vids, name, pats)]),
    ]
    logs = []
    for name, fn in jobs:
        rows, log = _run_source(run_at, ticker, name, fn, is_initial)
        log["added"] = db.insert_new(db.items, rows, ["ticker", "uid"]) if rows else 0
        logs.append(log)
    return logs


def update(watch_rows: list[dict], progress=None) -> list[dict]:
    """watch_rows: 관심종목 행 목록. progress(완료 수, 전체 수, 종목) 로 진행 상황을 알린다."""
    run_at = db.now()
    logs = []
    videos = {}  # 채널 목록은 종목마다가 아니라 한 번만 받는다
    for ch in db.list_channels(active_only=True).to_dict("records"):
        _, log = _run_source(run_at, None, f"youtube:{ch['name']}",
                             lambda c=ch: videos.setdefault(c["name"], youtube.channel_videos(c["channel_id"])), False)
        logs.append({**log, "added": 0})
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(_update_ticker, run_at, w, videos): w["ticker"] for w in watch_rows}
        for done, f in enumerate(as_completed(futures), 1):
            logs.extend(f.result())
            if progress:
                progress(done, len(futures), futures[f])
    db.insert_new(db.fetch_log, logs, ["id"])
    return logs
