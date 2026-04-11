"""
LINE メッセージ / ポストバック処理。
クイックリプライとフレックスメッセージを使った対話的な在庫管理フローを提供する。
"""
import random
import re
import database

# ─────────────────────────────────────────────
#  定数
# ─────────────────────────────────────────────
FLOW_INCREASE = "increase"
FLOW_DECREASE = "decrease"
FLOW_THRESHOLD = "threshold"
FLOW_ADD_PRODUCT = "add_product"
FLOW_DELETE_PRODUCT = "delete_product"
FLOW_RENAME_PRODUCT = "rename_product"

STEP_CATEGORY = "category"
STEP_PRODUCT  = "product"
STEP_QUANTITY  = "quantity"
STEP_DIRECT_INPUT = "direct_input"
STEP_CONFIRM   = "confirm"
STEP_SETTINGS_MENU = "settings_menu"
STEP_INPUT_NAME = "input_name"
STEP_INPUT_NEW_NAME = "input_new_name"

# テキスト入力での在庫増減パターン: "商品名 数量" (例: りんご -5, りんご +10, りんご 3)
QUANTITY_RE = re.compile(r"^(.+?)\s+([\+\-]?\d+)$")

# りっくん関係の感情メッセージ
RIKKUN_MESSAGES = [
    "りっくんのおせわ、がんばるでしゅ！💪👶",
    "りっくんだいしゅき～！🥰",
    "りっくんのために、えいえいおー！✨",
    "りっくんのもの、ちゃんとかんりしゅるでしゅ！📦",
    "りっくん、まかしぇて～！😊",
    "りっくんのぶん、わしゅれないでしゅよ！🍼",
]


def _rikkun_msg(category: str) -> str:
    """りっくん関係カテゴリの場合、感情メッセージを返す"""
    if category == "りっくん関係":
        return "\n" + random.choice(RIKKUN_MESSAGES)
    return ""


