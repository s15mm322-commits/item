"""
LINE メッセージ / ポストバック処理。
クイックリプライとフレックスメッセージを使った対話的な在庫管理フローを提供する。

言語モード:
  normal  - 通常の日本語
  rikkun  - 赤ちゃん言葉（でしゅ語）
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


# ─────────────────────────────────────────────
#  言語モード
# ─────────────────────────────────────────────
def _mode() -> str:
    """現在の言語モードを取得（normal / rikkun）"""
    return database.get_setting("language_mode") or "normal"


def _t(normal: str, rikkun: str, mode: str = None) -> str:
    """モードに応じたテキストを返す"""
    if mode is None:
        mode = _mode()
    return rikkun if mode == "rikkun" else normal


def _rikkun_extra(category: str, mode: str) -> str:
    """りっくん関係カテゴリかつりっくんモードの場合、感情メッセージを返す"""
    if mode == "rikkun" and category == "りっくん関係":
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
        item = database.get_item(name)
        if item:
            database.clear_session(user_id)
            new_qty = database.update_quantity(name, delta)
            return [_build_completion_flex(name, delta, new_qty)]
        else:
            return [_build_text(_t(
                f"「{name}」は商品マスタに登録されていません。\n在庫設定メニューから商品を追加してください。",
                f"「{name}」はおしょうひんにないでしゅ…😢\nざいこせっていから追加してほしいでしゅ！",
            ))]

    # ── セッション外のフリーテキスト ──
    return [_build_text(_t(
        "メニューから操作を選択してください。\nテキストで在庫増減する場合：商品名 数量（例: マスク -3）",
        "メニューからえらんでほしいでしゅ！🍼\nテキストでざいこふやしたりへらしたりもできるでしゅ：商品名 数量（れい: マスク -3）",
    ))]


# ─────────────────────────────────────────────
#  ポストバックハンドラ
# ─────────────────────────────────────────────
def handle_postback(data: str, user_id: str) -> list[dict]:
    """
    ポストバックデータを処理し、返信メッセージオブジェクトのリストを返す。
    """
    params = dict(p.split("=", 1) for p in data.split("&") if "=" in p)
    action = params.get("action", "")
    mode = _mode()

    # ── リッチメニューからのアクション ──
    if action == "start_increase":
        database.set_session(user_id, FLOW_INCREASE, STEP_CATEGORY)
        return [_build_category_select(_t("➕ 入庫：カテゴリを選んでください", "➕ にゅうこ：カテゴリをえらぶでしゅ！", mode))]

    if action == "start_decrease":
        database.set_session(user_id, FLOW_DECREASE, STEP_CATEGORY)
        return [_build_category_select(_t("➖ 出庫：カテゴリを選んでください", "➖ しゅっこ：カテゴリをえらぶでしゅ！", mode))]

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
            return [_build_text(_t("商品が指定されていません。", "おしょうひんがわかんないでしゅ…😢", mode))]
        database.set_session(user_id, FLOW_INCREASE, STEP_QUANTITY, product=product)
        return [_build_quantity_select(product, FLOW_INCREASE)]

    # ── 言語モード切替 ──
    if action == "toggle_mode":
        new_mode = "rikkun" if mode == "normal" else "normal"
        database.set_setting("language_mode", new_mode)
        if new_mode == "rikkun":
            msg = "👶 りっくんモードにしたでしゅ！\nこれからはでしゅ語でしゃべるでしゅよ～🍼"
        else:
            msg = "✅ 通常モードに切り替えました。\nこれからは通常の言葉でお話しします。"
        database.set_session(user_id, "settings", STEP_SETTINGS_MENU)
        return [_build_text(msg), _build_settings_menu()]

    # ── 在庫設定サブメニュー ──
    if action == "settings_add":
        database.set_session(user_id, FLOW_ADD_PRODUCT, STEP_CATEGORY)
        return [_build_category_select(_t("➕ 追加先のカテゴリを選んでください", "➕ ついかするカテゴリをえらぶでしゅ！", mode))]

    if action == "settings_delete":
        database.set_session(user_id, FLOW_DELETE_PRODUCT, STEP_CATEGORY)
        return [_build_category_select(_t("🗑️ 削除する商品のカテゴリを選んでください", "🗑️ さくじょするカテゴリをえらぶでしゅ！", mode))]

    if action == "settings_rename":
        database.set_session(user_id, FLOW_RENAME_PRODUCT, STEP_CATEGORY)
        return [_build_category_select(_t("✏️ 名称変更する商品のカテゴリを選んでください", "✏️ おなまえかえるカテゴリをえらぶでしゅ！", mode))]

    if action == "settings_threshold":
        database.set_session(user_id, FLOW_THRESHOLD, STEP_CATEGORY)
        return [_build_category_select(_t("🔔 閾値変更する商品のカテゴリを選んでください", "🔔 しきいちかえるカテゴリをえらぶでしゅ！", mode))]

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
        return [_build_text(_t(
            "キャンセルしました。メニューから操作を選んでください。",
            "やめたでしゅ！🙌 メニューからまたえらんでほしいでしゅ！",
            mode,
        ))]

    if action == "back_to_category":
        return _handle_back_to_category(user_id)

    if action == "back_to_product":
        return _handle_back_to_product(user_id)

    if action == "back_to_quantity":
        return _handle_back_to_quantity(user_id)

    if action == "back_to_settings":
        database.set_session(user_id, "settings", STEP_SETTINGS_MENU)
        return [_build_settings_menu()]

    return [_build_text(_t(
        "不明な操作です。メニューからもう一度お試しください。",
        "なにかわかんないでしゅ…😵 メニューからもういっかいやってみてでしゅ！",
        mode,
    ))]


# ─────────────────────────────────────────────
#  在庫設定メニュー
# ─────────────────────────────────────────────
def _build_settings_menu() -> dict:
    mode = _mode()
    is_rikkun = (mode == "rikkun")

    toggle_label = "👶 りっくんモードにする" if not is_rikkun else "🔤 通常モードにもどす"
    toggle_display = toggle_label

    items = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": _t("➕ 在庫追加", "➕ ざいこついか", mode),
                "data": "action=settings_add",
                "displayText": _t("➕ 在庫追加", "➕ ざいこついか", mode),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": _t("🗑️ 在庫削除", "🗑️ ざいこさくじょ", mode),
                "data": "action=settings_delete",
                "displayText": _t("🗑️ 在庫削除", "🗑️ ざいこさくじょ", mode),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": _t("✏️ 在庫名称変更", "✏️ おなまえへんこう", mode),
                "data": "action=settings_rename",
                "displayText": _t("✏️ 在庫名称変更", "✏️ おなまえへんこう", mode),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": _t("🔔 閾値変更", "🔔 しきいちへんこう", mode),
                "data": "action=settings_threshold",
                "displayText": _t("🔔 閾値変更", "🔔 しきいちへんこう", mode),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": toggle_label,
                "data": "action=toggle_mode",
                "displayText": toggle_display,
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": _t("← キャンセル", "← やめる", mode),
                "data": "action=cancel",
                "displayText": _t("キャンセル", "やめる", mode),
            },
        },
    ]
    return _build_text(
        _t("⚙️ 在庫設定：操作を選んでください", "⚙️ ざいこせってい：なにしゅる～？🍼", mode),
        {"items": items},
    )


# ─────────────────────────────────────────────
#  フロー処理: カテゴリ選択
# ─────────────────────────────────────────────
def _handle_select_category(params: dict, user_id: str) -> list[dict]:
    category = params.get("category", "")
    session = database.get_session(user_id)
    mode = _mode()
    if not session:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    flow = session["flow"]

    if flow == FLOW_ADD_PRODUCT:
        database.set_session(user_id, flow, STEP_INPUT_NAME, category=category)
        msg = _t(
            f"➕ {category} > 追加する商品名を入力してください",
            f"➕ {category} > ついかするおしょうひんのなまえをいれてでしゅ！",
            mode,
        )
        msg += _rikkun_extra(category, mode)
        return [_build_text(msg)]

    database.set_session(user_id, flow, STEP_PRODUCT, category=category)

    flow_labels_normal = {
        FLOW_INCREASE: "➕ 入庫",
        FLOW_DECREASE: "➖ 出庫",
        FLOW_THRESHOLD: "🔔 閾値変更",
        FLOW_DELETE_PRODUCT: "🗑️ 削除",
        FLOW_RENAME_PRODUCT: "✏️ 名称変更",
    }
    flow_labels_rikkun = {
        FLOW_INCREASE: "➕ にゅうこ",
        FLOW_DECREASE: "➖ しゅっこ",
        FLOW_THRESHOLD: "🔔 しきいちへんこう",
        FLOW_DELETE_PRODUCT: "🗑️ さくじょ",
        FLOW_RENAME_PRODUCT: "✏️ おなまえへんこう",
    }
    prefix = _t(flow_labels_normal.get(flow, ""), flow_labels_rikkun.get(flow, ""), mode)
    label = _t(
        f"{prefix} > {category}：商品を選んでください",
        f"{prefix} > {category}：おしょうひんをえらぶでしゅ！",
        mode,
    )
    label += _rikkun_extra(category, mode)

    return [_build_product_select(category, label)]


# ─────────────────────────────────────────────
#  フロー処理: 商品選択
# ─────────────────────────────────────────────
def _handle_select_product(params: dict, user_id: str) -> list[dict]:
    product = params.get("product", "")
    session = database.get_session(user_id)
    mode = _mode()
    if not session:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    flow = session["flow"]
    category = session.get("category", "")

    if flow == FLOW_DELETE_PRODUCT:
        database.set_session(user_id, flow, STEP_CONFIRM, category=category, product=product)
        return [_build_delete_confirm_flex(product)]

    if flow == FLOW_RENAME_PRODUCT:
        database.set_session(user_id, flow, STEP_INPUT_NEW_NAME, category=category, product=product)
        return [_build_text(_t(
            f"✏️ 「{product}」の新しい名称を入力してください",
            f"✏️ 「{product}」のあたらしいおなまえをいれてでしゅ！",
            mode,
        ))]

    if flow == FLOW_THRESHOLD:
        database.set_session(user_id, flow, STEP_QUANTITY, category=category, product=product)
        return [_build_threshold_select(product)]

    database.set_session(user_id, flow, STEP_QUANTITY, category=category, product=product)
    return [_build_quantity_select(product, flow)]


# ─────────────────────────────────────────────
#  フロー処理: 商品名入力（追加）
# ─────────────────────────────────────────────
def _handle_input_name(text: str, user_id: str, session: dict) -> list[dict]:
    flow = session["flow"]
    mode = _mode()

    if flow == FLOW_ADD_PRODUCT:
        name = text.strip()
        if not name:
            return [_build_text(_t("商品名を入力してください。", "おしょうひんのなまえをいれてほしいでしゅ！🍼", mode))]

        category = session["category"]
        success = database.add_product(name, category)
        database.clear_session(user_id)

        if success:
            msg = _t(
                f"✅ 「{name}」を {category} カテゴリに追加しました。\n初期数量: {database.DEFAULT_QUANTITY}個 / 閾値: {database.DEFAULT_THRESHOLD}",
                f"✅ 「{name}」を {category} にいれたでしゅ！🎉\nさいしょのかず: {database.DEFAULT_QUANTITY}こ / しきいち: {database.DEFAULT_THRESHOLD}",
                mode,
            )
            msg += _rikkun_extra(category, mode)
            return [_build_text(msg)]
        else:
            return [_build_text(_t(
                f"⚠️ 「{name}」は既に登録されています。",
                f"⚠️ 「{name}」はもうあるでしゅよ～😅",
                mode,
            ))]

    return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]


# ─────────────────────────────────────────────
#  フロー処理: 新名称入力（リネーム）
# ─────────────────────────────────────────────
def _handle_input_new_name(text: str, user_id: str, session: dict) -> list[dict]:
    mode = _mode()
    new_name = text.strip()
    if not new_name:
        return [_build_text(_t("新しい商品名を入力してください。", "あたらしいおなまえをいれてほしいでしゅ！🍼", mode))]

    old_name = session["product"]
    success = database.rename_product(old_name, new_name)
    database.clear_session(user_id)

    if success:
        return [_build_text(_t(
            f"✅ 「{old_name}」→「{new_name}」に名称を変更しました。",
            f"✅ 「{old_name}」→「{new_name}」におなまえかえたでしゅ！🎉",
            mode,
        ))]
    else:
        return [_build_text(_t(
            f"⚠️ 名称変更に失敗しました。「{new_name}」が既に存在するか、元の商品が見つかりません。",
            f"⚠️ おなまえかえられなかったでしゅ…😢「{new_name}」がもうあるか、もとのおしょうひんがみつかんないでしゅ。",
            mode,
        ))]


# ─────────────────────────────────────────────
#  フロー処理: 数量選択
# ─────────────────────────────────────────────
def _handle_select_quantity(params: dict, user_id: str) -> list[dict]:
    qty = int(params.get("qty", "0"))
    session = database.get_session(user_id)
    mode = _mode()
    if not session:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    flow = session["flow"]
    product = session["product"]

    if flow == FLOW_THRESHOLD:
        database.set_threshold(product, qty)
        database.clear_session(user_id)
        return [_build_text(_t(
            f"✅ {product} の通知閾値を {qty} に設定しました。",
            f"✅ {product} のしきいちを {qty} にしたでしゅ！🔔",
            mode,
        ))]

    database.set_session(user_id, flow, STEP_CONFIRM, category=session["category"], product=product, quantity=qty)
    return [_build_confirm_flex(user_id, session, qty)]


def _handle_direct_input_start(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    mode = _mode()
    if not session:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    database.set_session(user_id, session["flow"], STEP_DIRECT_INPUT, category=session["category"], product=session["product"])
    return [_build_text(_t("数量を入力してください（例: 15）", "おかずをにゅうりょくしてでしゅ！（れい: 15）🔢", mode))]


def _handle_direct_input(text: str, user_id: str, session: dict) -> list[dict]:
    mode = _mode()
    try:
        qty = int(text)
    except ValueError:
        return [_build_text(_t("数値を入力してください（例: 15）", "おすうじをいれてほしいでしゅ～（れい: 15）🔢", mode))]

    if qty <= 0:
        return [_build_text(_t("1以上の数値を入力してください。", "1いじょうのおすうじをいれてでしゅ！☝️", mode))]

    flow = session["flow"]

    if flow == FLOW_THRESHOLD:
        database.set_threshold(session["product"], qty)
        database.clear_session(user_id)
        return [_build_text(_t(
            f"✅ {session['product']} の通知閾値を {qty} に設定しました。",
            f"✅ {session['product']} のしきいちを {qty} にしたでしゅ！🔔",
            mode,
        ))]

    actual_qty = qty if flow == FLOW_INCREASE else -qty
    database.set_session(user_id, flow, STEP_CONFIRM, category=session["category"], product=session["product"], quantity=actual_qty)
    return [_build_confirm_flex(user_id, session, actual_qty)]


# ─────────────────────────────────────────────
#  フロー処理: 確定
# ─────────────────────────────────────────────
def _handle_confirm(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    mode = _mode()
    if not session or session["step"] != STEP_CONFIRM:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    product = session["product"]
    qty = session["quantity"]
    new_qty = database.update_quantity(product, qty)
    database.clear_session(user_id)

    return [_build_completion_flex(product, qty, new_qty)]


def _handle_confirm_delete(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    mode = _mode()
    if not session or session["flow"] != FLOW_DELETE_PRODUCT:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    product = session["product"]
    success = database.delete_product(product)
    database.clear_session(user_id)

    if success:
        return [_build_text(_t(f"✅ 「{product}」を削除しました。", f"✅ 「{product}」をけしたでしゅ！ばいばい～👋", mode))]
    else:
        return [_build_text(_t(f"⚠️ 「{product}」の削除に失敗しました。", f"⚠️ 「{product}」がけせなかったでしゅ…😢", mode))]


# ─────────────────────────────────────────────
#  フロー処理: 戻る
# ─────────────────────────────────────────────
def _handle_back_to_category(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    mode = _mode()
    if not session:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    flow = session["flow"]

    if flow in (FLOW_ADD_PRODUCT, FLOW_DELETE_PRODUCT, FLOW_RENAME_PRODUCT, FLOW_THRESHOLD):
        database.set_session(user_id, flow, STEP_CATEGORY)
        flow_labels = {
            FLOW_ADD_PRODUCT: _t("➕ 追加先のカテゴリを選んでください", "➕ ついかするカテゴリをえらぶでしゅ！", mode),
            FLOW_DELETE_PRODUCT: _t("🗑️ 削除する商品のカテゴリを選んでください", "🗑️ さくじょするカテゴリをえらぶでしゅ！", mode),
            FLOW_RENAME_PRODUCT: _t("✏️ 名称変更する商品のカテゴリを選んでください", "✏️ おなまえかえるカテゴリをえらぶでしゅ！", mode),
            FLOW_THRESHOLD: _t("🔔 閾値変更する商品のカテゴリを選んでください", "🔔 しきいちかえるカテゴリをえらぶでしゅ！", mode),
        }
        return [_build_category_select(flow_labels.get(flow, _t("カテゴリを選んでください", "カテゴリをえらぶでしゅ！", mode)))]

    database.set_session(user_id, flow, STEP_CATEGORY)
    if flow == FLOW_INCREASE:
        label = _t("➕ 入庫：カテゴリを選んでください", "➕ にゅうこ：カテゴリをえらぶでしゅ！", mode)
    else:
        label = _t("➖ 出庫：カテゴリを選んでください", "➖ しゅっこ：カテゴリをえらぶでしゅ！", mode)

    return [_build_category_select(label)]


def _handle_back_to_product(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    mode = _mode()
    if not session or not session["category"]:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    flow = session["flow"]
    category = session["category"]
    database.set_session(user_id, flow, STEP_PRODUCT, category=category)

    flow_labels_normal = {
        FLOW_INCREASE: "➕ 入庫",
        FLOW_DECREASE: "➖ 出庫",
        FLOW_THRESHOLD: "🔔 閾値変更",
        FLOW_DELETE_PRODUCT: "🗑️ 削除",
        FLOW_RENAME_PRODUCT: "✏️ 名称変更",
    }
    flow_labels_rikkun = {
        FLOW_INCREASE: "➕ にゅうこ",
        FLOW_DECREASE: "➖ しゅっこ",
        FLOW_THRESHOLD: "🔔 しきいちへんこう",
        FLOW_DELETE_PRODUCT: "🗑️ さくじょ",
        FLOW_RENAME_PRODUCT: "✏️ おなまえへんこう",
    }
    prefix = _t(flow_labels_normal.get(flow, ""), flow_labels_rikkun.get(flow, ""), mode)
    label = _t(
        f"{prefix} > {category}：商品を選んでください",
        f"{prefix} > {category}：おしょうひんをえらぶでしゅ！",
        mode,
    )

    return [_build_product_select(category, label)]


def _handle_back_to_quantity(user_id: str) -> list[dict]:
    session = database.get_session(user_id)
    mode = _mode()
    if not session or not session["product"]:
        return [_build_text(_t("セッションが切れました。メニューからやり直してください。", "おぼえてないでしゅ…😢 メニューからやりなおしてほしいでしゅ！", mode))]

    flow = session["flow"]
    database.set_session(user_id, flow, STEP_QUANTITY, category=session["category"], product=session["product"])

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
    mode = _mode()
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
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": _t("← キャンセル", "← やめる", mode),
            "data": "action=cancel",
            "displayText": _t("キャンセル", "やめる", mode),
        },
    })
    return _build_text(label, {"items": items})


def _build_product_select(category: str, label: str) -> dict:
    mode = _mode()
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
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": _t("← 戻る", "← もどる", mode),
            "data": "action=back_to_category",
            "displayText": _t("戻る", "もどる", mode),
        },
    })
    return _build_text(label, {"items": items})


def _build_quantity_select(product: str, flow: str) -> dict:
    mode = _mode()
    if flow == FLOW_INCREASE:
        quantities = [1, 2, 3, 5, 10]
        label = _t(f"➕ {product}：数量を選んでください", f"➕ {product}：おかずをえらぶでしゅ！", mode)
    else:
        quantities = [-1, -2, -3, -5, -10]
        label = _t(f"➖ {product}：数量を選んでください", f"➖ {product}：おかずをえらぶでしゅ！", mode)

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
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": _t("直接入力", "じぶんでいれる", mode),
            "data": "action=direct_input",
            "displayText": _t("直接入力", "じぶんでいれる", mode),
        },
    })
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": _t("← 戻る", "← もどる", mode),
            "data": "action=back_to_product",
            "displayText": _t("戻る", "もどる", mode),
        },
    })
    return _build_text(label, {"items": items})


def _build_threshold_select(product: str) -> dict:
    mode = _mode()
    thresholds = [1, 2, 3, 5, 10]
    label = _t(f"🔔 {product}：通知閾値を選んでください", f"🔔 {product}：しきいちをえらぶでしゅ！", mode)

    items = []
    for t in thresholds:
        items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"{t}",
                "data": f"action=select_quantity&qty={t}",
                "displayText": _t(f"閾値: {t}", f"しきいち: {t}", mode),
            },
        })
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": _t("直接入力", "じぶんでいれる", mode),
            "data": "action=direct_input",
            "displayText": _t("直接入力", "じぶんでいれる", mode),
        },
    })
    items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": _t("← 戻る", "← もどる", mode),
            "data": "action=back_to_product",
            "displayText": _t("戻る", "もどる", mode),
        },
    })
    return _build_text(label, {"items": items})


# ─────────────────────────────────────────────
#  メッセージビルダー: フレックスメッセージ
# ─────────────────────────────────────────────
def _build_confirm_flex(user_id: str, session: dict, qty: int) -> dict:
    mode = _mode()
    product = session["product"]
    flow = session["flow"]
    current_qty = database.get_quantity(product)
    new_qty = current_qty + qty

    flow_label = _t("入庫", "にゅうこ", mode) if flow == FLOW_INCREASE else _t("出庫", "しゅっこ", mode)
    flow_color = "#1A6FBF" if flow == FLOW_INCREASE else "#DC3545"
    sign = "+" if qty > 0 else ""

    header_text = _t(f"📋 {flow_label}確認", f"📋 これであってましゅか？（{flow_label}）", mode)

    return {
        "type": "flex",
        "altText": _t(f"{flow_label}確認: {product} {sign}{qty}", f"{flow_label}かくにん: {product} {sign}{qty}", mode),
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": flow_color,
                "contents": [{
                    "type": "text",
                    "text": header_text,
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
                    _flex_kv(_t("商品名", "おしょうひん", mode), product),
                    _flex_kv(_t("数量", "おかず", mode), f"{sign}{qty}"),
                    {"type": "separator", "margin": "md"},
                    _flex_kv(_t("変更前", "いまのかず", mode), _t(f"{current_qty} 個", f"{current_qty} こ", mode)),
                    _flex_kv(_t("変更後", "かえたあと", mode), _t(f"{new_qty} 個", f"{new_qty} こ", mode)),
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
                            "label": _t("✅ 確定", "✅ これでいいでしゅ", mode),
                            "data": "action=confirm",
                            "displayText": _t("確定", "かくてい！", mode),
                        },
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "postback",
                            "label": _t("❌ キャンセル", "❌ やめる", mode),
                            "data": "action=cancel",
                            "displayText": _t("キャンセル", "やめる", mode),
                        },
                    },
                ],
            },
        },
    }


def _build_delete_confirm_flex(product: str) -> dict:
    mode = _mode()
    item = database.get_item(product)
    qty = item["quantity"] if item else 0

    return {
        "type": "flex",
        "altText": _t(f"削除確認: {product}", f"さくじょかくにん: {product}", mode),
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#DC3545",
                "contents": [{
                    "type": "text",
                    "text": _t("🗑️ 削除確認", "🗑️ けしちゃうでしゅか？", mode),
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
                    _flex_kv(_t("商品名", "おしょうひん", mode), product),
                    _flex_kv(_t("現在庫数", "いまのかず", mode), _t(f"{qty} 個", f"{qty} こ", mode)),
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "text",
                        "text": _t("この商品を削除しますか？", "ほんとにけしちゃうでしゅか？😳", mode),
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
                            "label": _t("🗑️ 削除する", "🗑️ けしちゃう", mode),
                            "data": "action=confirm_delete",
                            "displayText": _t("削除する", "けしちゃう", mode),
                        },
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "postback",
                            "label": _t("❌ キャンセル", "❌ やめる", mode),
                            "data": "action=cancel",
                            "displayText": _t("キャンセル", "やめる", mode),
                        },
                    },
                ],
            },
        },
    }


def _build_completion_flex(product: str, delta: int, new_qty: int) -> dict:
    mode = _mode()
    sign = "+" if delta > 0 else ""
    flow_label = _t("入庫", "にゅうこ", mode) if delta > 0 else _t("出庫", "しゅっこ", mode)

    body_contents = [
        {
            "type": "text",
            "text": _t(f"✅ {flow_label}完了", f"✅ {flow_label}できたでしゅ！🎉", mode),
            "weight": "bold",
            "size": "xl",
            "color": "#06C755",
            "wrap": True,
        },
        {"type": "separator", "margin": "md"},
        _flex_kv(_t("商品名", "おしょうひん", mode), product),
        _flex_kv(_t("変更数量", "かわったかず", mode), f"{sign}{delta}"),
        _flex_kv(_t("現在庫数", "いまのかず", mode), _t(f"{new_qty} 個", f"{new_qty} こ", mode)),
    ]

    item = database.get_item(product)
    if item and new_qty <= item["threshold"]:
        body_contents.append({"type": "separator", "margin": "md"})
        body_contents.append({
            "type": "text",
            "text": _t(
                f"⚠️ 在庫が閾値（{item['threshold']}）以下です！",
                f"⚠️ ざいこがしきいち（{item['threshold']}）いかでしゅ！おかいものいかなきゃ！🛒",
                mode,
            ),
            "color": "#DC3545",
            "weight": "bold",
            "size": "sm",
            "margin": "md",
            "wrap": True,
        })

    return {
        "type": "flex",
        "altText": _t(f"{flow_label}完了: {product} → {new_qty}個", f"{flow_label}かんりょう: {product} → {new_qty}こ", mode),
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
    mode = _mode()
    items = database.get_all_inventory()
    if not items:
        return _build_text(_t("在庫データがありません。", "ざいこがないでしゅ…からっぽでしゅ😢", mode))

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
            "text": _t("📦 在庫一覧", "📦 ざいこいちらん", mode),
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
            qty_str = _t(f"{item['quantity']}個", f"{item['quantity']}こ", mode)
            body_contents.append({
                "type": "text",
                "text": f"  {item['name']}: {qty_str}{warn}",
                "size": "sm",
                "color": "#DC3545" if item["quantity"] <= item["threshold"] else "#333333",
                "wrap": True,
            })

    if uncategorized:
        body_contents.append({
            "type": "text", "text": "📦 その他",
            "weight": "bold", "size": "sm", "color": "#555555", "margin": "lg",
        })
        for item in uncategorized:
            warn = " ⚠️" if item["quantity"] <= item["threshold"] else ""
            qty_str = _t(f"{item['quantity']}個", f"{item['quantity']}こ", mode)
            body_contents.append({
                "type": "text",
                "text": f"  {item['name']}: {qty_str}{warn}",
                "size": "sm",
                "color": "#DC3545" if item["quantity"] <= item["threshold"] else "#333333",
                "wrap": True,
            })

    return {
        "type": "flex",
        "altText": _t("📦 在庫一覧", "📦 ざいこいちらん", mode),
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
    mode = _mode()
    items = database.get_low_stock()
    if not items:
        return _build_text(_t("✅ 在庫不足の商品はありません。", "✅ ざいこはぜんぶだいじょうぶでしゅ！えらい！🌟", mode))

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
                    "text": _t("⚠️ 在庫不足", "⚠️ たりないでしゅ！", mode),
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
                    _flex_kv(_t("現在庫", "いまのかず", mode), _t(f"{item['quantity']} 個", f"{item['quantity']} こ", mode)),
                    _flex_kv(_t("閾値", "しきいち", mode), _t(f"{item['threshold']} 個", f"{item['threshold']} こ", mode)),
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
                        "label": _t("✅ 補充完了", "✅ ほじゅうしたでしゅ", mode),
                        "data": f"action=start_restock&product={item['name']}",
                        "displayText": _t(f"{item['name']}を補充", f"{item['name']}をほじゅう", mode),
                    },
                }],
            },
        })

    return {
        "type": "flex",
        "altText": _t(f"⚠️ 在庫不足 {len(items)}件", f"⚠️ ざいこたりない {len(items)}けん", mode),
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }


def _build_manual_flex() -> dict:
    mode = _mode()
    return {
        "type": "flex",
        "altText": _t("📖 操作マニュアル", "📖 つかいかたマニュアル", mode),
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1A6FBF",
                "contents": [{
                    "type": "text",
                    "text": _t("📖 操作マニュアル", "📖 りっくんのつかいかた", mode),
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
                    _manual_section(
                        _t("➕ 在庫を増やす", "➕ ざいこをふやしゅ", mode),
                        _t("メニューから「在庫を増やす」をタップ\n→ カテゴリ → 商品 → 数量 → 確定",
                           "メニューから「ざいこをふやしゅ」をタップ\n→ カテゴリ → おしょうひん → おかず → かくてい！", mode),
                    ),
                    _manual_section(
                        _t("➖ 在庫を減らす", "➖ ざいこをへらしゅ", mode),
                        _t("メニューから「在庫を減らす」をタップ\n→ カテゴリ → 商品 → 数量 → 確定",
                           "メニューから「ざいこをへらしゅ」をタップ\n→ カテゴリ → おしょうひん → おかず → かくてい！", mode),
                    ),
                    _manual_section(
                        _t("📋 在庫確認", "📋 ざいこかくにん", mode),
                        _t("メニューから「在庫確認」をタップ\n→ 全商品の在庫をカテゴリ別に表示",
                           "メニューから「ざいこかくにん」をタップ\n→ ぜんぶのざいこがみれるでしゅ！", mode),
                    ),
                    _manual_section(
                        _t("⚠️ 在庫不足確認", "⚠️ たりないものかくにん", mode),
                        _t("メニューから「在庫不足確認」をタップ\n→ 閾値以下の商品を一覧表示",
                           "メニューから「たりないもの」をタップ\n→ しきいちいかのおしょうひんがわかるでしゅ！", mode),
                    ),
                    _manual_section(
                        _t("⚙️ 在庫設定", "⚙️ ざいこせってい", mode),
                        _t("商品の追加・削除・名称変更・閾値変更",
                           "おしょうひんのついか・さくじょ・おなまえへんこう・しきいちへんこう", mode),
                    ),
                    _manual_section(
                        _t("📝 テキスト入力", "📝 テキストでもできるでしゅ", mode),
                        _t("「商品名 数量」で直接増減\n例: マスク -3、ティッシュ +5",
                           "「しょうひんめい すうりょう」でちょくせつふやしたりへらしたり\nれい: マスク -3、ティッシュ +5", mode),
                    ),
                    _manual_section(
                        _t("⏰ 毎朝7時通知", "⏰ まいあさ7じにおしらせ", mode),
                        _t("閾値以下の在庫がある場合\n自動でアラートが届きます",
                           "たりないものがあったら\nじどうでおしえてあげるでしゅ！🌅", mode),
                    ),
                    _manual_section(
                        "👶 言語モード切替",
                        _t("在庫設定メニューから\n通常モード ↔ りっくんモード を切り替えられます",
                           "ざいこせっていメニューから\nふつうのことばとでしゅ語をきりかえられるでしゅ！", mode),
                    ),
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
    mode = _mode()
    if mode == "rikkun":
        lines = ["⚠️ たりないものがあるでしゅ！🍼", "─────────────────"]
        for item in items:
            lines.append(f"{item['name']}: {item['quantity']}こ（しきいち: {item['threshold']}）")
        lines.append("─────────────────\nおかいものいってほしいでしゅ～🛒")
    else:
        lines = ["⚠️ 在庫不足アラート", "─────────────────"]
        for item in items:
            lines.append(f"{item['name']}: {item['quantity']}個（閾値: {item['threshold']}）")
        lines.append("─────────────────\n補充をご確認ください。")
    return "\n".join(lines)
