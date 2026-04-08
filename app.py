import logging
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, SourceUser, SourceGroup, SourceRoom
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


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    # 通知先を保存（グループ > ユーザーの優先順位）
    source = event.source
    if isinstance(source, SourceGroup):
        database.set_setting("notify_target", source.group_id)
    elif isinstance(source, SourceRoom):
        database.set_setting("notify_target", source.room_id)
    elif isinstance(source, SourceUser):
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


# Gunicornからimportされたときにも初期化が走るよう、モジュールレベルで実行
database.init_db()
_scheduler = sched.create_scheduler()
_scheduler.start()

if __name__ == "__main__":
    app.run(port=config.PORT, debug=False)
