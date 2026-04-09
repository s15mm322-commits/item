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
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    PostbackAction,
    MessageAction,
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


# ─────────── メッセージ → LINE SDK メッセージオブジェクト変換 ───────────
def _build_quick_reply(qr_dict: dict) -> QuickReply:
    """dict形式のクイックリプライをSDKオブジェクトに変換する。"""
    items = []
    for item in qr_dict.get("items", []):
        action_dict = item.get("action", {})
        action_type = action_dict.get("type", "")
        if action_type == "postback":
            action = PostbackAction(
                label=action_dict.get("label", ""),
                data=action_dict.get("data", ""),
                display_text=action_dict.get("displayText"),
            )
        elif action_type == "message":
            action = MessageAction(
                label=action_dict.get("label", ""),
                text=action_dict.get("text", ""),
            )
        else:
            continue
        items.append(QuickReplyItem(action=action))
    return QuickReply(items=items)


def _to_line_messages(msg_dicts: list[dict]) -> list:
    """line_handler が返す dict リストを LINE SDK メッセージオブジェクトに変換する。"""
    messages = []
    for m in msg_dicts:
        if m["type"] == "text":
            kwargs = {"text": m["text"]}
            if m.get("quickReply"):
                kwargs["quick_reply"] = _build_quick_reply(m["quickReply"])
            messages.append(TextMessage(**kwargs))
        elif m["type"] == "flex":
            messages.append(FlexMessage(
                alt_text=m["altText"],
                contents=FlexContainer.from_dict(m["contents"]),
            ))
    return messages


# ─────────── テキストメッセージ ───────────
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    source = event.source
    user_id = None

    # 通知先を保存
    if hasattr(source, "group_id") and source.group_id:
        database.set_setting("notify_target", source.group_id)
        user_id = source.group_id
    elif hasattr(source, "room_id") and source.room_id:
        database.set_setting("notify_target", source.room_id)
        user_id = source.room_id
    elif hasattr(source, "user_id") and source.user_id:
        user_id = source.user_id
        if not database.get_setting("notify_target"):
            database.set_setting("notify_target", user_id)

    if not user_id:
        return

    reply_dicts = line_handler.handle_message(event.message.text, user_id)
    messages = _to_line_messages(reply_dicts)

    configuration = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages,
            )
        )


# ─────────── ポストバック ───────────
@handler.add(PostbackEvent)
def handle_postback(event: PostbackEvent):
    source = event.source
    user_id = None

    if hasattr(source, "group_id") and source.group_id:
        user_id = source.group_id
    elif hasattr(source, "room_id") and source.room_id:
        user_id = source.room_id
    elif hasattr(source, "user_id") and source.user_id:
        user_id = source.user_id

    if not user_id:
        return

    reply_dicts = line_handler.handle_postback(event.postback.data, user_id)
    messages = _to_line_messages(reply_dicts)

    configuration = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages,
            )
        )


# Gunicornからimportされたときにも初期化が走るよう、モジュールレベルで実行
database.init_db()
_scheduler = sched.create_scheduler()
_scheduler.start()

if __name__ == "__main__":
    app.run(port=config.PORT, debug=False)
