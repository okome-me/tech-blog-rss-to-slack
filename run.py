import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import requests


FEEDS_FILE = Path("feeds.txt")
STATE_FILE = Path("notified.json")

DEDUP_WINDOW_SEC = 60 * 60  # 直近1時間
MAX_POSTS_PER_RUN = 200
SLEEP_BETWEEN_POSTS_SEC = 0.7


def normalize_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    p = urlparse(u)

    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()

    path = p.path or "/"
    # 末尾スラッシュの揺れを潰す（ルート以外）
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # フラグメントは同一扱い
    fragment = ""

    # utm系などを落とす（必要なら増やせます）
    drop_prefixes = ("utm_",)
    drop_keys = {"ref", "fbclid", "gclid"}
    q = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        lk = k.lower()
        if lk.startswith(drop_prefixes) or lk in drop_keys:
            continue
        q.append((k, v))
    query = urlencode(q, doseq=True)

    return urlunparse((scheme, netloc, path, p.params, query, fragment))


def load_state(now: float) -> dict[str, float]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        cutoff = now - DEDUP_WINDOW_SEC
        pruned = {}
        for k, v in data.items():
            try:
                ts = float(v)
            except Exception:
                continue
            if ts >= cutoff:
                pruned[k] = ts
        return pruned
    except Exception:
        return {}


def save_state(state: dict[str, float]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def read_feeds():
    if not FEEDS_FILE.exists():
        return []
    lines = [l.strip() for l in FEEDS_FILE.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def slack_post(webhook_url: str, title: str, link: str, source: str):
    text = f"{title}\n{link}\n（{source}）"
    resp = requests.post(webhook_url, json={"text": text}, timeout=20)
    resp.raise_for_status()


def entry_key(entry) -> str:
    link = normalize_url(entry.get("link") or "")
    if link:
        return link
    guid = (entry.get("id") or entry.get("guid") or "").strip()
    if guid:
        return f"guid:{guid}"
    title = (entry.get("title") or "").strip()
    return f"noid:{title}"


def main():
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        raise SystemExit("SLACK_WEBHOOK_URL is not set")

    feeds = read_feeds()
    if not feeds:
        print("feeds.txt is empty")
        return

    now = time.time()
    state = load_state(now)
    cutoff = now - DEDUP_WINDOW_SEC

    new_items = []
    for feed_url in feeds:
        d = feedparser.parse(feed_url)
        source = (d.feed.get("title") or feed_url).strip()
        for e in d.entries[:30]:
            key = entry_key(e)
            if not key:
                continue
            ts = state.get(key)
            if ts is not None and ts >= cutoff:
                continue

            title = (e.get("title") or "(no title)").strip()
            link = normalize_url(e.get("link") or "")
            if not link:
                continue
            new_items.append((key, title, link, source))

    to_post = new_items[:MAX_POSTS_PER_RUN]

    posted = 0
    for key, title, link, source in to_post:
        try:
            slack_post(webhook, title, link, source)
            state[key] = time.time()
            posted += 1
            time.sleep(SLEEP_BETWEEN_POSTS_SEC)
        except Exception as ex:
            print(f"failed: {link} ({ex})")

    state = {k: v for k, v in state.items() if v >= time.time() - DEDUP_WINDOW_SEC}
    save_state(state)
    print(f"posted={posted}, discovered_new={len(new_items)}, kept_state={len(state)}")


if __name__ == "__main__":
    main()
