# 在庫管理システム（LINE Bot）

LINE Messaging API + SQLite + Flask による在庫管理ボット。

## 機能

| メッセージ例 | 動作 |
|---|---|
| `りんご -5` | りんごの在庫を 5 減らす |
| `バナナ +10` | バナナの在庫を 10 増やす |
| `牛乳 3` | 牛乳の在庫を 3 増やす（+省略可） |
| `りんご 閾値 3` | りんごの閾値を 3 に設定 |
| `在庫確認` | 全商品の在庫一覧を返信 |

毎朝 7:00（JST）に閾値以下の商品をプッシュ通知します。

---

## セットアップ

### 1. LINE Developers でチャンネル作成

1. [LINE Developers](https://developers.line.biz/) でプロバイダーを作成
2. **Messaging API** チャンネルを作成
3. 以下をメモしておく
   - チャンネルシークレット
   - チャンネルアクセストークン（長期）

### 2. ローカル開発

```bash
git clone <このリポジトリ>
cd 在庫管理システム

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# .env を編集して LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN を設定

python app.py
```

### 3. Render へデプロイ

#### 方法 A: render.yaml を使う（推奨）

1. GitHub にリポジトリをプッシュ
2. [Render ダッシュボード](https://dashboard.render.com/) → **New > Blueprint**
3. リポジトリを選択すると `render.yaml` が自動検出される
4. 環境変数 `LINE_CHANNEL_SECRET` と `LINE_CHANNEL_ACCESS_TOKEN` を入力してデプロイ

#### 方法 B: 手動設定

1. **New > Web Service** → GitHub リポジトリを接続
2. 設定:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --workers 1 --bind 0.0.0.0:$PORT --timeout 120`
3. **Environment Variables** に以下を追加:
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `DATABASE_PATH` = `/data/inventory.db`
4. **Disks** タブ → マウントパス `/data`、サイズ 1GB で追加

### 4. Webhook URL を設定

Render のデプロイ完了後、発行された URL を LINE Developers のチャンネル設定に登録する。

```
https://<your-app>.onrender.com/webhook
```

**Webhook の利用** を ON に設定。

---

## 注意事項

### Render 無料プランのスリープ問題

無料プランでは 15 分間リクエストがないとサービスがスリープし、APScheduler が停止します。
毎朝 7 時の通知を確実に届けるには以下のいずれかを選択してください。

- **Render の有料プランを使用**（推奨）
- **外部 cron サービスで `/health` を定期 ping**
  例: [cron-job.org](https://cron-job.org/) で 10 分ごとに `https://<your-app>.onrender.com/health` を叩く

### SQLite の永続化

`render.yaml` に Disk の設定があるため、デプロイしても `/data/inventory.db` は消えません。
無料プランでは Disk が使えないため、デプロイのたびにデータがリセットされます。

### ワーカー数

APScheduler の重複実行防止のため、Gunicorn は必ず `--workers 1` で起動してください。
