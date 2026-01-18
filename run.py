import json
import os
import time
from pathlib import Path

import feedparser
import requests


FEEDS_FILE = Path("feeds.txt")
STATE_FILE = Path("notified.json")

# 無制限だと荒れるので、技術的な安全弁だけ入れます（必要なら後で外せます）
MAX_POSTS_PER_RUN = 60         # 1回の実行で最大何件流すか
SLEEP_BETWEEN_POSTS_SEC = 0.7  # Slack連投の間隔（レート制限回避）


def load_state():
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_state(seen):
    # サイズが増えすぎないよう、直近のみ保持（十分大きめ）
    keep = list(seen)[-5000:]
    STATE_FILE.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")


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
    # RSSごとに揺れるので、まずはlink優先でキーを作ります
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

    seen = load_state()

    new_items = []
    for feed_url in feeds:
        d = feedparser.parse(feed_url)
        source = (d.feed.get("title") or feed_url).strip()
        for e in d.entries[:20]:  # 各フィードから直近20件だけ見る
            key = entry_id(e)
            if key in seen:
                continue
            title = (e.get("title") or "(no title)").strip()
            link = (e.get("link") or "").strip()
            # linkが無いとSlackに流しても意味が薄いのでスキップ
            if not link:
                continue
            # publishedが取れるなら新しい順にしたいが、揺れるのでここでは単純に追加
            new_items.append((key, title, link, source))

    # 新規が大量に出た初回だけ事故りやすいので、上限で安全に流します
    to_post = new_items[:MAX_POSTS_PER_RUN]

    posted = 0
    for key, title, link, source in to_post:
        try:
            slack_post(webhook, title, link, source)
            seen.add(key)
            posted += 1
            time.sleep(SLEEP_BETWEEN_POSTS_SEC)
        except Exception as ex:
            print(f"failed: {link} ({ex})")

    save_state(seen)
    print(f"posted={posted}, discovered_new={len(new_items)}")


if __name__ == "__main__":
    main()