# ─────────────────────────────────────────────
#  メッセージハンドラ（テキスト入力）
# ─────────────────────────────────────────────
def handle_message(text: str, user_id: str) -> list[dict]:
    """
    テキストメッセージを処理し、返信メッセージオブジェクトのリストを返す。
    """
    text = text.strip()
    session = database.get_session(user_id)

    # ── 直接入力モード ──
    if session and session["step"] == STEP_DIRECT_INPUT:
        return _handle_direct_input(text, user_id, session)

    # ── 商品名入力モード（追加/リネーム） ──
    if session and session["step"] == STEP_INPUT_NAME:
        return _handle_input_name(text, user_id, session)

    # ── 新名称入力モード（リネーム） ──
    if session and session["step"] == STEP_INPUT_NEW_NAME:
        return _handle_input_new_name(text, user_id, session)

    # ── リッチメニューからのメッセージは常に優先 ──
    if text == "在庫確認":
        database.clear_session(user_id)
        return [_build_inventory_flex()]
    if text == "ヘルプ":
        database.clear_session(user_id)
        return [_build_manual_flex()]

    # ── テキストメッセージでの在庫増減 ──
    m = QUANTITY_RE.match(text)
    if m:
        name, delta = m.group(1).strip(), int(m.group(2))
        # 商品マスタに存在する場合のみ処理
        item = database.get_item(name)
        if item:
            database.clear_session(user_id)
            new_qty = database.update_quantity(name, delta)
            return [_build_completion_flex(name, delta, new_qty)]
        else:
            return [_build_text(
                f"「{name}」はおしょうひんにないでしゅ…😢\n"
                "ざいこせっていから追加してほしいでしゅ！"
            )]

    # ── セッション外のフリーテキスト ──
    return [_build_text("メニューからえらんでほしいでしゅ！🍼\nテキストでざいこふやしたりへらしたりもできるでしゅ：商品名 数量（れい: マスク -3）")]


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
        return [_build_category_select("➕ にゅうこ：カテゴリをえらぶでしゅ！")]

    if action == "start_decrease":
        database.set_session(user_id, FLOW_DECREASE, STEP_CATEGORY)
        return [_build_category_select("➖ しゅっこ：カテゴリをえらぶでしゅ！")]

    if action == "check_inventory":
        database.clear_session(user_id)
        return [_build_inventory_flex()]

    if action == "check_low_stock":
        database.clear_session(user_id)
        return [_build_low_stock_flex()]

    if action == "start_settings":
        database.set_session(user_id, "settings", STEP_SETTINGS_MENU)
        return [_build_settings_menu()]

    if action == "show_manual":
        database.clear_session(user_id)
        return [_build_manual_flex()]

    if action == "start_restock":
        product = params.get("product", "")
        if not product:
            return [_build_text("おしょうひんがわかんないでしゅ…😢")]
        # カテゴリは補充フローでは不要なのでNoneのままセッションを設定
        database.set_session(user_id, FLOW_INCREASE, STEP_QUANTITY, product=product)
        return [_build_quantity_select(product, FLOW_INCREASE)]

    # ── 在庫設定サブメニュー ──
    if action == "settings_add":
        database.set_session(user_id, FLOW_ADD_PRODUCT, STEP_CATEGORY)
        return [_build_category_select("➕ ついかするカテゴリをえらぶでしゅ！")]

    if action == "settings_delete":
        database.set_session(user_id, FLOW_DELETE_PRODUCT, STEP_CATEGORY)
        return [_build_category_select("🗑️ さくじょするカテゴリをえらぶでしゅ！")]

    if action == "settings_rename":
        database.set_session(user_id, FLOW_RENAME_PRODUCT, STEP_CATEGORY)
        return [_build_category_select("✏️ おなまえかえるカテゴリをえらぶでしゅ！")]

    if action == "settings_threshold":
        database.set_session(user_id, FLOW_THRESHOLD, STEP_CATEGORY)
        return [_build_category_select("🔔 しきいちかえるカテゴリをえらぶでしゅ！")]

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

    if action == "confirm_delete":
        return _handle_confirm_delete(user_id)

    if action == "cancel" or action == "back_to_menu":
        database.clear_session(user_id)
        return [_build_text("やめたでしゅ！🙌 メニューからまたえらんでほしいでしゅ！")]

    if action == "back_to_category":
        return _handle_back_to_category(user_id)

    if action == "back_to_product":
        return _handle_back_to_product(user_id)

    if action == "back_to_quantity":
        return _handle_back_to_quantity(user_id)

    if action == "back_to_settings":
        database.set_session(user_id, "settings", STEP_SETTINGS_MENU)
        return [_build_settings_menu()]

    return [_build_text("なにかわかんないでしゅ…😵 メニューからもういっかいやってみてでしゅ！")]


# ─────────────────────────────────────────────
#  在庫設定メニュー
# ─────────────────────────────────────────────
def _build_settings_menu() -> dict:
    items = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": "➕ ざいこついか",
                "data": "action=settings_add",
                "displayText": "➕ ざいこついか",
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": "🗑️ ざいこさくじょ",
                "data": "action=settings_delete",
                "displayText": "🗑️ ざいこさくじょ",
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": "✏️ おなまえへんこう",
                "data": "action=settings_rename",
                "displayText": "✏️ おなまえへんこう",
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": "🔔 しきいちへんこう",
                "data": "action=settings_threshold",
                "displayText": "🔔 しきいちへんこう",
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": "← やめる",
                "data": "action=cancel",
                "displayText": "やめる",
            },
        },
    ]
    return _build_text("⚙️ ざいこせってい：なにしゅる～？🍼", {"items": items})


# ─────────────────────────────────────────────
#  フロー処理: カテゴリ選択
# ─────────────────────────────────────────────
def _handle_select_category(params: dict, user_id: str) -> list[dict]:
    category = params.get("category", "")
    session = database.get_session(user_id)
    if not session:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    flow = session["flow"]

    # 在庫追加フロー → 商品名入力へ
    if flow == FLOW_ADD_PRODUCT:
        database.set_session(user_id, flow, STEP_INPUT_NAME, category=category)
        msg = f"➕ {category} > ついかするおしょうひんのなまえをいれてでしゅ！"
        msg += _rikkun_msg(category)
        return [_build_text(msg)]

    database.set_session(
        user_id, flow, STEP_PRODUCT,
        category=category,
    )

    flow_labels = {
        FLOW_INCREASE: "➕ にゅうこ",
        FLOW_DECREASE: "➖ しゅっこ",
        FLOW_THRESHOLD: "🔔 しきいちへんこう",
        FLOW_DELETE_PRODUCT: "🗑️ さくじょ",
        FLOW_RENAME_PRODUCT: "✏️ おなまえへんこう",
    }
    prefix = flow_labels.get(flow, "")
    label = f"{prefix} > {category}：おしょうひんをえらぶでしゅ！"
    label += _rikkun_msg(category)

    return [_build_product_select(category, label)]


