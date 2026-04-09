"""
LINE メッセージ / ポストバック処理。
クイックリプライとフレックスメッセージを使った対話的な在庫管理フローを提供する。
"""
import database

# ─────────────────────────────────────────────
#  定数
# ─────────────────────────────────────────────
FLOW_INCREASE = "increase"
FLOW_DECREASE = "decrease"
FLOW_THRESHOLD = "threshold"

STEP_CATEGORY = "category"
STEP_PRODUCT  = "product"
STEP_QUANTITY  = "quantity"
STEP_DIRECT_INPUT = "direct_input"
STEP_CONFIRM   = "confirm"


# ─────────────────────────────────────────────
#  メッセージハンドラ（テキスト入力）
# ─────────────────────────────────────────────
def handle_message(text: str, user_id: str) -> list[dict]:
    """
    テキストメッセージを処理し、返信メッセージオブジェクトのリストを返す。
    各dictは {"type": "text", "text": ..., "quickReply": ...}
    または {"type": "flex", ...} 形式。
    """
    text = text.strip()
    session = database.get_session(user_id)

    # ── 直接入力モード ──
    if session and session["step"] == STEP_DIRECT_INPUT:
        return _handle_direct_input(text, user_id, session)

    # ── セッション中のテキスト入力（クイックリプライの代わりにテキスト送信した場合） ──
    # セッション中でもリッチメニューからのメッセージは優先処理
    if text == "在庫確認":
        database.clear_session(user_id)
        return [_build_inventory_flex()]
    if text == "ヘルプ":
        database.clear_session(user_id)
        return [_build_manual_flex()]

    # ── セッション外のフリーテキスト ──
    if not session:
        return [_build_text("メニューから操作を選択してください。")]

    return [_build_text("メニューまたはクイックリプライから操作を選択してください。")]


# ─────────────────────────────────────────────
#  ポストバックハンドラ
# ─────────────────────────────────────────────
def handle_postback(data: str, user_id: str) -> list[dict]:
    """
    ポストバックデータを処理し、返信メッセージオブジェクトのリストを返す。
    """
    params = dict(p.split("=", 1) for p in data.split("&") if "=" in p)
    action = params.get("action", "")

    # ── リッチメニューからのアクション ──
    if action == "start_increase":
        database.set_session(user_id, FLOW_INCREASE, STEP_CATEGORY)
        return [_build_category_select("➕ 入庫：カテゴリを選んでください")]

    if action == "start_decrease":
        database.set_session(user_id, FLOW_DECREASE, STEP_CATEGORY)
        return [_build_category_select("➖ 出庫：カテゴリを選んでください")]

    if action == "check_inventory":
        database.clear_session(user_id)
        return [_build_inventory_flex()]

    if action == "check_low_stock":
        database.clear_session(user_id)
        return [_build_low_stock_flex()]

    if action == "start_threshold":
        database.set_session(user_id, FLOW_THRESHOLD, STEP_CATEGORY)
        return [_build_category_select("🔔 通知設定：カテゴリを選んでください")]

    if action == "show_manual":
        database.clear_session(user_id)
        return [_build_manual_flex()]

    # ── フロー中のアクション ──
    if action == "select_category":
        return _handle_select_category(params, user_id)

    if action == "select_product":
        return _handle_select_product(params, user_id)

    if action == "select_quantity":
        return _handle_select_quantity(params, user_id)

    if action == "direct_input":
        return _handle_direct_input_start(user_id)

    if action == "confirm":
        return _handle_confirm(user_id)

    if action == "cancel" or action == "back_to_menu":
        database.clear_session(user_id)
        return [_build_text("キャンセルしました。メニューから操作を選んでください。")]

    if action == "back_to_category":
        return _handle_back_to_category(user_id)

    if action == "back_to_product":
        return _handle_back_to_product(user_id)

    if action == "back_to_quantity":
        return _handle_back_to_quantity(user_id)

    return [_build_text("不明な操作です。メニューからもう一度お試しください。")]


