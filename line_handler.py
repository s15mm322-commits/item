import re
import database

# 例: 'りんご -5', 'バナナ +10', '牛乳 3'
QUANTITY_RE = re.compile(r"^(.+?)\s*([\+\-]?\d+)$")

# 例: 'りんご 閾値 3'
THRESHOLD_RE = re.compile(r"^(.+?)\s+閾値\s*(\d+)$")


def handle_message(text: str, source) -> str:
    text = text.strip()

    # ---- 在庫確認 ----
    if text == "在庫確認":
        return _format_inventory()

    # ---- 閾値設定: 'りんご 閾値 3' ----
    m = THRESHOLD_RE.match(text)
    if m:
        name, threshold = m.group(1), int(m.group(2))
        database.set_threshold(name, threshold)
        return f"✅ {name} の閾値を {threshold} に設定しました。"

    # ---- 在庫増減: 'りんご -5' ----
    m = QUANTITY_RE.match(text)
    if m:
        name, delta = m.group(1), int(m.group(2))
        new_qty = database.update_quantity(name, delta)
        sign = "+" if delta >= 0 else ""
        result = f"✅ {name}: {sign}{delta} → 現在 {new_qty} 個"
        items = database.get_all_inventory()
        item = next((i for i in items if i["name"] == database.normalize(name)), None)
        if item and new_qty <= item["threshold"]:
            result += f"\n⚠️ 在庫が閾値（{item['threshold']}）以下です！"
        return result

    # ---- ヘルプ ----
    return (
        "📦 在庫管理ボット\n"
        "─────────────────\n"
        "在庫確認          → 一覧表示\n"
        "りんご -5         → 在庫を減らす\n"
        "りんご +10        → 在庫を増やす\n"
        "りんご 閾値 3     → 閾値を設定\n"
    )


def _format_inventory() -> str:
    items = database.get_all_inventory()
    if not items:
        return "在庫データがありません。\n「商品名 数量」で在庫を登録できます。"
    lines = ["📦 在庫一覧", "─────────────────"]
    for item in items:
        warn = " ⚠️" if item["quantity"] <= item["threshold"] else ""
        lines.append(f"{item['name']}: {item['quantity']}個{warn}")
    return "\n".join(lines)


def format_low_stock_alert(items: list[dict]) -> str:
    lines = ["⚠️ 在庫不足アラート", "─────────────────"]
    for item in items:
        lines.append(f"{item['name']}: {item['quantity']}個（閾値: {item['threshold']}）")
    lines.append("─────────────────\n補充をご確認ください。")
    return "\n".join(lines)