# ─────────────────────────────────────────────
#  フロー処理: 商品選択
# ─────────────────────────────────────────────
def _handle_select_product(params: dict, user_id: str) -> list[dict]:
    product = params.get("product", "")
    session = database.get_session(user_id)
    if not session:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    flow = session["flow"]
    category = session.get("category", "")

    # 削除フロー → 確認画面
    if flow == FLOW_DELETE_PRODUCT:
        database.set_session(
            user_id, flow, STEP_CONFIRM,
            category=category, product=product,
        )
        return [_build_delete_confirm_flex(product)]

    # 名称変更フロー → 新名称入力
    if flow == FLOW_RENAME_PRODUCT:
        database.set_session(
            user_id, flow, STEP_INPUT_NEW_NAME,
            category=category, product=product,
        )
        return [_build_text(f"✏️ 「{product}」のあたらしいおなまえをいれてでしゅ！")]

    # 閾値設定フローの場合：閾値選択に進む
    if flow == FLOW_THRESHOLD:
        database.set_session(
            user_id, flow, STEP_QUANTITY,
            category=category, product=product,
        )
        return [_build_threshold_select(product)]

    # 入庫・出庫フロー：数量選択に進む
    database.set_session(
        user_id, flow, STEP_QUANTITY,
        category=category, product=product,
    )
    return [_build_quantity_select(product, flow)]


# ─────────────────────────────────────────────
#  フロー処理: 商品名入力（追加）
# ─────────────────────────────────────────────
def _handle_input_name(text: str, user_id: str, session: dict) -> list[dict]:
    flow = session["flow"]

    if flow == FLOW_ADD_PRODUCT:
        name = text.strip()
        if not name:
            return [_build_text("おしょうひんのなまえをいれてほしいでしゅ！🍼")]

        category = session["category"]
        success = database.add_product(name, category)
        database.clear_session(user_id)

        if success:
            msg = f"✅ 「{name}」を {category} にいれたでしゅ！🎉\nさいしょのかず: {database.DEFAULT_QUANTITY}こ / しきいち: {database.DEFAULT_THRESHOLD}"
            msg += _rikkun_msg(category)
            return [_build_text(msg)]
        else:
            return [_build_text(f"⚠️ 「{name}」はもうあるでしゅよ～😅")]

    return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]


# ─────────────────────────────────────────────
#  フロー処理: 新名称入力（リネーム）
# ─────────────────────────────────────────────
def _handle_input_new_name(text: str, user_id: str, session: dict) -> list[dict]:
    new_name = text.strip()
    if not new_name:
        return [_build_text("あたらしいおなまえをいれてほしいでしゅ！🍼")]

    old_name = session["product"]
    success = database.rename_product(old_name, new_name)
    database.clear_session(user_id)

    if success:
        return [_build_text(f"✅ 「{old_name}」→「{new_name}」におなまえかえたでしゅ！🎉")]
    else:
        return [_build_text(f"⚠️ おなまえかえられなかったでしゅ…😢「{new_name}」がもうあるか、もとのおしょうひんがみつかんないでしゅ。")]


# ─────────────────────────────────────────────
#  フロー処理: 数量選択
# ─────────────────────────────────────────────
def _handle_select_quantity(params: dict, user_id: str) -> list[dict]:
    qty = int(params.get("qty", "0"))
    session = database.get_session(user_id)
    if not session:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    flow = session["flow"]
    product = session["product"]

    # 閾値設定フロー
    if flow == FLOW_THRESHOLD:
        database.set_threshold(product, qty)
        database.clear_session(user_id)
        return [_build_text(f"✅ {product} のしきいちを {qty} にしたでしゅ！🔔")]

    # 入庫・出庫フロー → 確認画面へ
    database.set_session(
        user_id, flow, STEP_CONFIRM,
        category=session["category"], product=product, quantity=qty,
    )
    return [_build_confirm_flex(user_id, session, qty)]