# ─────────────────────────────────────────────
#  フロー処理: カテゴリ選択
# ─────────────────────────────────────────────
def _handle_select_category(params: dict, user_id: str) -> list[dict]:
    category = params.get("category", "")
    session = database.get_session(user_id)
    if not session:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    database.set_session(
        user_id, session["flow"], STEP_PRODUCT,
        category=category,
    )

    flow = session["flow"]
    if flow == FLOW_INCREASE:
        label = f"➕ 入庫 > {category}：商品を選んでください"
    elif flow == FLOW_DECREASE:
        label = f"➖ 出庫 > {category}：商品を選んでください"
    else:
        label = f"🔔 通知設定 > {category}：商品を選んでください"

    return [_build_product_select(category, label)]


# ─────────────────────────────────────────────
#  フロー処理: 商品選択
# ─────────────────────────────────────────────
def _handle_select_product(params: dict, user_id: str) -> list[dict]:
    product = params.get("product", "")
    session = database.get_session(user_id)
    if not session:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    flow = session["flow"]

    # 閾値設定フローの場合：閾値選択に進む
    if flow == FLOW_THRESHOLD:
        database.set_session(
            user_id, flow, STEP_QUANTITY,
            category=session["category"], product=product,
        )
        return [_build_threshold_select(product)]

    # 入庫・出庫フロー：数量選択に進む
    database.set_session(
        user_id, flow, STEP_QUANTITY,
        category=session["category"], product=product,
    )
    return [_build_quantity_select(product, flow)]


# ─────────────────────────────────────────────
#  フロー処理: 数量選択
# ─────────────────────────────────────────────
def _handle_select_quantity(params: dict, user_id: str) -> list[dict]:
    qty = int(params.get("qty", "0"))
    session = database.get_session(user_id)
    if not session:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    flow = session["flow"]
    product = session["product"]

    # 閾値設定フロー
    if flow == FLOW_THRESHOLD:
        database.set_threshold(product, qty)
        database.clear_session(user_id)
        return [_build_text(f"✅ {product} の通知閾値を {qty} に設定しました。")]

    # 入庫・出庫フロー → 確認画面へ
    database.set_session(
        user_id, flow, STEP_CONFIRM,
        category=session["category"], product=product, quantity=qty,
    )
    return [_build_confirm_flex(user_id, session, qty)]


