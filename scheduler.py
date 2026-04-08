import logging
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)
import config
import database
import line_handler

logger = logging.getLogger(__name__)
JST = pytz.timezone("Asia/Tokyo")


def send_low_stock_alert():
    """閾値以下の商品をLINEにプッシュ通知する"""
    notify_target = database.get_setting("notify_target")
    if not notify_target:
        logger.info("通知先が未設定のためスキップします。")
        return

    items = database.get_low_stock()
    if not items:
        logger.info("在庫不足の商品はありません。")
        return

    message_text = line_handler.format_low_stock_alert(items)
    configuration = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.push_message(
            PushMessageRequest(
                to=notify_target,
                messages=[TextMessage(text=message_text)],
            )
        )
    logger.info(f"低在庫アラートを送信しました: {len(items)} 件")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=JST)
    scheduler.add_job(
        func=send_low_stock_alert,
        trigger=CronTrigger(hour=config.ALERT_HOUR, minute=0, timezone=JST),
        id="daily_low_stock_alert",
        replace_existing=True,
    )
    return scheduler
