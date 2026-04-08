import json
import logging
import requests as http_requests
from flask import Flask, request, abort, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
import config
import database
import line_handler
import scheduler as sched

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
handler = WebhookHandler(config.LINE_CHANNEL_SECRET)


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/admin/setup-richmenu")
def setup_richmenu():
    """リッチメニューを登録するワンタイムエンドポイント。
    セキュリティのため LINE_CHANNEL_SECRET をクエリパラメータで渡す。
    例: /admin/setup-richmenu?secret=YOUR_CHANNEL_SECRET
    """
    secret = request.args.get("secret", "")
    if secret != config.LINE_CHANNEL_SECRET:
        abort(403)

    token = config.LINE_CHANNEL_ACCESS_TOKEN
    headers_json  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers_image = {"Authorization": f"Bearer {token}", "Content-Type": "image/png"}
    base      = "https://api.line.me/v2/bot"
    data_base = "https://api-data.line.me/v2/bot"

    # 既存メニューを削除
    existing = http_requests.get(f"{base}/richmenu/list", headers=headers_json).json()
    for rm in existing.get("richmenus", []):
        http_requests.delete(f"{base}/richmenu/{rm['richMenuId']}", headers=headers_json)

    # メニュー定義
    menu_body = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "inventory_menu",
        "chatBarText": "📦 メニュー",
        "areas": [
            {"bounds": {"x": 0,    "y": 0,   "width": 833, "height": 421},
             "action": {"type": "message", "text": "在庫確認"}},
            {"bounds": {"x": 833,  "y": 0,   "width": 834, "height": 421},
             "action": {"type": "postback", "data": "action=stock_decrease", "displayText": "在庫を減らす"}},
            {"bounds": {"x": 1667, "y": 0,   "width": 833, "height": 421},
             "action": {"type": "postback", "data": "action=stock_increase", "displayText": "在庫を増やす"}},
            {"bounds": {"x": 0,    "y": 421, "width": 833, "height": 422},
             "action": {"type": "postback", "data": "action=low_stock_check", "displayText": "在庫不足確認"}},
            {"bounds": {"x": 833,  "y": 421, "width": 834, "height": 422},
             "action": {"type": "postback", "data": "action=set_threshold", "displayText": "閾値を設定"}},
            {"bounds": {"x": 1667, "y": 421, "width": 833, "height": 422},
             "action": {"type": "message", "text": "ヘルプ"}},
        ],
    }

    # メニュー作成
    r = http_requests.post(
        f"{base}/richmenu",
        headers=headers_json,
        data=json.dumps(menu_body, ensure_ascii=False).encode("utf-8"),
    )
    if not r.ok:
        return jsonify({"step": "create_menu", "status": r.status_code, "error": r.text}), 500
    rid = r.json()["richMenuId"]

    # 画像を生成してアップロード
    import io
    from PIL import Image, ImageDraw, ImageFont

    W, H = 2500, 843
    COL_WIDTHS = [833, 834, 833]
    BUTTONS = [
        (0, 0, "在庫確認",   "全商品の在庫を表示"),
        (0, 1, "在庫を減らす", "例: りんご -5"),
        (0, 2, "在庫を増やす", "例: りんご +10"),
        (1, 0, "在庫不足確認", "閾値以下の商品を表示"),
        (1, 1, "閾値を設定",  "例: りんご 閾値 5"),
        (1, 2, "ヘルプ",     "操作方法を表示"),
    ]
    CELL_H = H // 2
    BG = ["#1A6FBF", "#1A8C4E"]

    img = Image.new("RGB", (W, H), "#1A6FBF")
    draw = ImageDraw.Draw(img)

    try:
        font_main = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 80)
        font_sub  = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 48)
    except Exception:
        font_main = ImageFont.load_default()
        font_sub  = ImageFont.load_default()

    for row, col, label, sublabel in BUTTONS:
        x = sum(COL_WIDTHS[:col])
        y = row * CELL_H
        w = COL_WIDTHS[col]
        h = CELL_H
        draw.rectangle([x, y, x+w-1, y+h-1], fill=BG[row], outline="#FFFFFF", width=3)
        cx = x + w // 2
        draw.text((cx, y + h * 0.40), label,    font=font_main, fill="#FFFFFF", anchor="mm")
        draw.text((cx, y + h * 0.68), sublabel, font=font_sub,  fill="#D0E8FF", anchor="mm")

    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)

    r2 = http_requests.post(
        f"{data_base}/richmenu/{rid}/content",
        headers=headers_image,
        data=buf.read(),
    )
    if not r2.ok:
        return jsonify({"step": "upload_image", "status": r2.status_code, "error": r2.text, "richMenuId": rid}), 500

    # デフォルト設定
    r3 = http_requests.post(f"{base}/richmenu/default/{rid}", headers=headers_json)
    if not r3.ok:
        return jsonify({"step": "set_default", "status": r3.status_code, "error": r3.text, "richMenuId": rid}), 500

    logger.info(f"リッチメニュー登録完了: {rid}")
    return jsonify({"status": "ok", "richMenuId": rid})


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("署名検証エラー")
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    # 通知先を保存（グループ > ユーザーの優先順位）
    source = event.source
    if hasattr(source, "group_id") and source.group_id:
        database.set_setting("notify_target", source.group_id)
    elif hasattr(source, "room_id") and source.room_id:
        database.set_setting("notify_target", source.room_id)
    elif hasattr(source, "user_id") and source.user_id:
        if not database.get_setting("notify_target"):
            database.set_setting("notify_target", source.user_id)

    reply_text = line_handler.handle_message(event.message.text, source)

    configuration = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


@handler.add(PostbackEvent)
def handle_postback(event: PostbackEvent):
    data = event.postback.data
    action = dict(p.split("=", 1) for p in data.split("&") if "=" in p).get("action", "")
    reply_text = line_handler.handle_postback(action)

    configuration = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


# Gunicornからimportされたときにも初期化が走るよう、モジュールレベルで実行
database.init_db()
_scheduler = sched.create_scheduler()
_scheduler.start()

if __name__ == "__main__":
    app.run(port=config.PORT, debug=False)