def _handle_direct_input_start(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    database.set_session(
        user_id, session["flow"], STEP_DIRECT_INPUT,
        category=session["category"], product=session["product"],
    )
    return [_build_text("数量を入力してください（例: 15）")]


def _handle_direct_input(text: str, user_id: str, session: dict) -> list[dict]:
    try:
        qty = int(text)
    except ValueError:
        return [_build_text("数値を入力してください（例: 15）")]

    if qty <= 0:
        return [_build_text("1以上の数値を入力してください。")]

    flow = session["flow"]

    # 閾値設定フロー
    if flow == FLOW_THRESHOLD:
        database.set_threshold(session["product"], qty)
        database.clear_session(user_id)
        return [_build_text(f"✅ {session['product']} の通知閾値を {qty} に設定しました。")]

    # 入庫・出庫フロー → 確認画面へ
    actual_qty = qty if flow == FLOW_INCREASE else -qty
    database.set_session(
        user_id, flow, STEP_CONFIRM,
        category=session["category"], product=session["product"], quantity=actual_qty,
    )
    return [_build_confirm_flex(user_id, session, actual_qty)]


# ─────────────────────────────────────────────
#  フロー処理: 確定
# ─────────────────────────────────────────────
def _handle_confirm(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session or session["step"] != STEP_CONFIRM:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    product = session["product"]
    qty = session["quantity"]
    new_qty = database.update_quantity(product, qty)
    database.clear_session(user_id)

    return [_build_completion_flex(product, qty, new_qty)]


# ─────────────────────────────────────────────
#  フロー処理: 戻る
# ─────────────────────────────────────────────
def _handle_back_to_category(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    flow = session["flow"]
    database.set_session(user_id, flow, STEP_CATEGORY)

    if flow == FLOW_INCREASE:
        label = "➕ 入庫：カテゴリを選んでください"
    elif flow == FLOW_DECREASE:
        label = "➖ 出庫：カテゴリを選んでください"
    else:
        label = "🔔 通知設定：カテゴリを選んでください"

    return [_build_category_select(label)]


def _handle_back_to_product(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session or not session["category"]:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    flow = session["flow"]
    category = session["category"]
    database.set_session(user_id, flow, STEP_PRODUCT, category=category)

    if flow == FLOW_INCREASE:
        label = f"➕ 入庫 > {category}：商品を選んでください"
    elif flow == FLOW_DECREASE:
        label = f"➖ 出庫 > {category}：商品を選んでください"
    else:
        label = f"🔔 通知設定 > {category}：商品を選んでください"

    return [_build_product_select(category, label)]


def _handle_back_to_quantity(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session or not session["product"]:
        return [_build_text("セッションが切れました。メニューからやり直してください。")]

    flow = session["flow"]
    database.set_session(
        user_id, flow, STEP_QUANTITY,
        category=session["category"], product=session["product"],
    )

    if flow == FLOW_THRESHOLD:
        return [_build_threshold_select(session["product"])]
    return [_build_quantity_select(session["product"], flow)]


# ─────────────────────────────────────────────
#  メッセージビルダー: テキスト
# ─────────────────────────────────────────────
def _build_text(text: str, quick_reply: dict = None) -> dict:
    msg = {"type": "text", "text": text}
    if quick_reply:
        msg["quickReply"] = quick_reply
    return msg


# ─────────────────────────────────────────────
#  メッセージビルダー: クイックリプライ
# ─────────────────────────────────────────────
def _build_category_select(label: str) -> dict:
    items = []
    for cat in database.CATEGORY_ORDER:
        icon = database.CATEGORY_ICONS.get(cat, "📦")
        items.append({
            "type": "action",
            "imageUrl": None,
            "action": {
                "type": "postback",
                "label": f"{icon} {cat}",
                "data": f"action=select_category&category={cat}",
                "displayText": f"{icon} {cat}",
            },
        })
    # キャンセルボタン
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "← キャンセル",
            "data": "action=cancel",
            "displayText": "キャンセル",
        },
    })
    return _build_text(label, {"items": items})


def _build_product_select(category: str, label: str) -> dict:
    products = database.CATEGORIES.get(category, [])
    items = []
    for p in products:
        items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": p,
                "data": f"action=select_product&product={p}",
                "displayText": p,
            },
        })
    # 戻るボタン
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "← 戻る",
            "data": "action=back_to_category",
            "displayText": "戻る",
        },
    })
    return _build_text(label, {"items": items})


def _build_quantity_select(product: str, flow: str) -> dict:
    if flow == FLOW_INCREASE:
        quantities = [1, 2, 3, 5, 10]
        label = f"➕ {product}：数量を選んでください"
    else:
        quantities = [-1, -2, -3, -5, -10]
        label = f"➖ {product}：数量を選んでください"

    items = []
    for q in quantities:
        sign = "+" if q > 0 else ""
        items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"{sign}{q}",
                "data": f"action=select_quantity&qty={q}",
                "displayText": f"{sign}{q}",
            },
        })
    # 直接入力ボタン
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "直接入力",
            "data": "action=direct_input",
            "displayText": "直接入力",
        },
    })
    # 戻るボタン
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "← 戻る",
            "data": "action=back_to_product",
            "displayText": "戻る",
        },
    })
    return _build_text(label, {"items": items})


def _build_threshold_select(product: str) -> dict:
    thresholds = [1, 2, 3, 5, 10]
    label = f"🔔 {product}：通知閾値を選んでください"

    items = []
    for t in thresholds:
        items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"{t}",
                "data": f"action=select_quantity&qty={t}",
                "displayText": f"閾値: {t}",
            },
        })
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "直接入力",
            "data": "action=direct_input",
            "displayText": "直接入力",
        },
    })
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "← 戻る",
            "data": "action=back_to_product",
            "displayText": "戻る",
        },
    })
    return _build_text(label, {"items": items})