def _handle_direct_input_start(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    database.set_session(
        user_id, session["flow"], STEP_DIRECT_INPUT,
        category=session["category"], product=session["product"],
    )
    return [_build_text("おかずをにゅうりょくしてでしゅ！（れい: 15）🔢")]


def _handle_direct_input(text: str, user_id: str, session: dict) -> list[dict]:
    try:
        qty = int(text)
    except ValueError:
        return [_build_text("おすうじをいれてほしいでしゅ～（れい: 15）🔢")]

    if qty <= 0:
        return [_build_text("1いじょうのおすうじをいれてでしゅ！☝️")]

    flow = session["flow"]

    # 閾値設定フロー
    if flow == FLOW_THRESHOLD:
        database.set_threshold(session["product"], qty)
        database.clear_session(user_id)
        return [_build_text(f"✅ {session['product']} のしきいちを {qty} にしたでしゅ！🔔")]

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
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    product = session["product"]
    qty = session["quantity"]
    new_qty = database.update_quantity(product, qty)
    database.clear_session(user_id)

    return [_build_completion_flex(product, qty, new_qty)]


def _handle_confirm_delete(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session or session["flow"] != FLOW_DELETE_PRODUCT:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    product = session["product"]
    success = database.delete_product(product)
    database.clear_session(user_id)

    if success:
        return [_build_text(f"✅ 「{product}」をけしたでしゅ！ばいばい～👋")]
    else:
        return [_build_text(f"⚠️ 「{product}」がけせなかったでしゅ…😢")]


# ─────────────────────────────────────────────
#  フロー処理: 戻る
# ─────────────────────────────────────────────
def _handle_back_to_category(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    flow = session["flow"]

    # 在庫設定系フローは設定メニューに戻る
    if flow in (FLOW_ADD_PRODUCT, FLOW_DELETE_PRODUCT, FLOW_RENAME_PRODUCT, FLOW_THRESHOLD):
        database.set_session(user_id, flow, STEP_CATEGORY)
        flow_labels = {
            FLOW_ADD_PRODUCT: "➕ ついかするカテゴリをえらぶでしゅ！",
            FLOW_DELETE_PRODUCT: "🗑️ さくじょするカテゴリをえらぶでしゅ！",
            FLOW_RENAME_PRODUCT: "✏️ おなまえかえるカテゴリをえらぶでしゅ！",
            FLOW_THRESHOLD: "🔔 しきいちかえるカテゴリをえらぶでしゅ！",
        }
        return [_build_category_select(flow_labels.get(flow, "カテゴリをえらぶでしゅ！"))]

    database.set_session(user_id, flow, STEP_CATEGORY)
    if flow == FLOW_INCREASE:
        label = "➕ にゅうこ：カテゴリをえらぶでしゅ！"
    else:
        label = "➖ しゅっこ：カテゴリをえらぶでしゅ！"

    return [_build_category_select(label)]


def _handle_back_to_product(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session or not session["category"]:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

    flow = session["flow"]
    category = session["category"]
    database.set_session(user_id, flow, STEP_PRODUCT, category=category)

    flow_labels = {
        FLOW_INCREASE: "➕ にゅうこ",
        FLOW_DECREASE: "➖ しゅっこ",
        FLOW_THRESHOLD: "🔔 しきいちへんこう",
        FLOW_DELETE_PRODUCT: "🗑️ さくじょ",
        FLOW_RENAME_PRODUCT: "✏️ おなまえへんこう",
    }
    prefix = flow_labels.get(flow, "")
    label = f"{prefix} > {category}：おしょうひんをえらぶでしゅ！"

    return [_build_product_select(category, label)]


def _handle_back_to_quantity(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    if not session or not session["product"]:
        return [_build_text("おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！")]

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
            "label": "← やめる",
            "data": "action=cancel",
            "displayText": "やめる",
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
            "label": "← もどる",
            "data": "action=back_to_category",
            "displayText": "もどる",
        },
    })
    return _build_text(label, {"items": items})


def _build_quantity_select(product: str, flow: str) -> dict:
    if flow == FLOW_INCREASE:
        quantities = [1, 2, 3, 5, 10]
        label = f"➕ {product}：おかずをえらぶでしゅ！"
    else:
        quantities = [-1, -2, -3, -5, -10]
        label = f"➖ {product}：おかずをえらぶでしゅ！"

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
            "label": "じぶんでいれる",
            "data": "action=direct_input",
            "displayText": "じぶんでいれる",
        },
    })
    # 戻るボタン
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "← もどる",
            "data": "action=back_to_product",
            "displayText": "もどる",
        },
    })
    return _build_text(label, {"items": items})


