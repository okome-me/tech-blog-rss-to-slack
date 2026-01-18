import json
import os
import time
from pathlib import Path

import feedparser
import requests


FEEDS_FILE = Path("feeds.txt")
STATE_FILE = Path("notified.json")

# 直近何秒の重複を避けるか（1時間）
DEDUP_WINDOW_SEC = 60 * 60

# 事故防止（必要なら上げる/外す）
MAX_POSTS_PER_RUN = 60
SLEEP_BETWEEN_POSTS_SEC = 0.7


def load_state(now: float) -> dict[str, float]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        pruned = {}
        cutoff = now - DEDUP_WINDOW_SEC
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


def entry_id(entry):
    link = (entry.get("link") or "").strip()
    if link:
        return link
    guid = (entry.get("id") or entry.get("guid") or "").strip()
    if guid:
        return guid
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

    new_items = []
    for feed_url in feeds:
        d = feedparser.parse(feed_url)
        source = (d.feed.get("title") or feed_url).strip()
        for e in d.entries[:20]:
            key = entry_id(e)
            # 直近1時間の重複を除外
            ts = state.get(key)
            if ts is not None and ts >= now - DEDUP_WINDOW_SEC:
                continue

            title = (e.get("title") or "(no title)").strip()
            link = (e.get("link") or "").strip()
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

    # 最後にもう一度古いものを落として保存
    state = {k: v for k, v in state.items() if v >= time.time() - DEDUP_WINDOW_SEC}
    save_state(state)
    print(f"posted={posted}, discovered_new={len(new_items)}, kept_state={len(state)}")


if __name__ == "__main__":
    main()