# ─────────────────────────────────────────────
#  メッセージビルダー: フレックスメッセージ
# ─────────────────────────────────────────────
def _build_confirm_flex(user_id: str, session: dict, qty: int) -> dict:
    product = session["product"]
    flow = session["flow"]
    current_qty = database.get_quantity(product)
    new_qty = current_qty + qty

    flow_label = "入庫" if flow == FLOW_INCREASE else "出庫"
    flow_color = "#1A6FBF" if flow == FLOW_INCREASE else "#DC3545"
    sign = "+" if qty > 0 else ""

    return {
        "type": "flex",
        "altText": f"{flow_label}確認: {product} {sign}{qty}",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": flow_color,
                "contents": [{
                    "type": "text",
                    "text": f"📋 {flow_label}確認",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "lg",
                }],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    _flex_kv("商品名", product),
                    _flex_kv("数量", f"{sign}{qty}"),
                    {
                        "type": "separator",
                        "margin": "md",
                    },
                    _flex_kv("変更前", f"{current_qty} 個"),
                    _flex_kv("変更後", f"{new_qty} 個"),
                ],
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "md",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#06C755",
                        "action": {
                            "type": "postback",
                            "label": "✅ 確定",
                            "data": "action=confirm",
                            "displayText": "確定",
                        },
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "postback",
                            "label": "❌ キャンセル",
                            "data": "action=cancel",
                            "displayText": "キャンセル",
                        },
                    },
                ],
            },
        },
    }


def _build_completion_flex(product: str, delta: int, new_qty: int) -> dict:
    sign = "+" if delta > 0 else ""
    flow_label = "入庫" if delta > 0 else "出庫"

    body_contents = [
        {
            "type": "text",
            "text": f"✅ {flow_label}完了",
            "weight": "bold",
            "size": "xl",
            "color": "#06C755",
        },
        {"type": "separator", "margin": "md"},
        _flex_kv("商品名", product),
        _flex_kv("変更数量", f"{sign}{delta}"),
        _flex_kv("現在庫数", f"{new_qty} 個"),
    ]

    # 閾値チェック
    item = database.get_item(product)
    if item and new_qty <= item["threshold"]:
        body_contents.append({"type": "separator", "margin": "md"})
        body_contents.append({
            "type": "text",
            "text": f"⚠️ 在庫が閾値（{item['threshold']}）以下です！",
            "color": "#DC3545",
            "weight": "bold",
            "size": "sm",
            "margin": "md",
            "wrap": True,
        })

    return {
        "type": "flex",
        "altText": f"{flow_label}完了: {product} → {new_qty}個",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": body_contents,
            },
        },
    }


def _build_inventory_flex() -> dict:
    items = database.get_all_inventory()
    if not items:
        return _build_text("在庫データがありません。")

    # カテゴリ別に分類
    categorized = {}
    uncategorized = []
    all_products = {}
    for cat, products in database.CATEGORIES.items():
        for p in products:
            all_products[p] = cat

    for item in items:
        cat = all_products.get(item["name"])
        if cat:
            categorized.setdefault(cat, []).append(item)
        else:
            uncategorized.append(item)

    body_contents = [
        {
            "type": "text",
            "text": "📦 在庫一覧",
            "weight": "bold",
            "size": "xl",
            "color": "#1A6FBF",
        },
        {"type": "separator", "margin": "md"},
    ]

    for cat in database.CATEGORY_ORDER:
        cat_items = categorized.get(cat, [])
        if not cat_items:
            continue
        icon = database.CATEGORY_ICONS.get(cat, "📦")
        body_contents.append({
            "type": "text",
            "text": f"{icon} {cat}",
            "weight": "bold",
            "size": "sm",
            "color": "#555555",
            "margin": "lg",
        })
        for item in cat_items:
            warn = " ⚠️" if item["quantity"] <= item["threshold"] else ""
            body_contents.append({
                "type": "text",
                "text": f"  {item['name']}: {item['quantity']}個{warn}",
                "size": "sm",
                "color": "#DC3545" if item["quantity"] <= item["threshold"] else "#333333",
                "wrap": True,
            })

    # 未分類
    if uncategorized:
        body_contents.append({
            "type": "text", "text": "📦 その他",
            "weight": "bold", "size": "sm", "color": "#555555", "margin": "lg",
        })
        for item in uncategorized:
            warn = " ⚠️" if item["quantity"] <= item["threshold"] else ""
            body_contents.append({
                "type": "text",
                "text": f"  {item['name']}: {item['quantity']}個{warn}",
                "size": "sm",
                "color": "#DC3545" if item["quantity"] <= item["threshold"] else "#333333",
                "wrap": True,
            })

    return {
        "type": "flex",
        "altText": "📦 在庫一覧",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": body_contents,
            },
        },
    }