def _build_threshold_select(product: str) -> dict:
    thresholds = [1, 2, 3, 5, 10]
    label = f"🔔 {product}：しきいちをえらぶでしゅ！"

    items = []
    for t in thresholds:
        items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"{t}",
                "data": f"action=select_quantity&qty={t}",
                "displayText": f"しきいち: {t}",
            },
        })
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "じぶんでいれる",
            "data": "action=direct_input",
            "displayText": "じぶんでいれる",
        },
    })
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "← もどる",
            "data": "action=back_to_product",
            "displayText": "もどる",
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

    flow_label = "にゅうこ" if flow == FLOW_INCREASE else "しゅっこ"
    flow_color = "#1A6FBF" if flow == FLOW_INCREASE else "#DC3545"
    sign = "+" if qty > 0 else ""

    return {
        "type": "flex",
        "altText": f"{flow_label}かくにん: {product} {sign}{qty}",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": flow_color,
                "contents": [{
                    "type": "text",
                    "text": f"📋 これであってましゅか？（{flow_label}）",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "lg",
                    "wrap": True,
                }],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    _flex_kv("おしょうひん", product),
                    _flex_kv("おかず", f"{sign}{qty}"),
                    {"type": "separator", "margin": "md"},
                    _flex_kv("いまのかず", f"{current_qty} こ"),
                    _flex_kv("かえたあと", f"{new_qty} こ"),
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
                            "label": "✅ これでいいでしゅ",
                            "data": "action=confirm",
                            "displayText": "かくてい！",
                        },
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "postback",
                            "label": "❌ やめる",
                            "data": "action=cancel",
                            "displayText": "やめる",
                        },
                    },
                ],
            },
        },
    }


def _build_delete_confirm_flex(product: str) -> dict:
    item = database.get_item(product)
    qty = item["quantity"] if item else 0

    return {
        "type": "flex",
        "altText": f"さくじょかくにん: {product}",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#DC3545",
                "contents": [{
                    "type": "text",
                    "text": "🗑️ けしちゃうでしゅか？",
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
                    _flex_kv("おしょうひん", product),
                    _flex_kv("いまのかず", f"{qty} こ"),
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "text",
                        "text": "ほんとにけしちゃうでしゅか？😳",
                        "size": "sm",
                        "color": "#DC3545",
                        "weight": "bold",
                        "margin": "md",
                        "wrap": True,
                    },
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
                        "color": "#DC3545",
                        "action": {
                            "type": "postback",
                            "label": "🗑️ けしちゃう",
                            "data": "action=confirm_delete",
                            "displayText": "けしちゃう",
                        },
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "postback",
                            "label": "❌ やめる",
                            "data": "action=cancel",
                            "displayText": "やめる",
                        },
                    },
                ],
            },
        },
    }


