"""
setup_richmenu.py
LINEリッチメニューを作成・登録するワンタイムスクリプト。
ローカルで1回実行すればOK（Renderでは実行不要）。

使い方:
    pip install pillow requests python-dotenv
    python setup_richmenu.py
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

import richmenu_image

load_dotenv()

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("エラー: LINE_CHANNEL_ACCESS_TOKEN が .env に設定されていません。")

HEADERS_JSON = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}
HEADERS_IMAGE = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "image/png",
}
BASE      = "https://api.line.me/v2/bot"
DATA_BASE = "https://api-data.line.me/v2/bot"

# ---- リッチメニュー定義 ----
RICH_MENU_BODY = {
    "size": {"width": 2500, "height": 843},
    "selected": True,
    "name": "inventory_menu",
    "chatBarText": "📦 メニュー",
    "areas": [
        # 上段左: 在庫確認
        {
            "bounds": {"x": 0, "y": 0, "width": 833, "height": 421},
            "action": {"type": "message", "text": "在庫確認"},
        },
        # 上段中: 在庫を減らす
        {
            "bounds": {"x": 833, "y": 0, "width": 834, "height": 421},
            "action": {
                "type": "postback",
                "data": "action=stock_decrease",
                "displayText": "在庫を減らす",
            },
        },
        # 上段右: 在庫を増やす
        {
            "bounds": {"x": 1667, "y": 0, "width": 833, "height": 421},
            "action": {
                "type": "postback",
                "data": "action=stock_increase",
                "displayText": "在庫を増やす",
            },
        },
        # 下段左: 在庫不足確認
        {
            "bounds": {"x": 0, "y": 421, "width": 833, "height": 422},
            "action": {
                "type": "postback",
                "data": "action=low_stock_check",
                "displayText": "在庫不足確認",
            },
        },
        # 下段中: 閾値を設定
        {
            "bounds": {"x": 833, "y": 421, "width": 834, "height": 422},
            "action": {
                "type": "postback",
                "data": "action=set_threshold",
                "displayText": "閾値を設定",
            },
        },
        # 下段右: ヘルプ
        {
            "bounds": {"x": 1667, "y": 421, "width": 833, "height": 422},
            "action": {"type": "message", "text": "ヘルプ"},
        },
    ],
}


def delete_all_rich_menus():
    r = requests.get(f"{BASE}/richmenu/list", headers=HEADERS_JSON)
    r.raise_for_status()
    menus = r.json().get("richmenus", [])
    for rm in menus:
        rid = rm["richMenuId"]
        requests.delete(f"{BASE}/richmenu/{rid}", headers=HEADERS_JSON)
        print(f"  削除: {rid}")
    if not menus:
        print("  既存メニューなし")


def create_rich_menu(body: dict) -> str:
    r = requests.post(
        f"{BASE}/richmenu",
        headers=HEADERS_JSON,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )
    if not r.ok:
        sys.exit(f"メニュー作成エラー: {r.status_code} {r.text}")
    return r.json()["richMenuId"]


def upload_image(rich_menu_id: str, image_path: str):
    with open(image_path, "rb") as f:
        r = requests.post(
            f"{DATA_BASE}/richmenu/{rich_menu_id}/content",
            headers=HEADERS_IMAGE,
            data=f,
        )
    if not r.ok:
        sys.exit(f"画像アップロードエラー: {r.status_code} {r.text}")


def set_default(rich_menu_id: str):
    r = requests.post(
        f"{BASE}/richmenu/default/{rich_menu_id}",
        headers=HEADERS_JSON,
    )
    if not r.ok:
        sys.exit(f"デフォルト設定エラー: {r.status_code} {r.text}")


if __name__ == "__main__":
    print("=== LINEリッチメニュー セットアップ ===\n")

    print("[1/4] 画像生成中...")
    img_path = richmenu_image.generate()

    print("\n[2/4] 既存メニュー削除中...")
    delete_all_rich_menus()

    print("\n[3/4] メニュー作成・画像アップロード中...")
    rid = create_rich_menu(RICH_MENU_BODY)
    print(f"  作成完了: {rid}")
    upload_image(rid, img_path)
    print("  画像アップロード完了")

    print("\n[4/4] デフォルトメニューに設定中...")
    set_default(rid)

    print(f"\n✅ 完了！リッチメニューID: {rid}")
    print("   LINEアプリを再起動すると反映されます。")