def _build_low_stock_flex() -> dict:
    items = database.get_low_stock()
    if not items:
        return _build_text("✅ 在庫不足の商品はありません。")

    body_contents = [
        {
            "type": "text",
            "text": "⚠️ 在庫不足一覧",
            "weight": "bold",
            "size": "xl",
            "color": "#DC3545",
        },
        {"type": "separator", "margin": "md"},
    ]
    for item in items:
        body_contents.append(
            _flex_kv(item["name"], f"{item['quantity']}個（閾値: {item['threshold']}）")
        )

    body_contents.append({"type": "separator", "margin": "md"})
    body_contents.append({
        "type": "text",
        "text": "補充をご確認ください。",
        "size": "sm",
        "color": "#999999",
        "margin": "md",
    })

    return {
        "type": "flex",
        "altText": "⚠️ 在庫不足一覧",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": body_contents,
            },
        },
    }


def _build_manual_flex() -> dict:
    return {
        "type": "flex",
        "altText": "📖 操作マニュアル",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1A6FBF",
                "contents": [{
                    "type": "text",
                    "text": "📖 操作マニュアル",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "lg",
                }],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "lg",
                "contents": [
                    _manual_section("➕ 在庫を増やす",
                                    "メニューから「在庫を増やす」をタップ\n→ カテゴリ → 商品 → 数量 → 確定"),
                    _manual_section("➖ 在庫を減らす",
                                    "メニューから「在庫を減らす」をタップ\n→ カテゴリ → 商品 → 数量 → 確定"),
                    _manual_section("📋 在庫確認",
                                    "メニューから「在庫確認」をタップ\n→ 全商品の在庫をカテゴリ別に表示"),
                    _manual_section("⚠️ 在庫不足確認",
                                    "メニューから「在庫不足確認」をタップ\n→ 閾値以下の商品を一覧表示"),
                    _manual_section("🔔 在庫通知設定",
                                    "メニューから「在庫通知設定」をタップ\n→ 商品ごとの通知閾値を変更"),
                    _manual_section("⏰ 毎朝7時通知",
                                    "閾値以下の在庫がある場合\n自動でアラートが届きます"),
                ],
            },
        },
    }


# ─────────────────────────────────────────────
#  ユーティリティ
# ─────────────────────────────────────────────
def _flex_kv(key: str, value: str) -> dict:
    return {
        "type": "box",
        "layout": "horizontal",
        "margin": "md",
        "contents": [
            {"type": "text", "text": key, "size": "sm", "color": "#999999", "flex": 0, "wrap": True},
            {"type": "text", "text": value, "size": "sm", "color": "#333333", "align": "end", "wrap": True},
        ],
    }


def _manual_section(title: str, body: str) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "text", "text": title, "weight": "bold", "size": "sm", "color": "#1A6FBF"},
            {"type": "text", "text": body, "size": "xs", "color": "#666666", "wrap": True, "margin": "sm"},
        ],
    }


def format_low_stock_alert(items: list[dict]) -> str:
    """スケジューラからの呼び出し用（テキスト形式）"""
    lines = ["⚠️ 在庫不足アラート", "─────────────────"]
    for item in items:
        lines.append(f"{item['name']}: {item['quantity']}個（閾値: {item['threshold']}）")
    lines.append("─────────────────\n補充をご確認ください。")
    return "\n".join(lines)