def _build_completion_flex(product: str, delta: int, new_qty: int) -> dict:
    sign = "+" if delta > 0 else ""
    flow_label = "にゅうこ" if delta > 0 else "しゅっこ"

    body_contents = [
        {
            "type": "text",
            "text": f"✅ {flow_label}できたでしゅ！🎉",
            "weight": "bold",
            "size": "xl",
            "color": "#06C755",
            "wrap": True,
        },
        {"type": "separator", "margin": "md"},
        _flex_kv("おしょうひん", product),
        _flex_kv("かわったかず", f"{sign}{delta}"),
        _flex_kv("いまのかず", f"{new_qty} こ"),
    ]

    # 閾値チェック
    item = database.get_item(product)
    if item and new_qty <= item["threshold"]:
        body_contents.append({"type": "separator", "margin": "md"})
        body_contents.append({
            "type": "text",
            "text": f"⚠️ ざいこがしきいち（{item['threshold']}）いかでしゅ！おかいものいかなきゃ！🛒",
            "color": "#DC3545",
            "weight": "bold",
            "size": "sm",
            "margin": "md",
            "wrap": True,
        })

    return {
        "type": "flex",
        "altText": f"{flow_label}かんりょう: {product} → {new_qty}こ",
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
        return _build_text("ざいこがないでしゅ…からっぽでしゅ😢")

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
            "text": "📦 ざいこいちらん",
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
                "text": f"  {item['name']}: {item['quantity']}こ{warn}",
                "size": "sm",
                "color": "#DC3545" if item["quantity"] <= item["threshold"] else "#333333",
                "wrap": True,
            })

    # 未分類
    if uncategorized:
        body_contents.append({
            "type": "text", "text": "📦 そのた",
            "weight": "bold", "size": "sm", "color": "#555555", "margin": "lg",
        })
        for item in uncategorized:
            warn = " ⚠️" if item["quantity"] <= item["threshold"] else ""
            body_contents.append({
                "type": "text",
                "text": f"  {item['name']}: {item['quantity']}こ{warn}",
                "size": "sm",
                "color": "#DC3545" if item["quantity"] <= item["threshold"] else "#333333",
                "wrap": True,
            })

    return {
        "type": "flex",
        "altText": "📦 ざいこいちらん",
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
        return _build_text("✅ ざいこはぜんぶだいじょうぶでしゅ！えらい！🌟")

    bubbles = []
    for item in items:
        bubbles.append({
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#DC3545",
                "paddingAll": "md",
                "contents": [{
                    "type": "text",
                    "text": "⚠️ たりないでしゅ！",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "sm",
                }],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": item["name"],
                        "weight": "bold",
                        "size": "lg",
                        "wrap": True,
                        "color": "#333333",
                    },
                    {"type": "separator", "margin": "md"},
                    _flex_kv("いまのかず", f"{item['quantity']} こ"),
                    _flex_kv("しきいち",   f"{item['threshold']} こ"),
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "button",
                    "style": "primary",
                    "color": "#1A6FBF",
                    "action": {
                        "type": "postback",
                        "label": "✅ ほじゅうしたでしゅ",
                        "data": f"action=start_restock&product={item['name']}",
                        "displayText": f"{item['name']}をほじゅう",
                    },
                }],
            },
        })

    return {
        "type": "flex",
        "altText": f"⚠️ ざいこたりない {len(items)}けん",
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }


def _build_manual_flex() -> dict:
    return {
        "type": "flex",
        "altText": "📖 つかいかたマニュアル",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1A6FBF",
                "contents": [{
                    "type": "text",
                    "text": "📖 りっくんのつかいかた",
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
                    _manual_section("➕ ざいこをふやしゅ",
                                    "メニューから「ざいこをふやしゅ」をタップ\n→ カテゴリ → おしょうひん → おかず → かくてい！"),
                    _manual_section("➖ ざいこをへらしゅ",
                                    "メニューから「ざいこをへらしゅ」をタップ\n→ カテゴリ → おしょうひん → おかず → かくてい！"),
                    _manual_section("📋 ざいこかくにん",
                                    "メニューから「ざいこかくにん」をタップ\n→ ぜんぶのざいこがみれるでしゅ！"),
                    _manual_section("⚠️ たりないものかくにん",
                                    "メニューから「たりないもの」をタップ\n→ しきいちいかのおしょうひんがわかるでしゅ！"),
                    _manual_section("⚙️ ざいこせってい",
                                    "おしょうひんのついか・さくじょ・おなまえへんこう・しきいちへんこう"),
                    _manual_section("📝 テキストでもできるでしゅ",
                                    "「しょうひんめい すうりょう」でちょくせつふやしたりへらしたり\nれい: マスク -3、ティッシュ +5"),
                    _manual_section("⏰ まいあさ7じにおしらせ",
                                    "たりないものがあったら\nじどうでおしえてあげるでしゅ！🌅"),
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
    lines = ["⚠️ たりないものがあるでしゅ！🍼", "─────────────────"]
    for item in items:
        lines.append(f"{item['name']}: {item['quantity']}こ（しきいち: {item['threshold']}）")
    lines.append("─────────────────\nおかいものいってほしいでしゅ～🛒")
    return "\n".join(lines)
