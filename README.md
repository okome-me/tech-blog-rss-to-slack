# tech-blog-rss-to-slack

国内テックブログのRSSを定期取得し、新着記事をSlackの固定チャンネルへ1記事ずつ自動投稿する仕組みです。  
サーバを用意せず、GitHub Actionsの無料枠だけで動作します。

## できること

- 複数（30サイト程度）のテックブログRSSを監視
- 新着記事のみを検出し、重複なくSlackへ投稿
- 1記事ごとに即時投稿
- サーバレス（GitHub Actionsのみ）
- 無料枠で運用可能

## 全体構成

GitHub Actions が一定間隔で実行され、RSSを取得します。  
未通知の記事だけを判定し、Slack Incoming Webhook を使って投稿します。  
通知済みの記事URLはリポジトリ内の `notified.json` に保存されます。

## 前提条件

- GitHubアカウント
- Slackワークスペースの管理権限（Incoming Webhook作成用）

## セットアップ手順

1. このリポジトリを作成する  
2. SlackでIncoming Webhookを作成し、通知したいチャンネルに紐づける  
3. Webhook URLをGitHubリポジトリのSecretsに  
   `SLACK_WEBHOOK_URL` という名前で登録する  
4. `feeds.txt` に取得したいテックブログのRSS URLを1行ずつ記載する  
5. GitHub Actionsを有効化する  

以上で、20分ごとに自動で新着記事がSlackへ投稿されます。

## ファイル構成

- `feeds.txt`  
  監視対象のRSS/Atom URL一覧。1行に1URL。

- `run.py`  
  RSS取得、重複判定、Slack投稿を行うメインスクリプト。

- `notified.json`  
  通知済み記事の識別子を保存するファイル。  
  GitHub Actions実行時に自動更新されます。

- `.github/workflows/rss_to_slack.yml`  
  定期実行用のGitHub Actions設定。

## 投稿形式

Slackには以下の形式で投稿されます。

```
記事タイトル
記事URL
（ブログ名）
```

## 実行間隔の変更

`.github/workflows/rss_to_slack.yml` の `cron` を変更してください。

例：10分ごと

```
*/10 * * * *
```

## 注意事項

- 初回実行時は過去記事がまとめて検出される可能性があります
- Slackの連投制限回避のため、投稿間に短い待ち時間を入れています
- RSSが無いサイトには対応していません（必要な場合は拡張してください）

## 想定用途

- 社内の技術キャッチアップ用チャンネル
- 技術広報・採用チームの情報収集
- 個人の学習用Slackチャンネル
