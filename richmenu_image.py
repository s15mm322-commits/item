"""
リッチメニュー画像を生成するモジュール。
setup_richmenu.py から呼び出される。ローカルで実行すること。
"""
import os
from PIL import Image, ImageDraw, ImageFont

# ---- レイアウト定数 ----
WIDTH, HEIGHT = 2500, 843
COLS, ROWS = 3, 2
CELL_W = WIDTH // COLS          # 833
CELL_H = HEIGHT // ROWS         # 421

# 中央列だけ1px広くして合計2500にする
COL_WIDTHS = [833, 834, 833]

# ---- 色 ----
COLORS = {
    "bg_top":    "#1A6FBF",   # 上段：青
    "bg_bottom": "#1A8C4E",   # 下段：緑
    "border":    "#FFFFFF",
    "text":      "#FFFFFF",
    "subtext":   "#D0E8FF",
}

# ---- ボタン定義 ----
BUTTONS = [
    # (行, 列, アイコン, ラベル, サブラベル)
    (0, 0, "📦", "在庫確認",     "全商品の在庫を表示"),
    (0, 1, "➖", "在庫を減らす", "例: りんご -5"),
    (0, 2, "➕", "在庫を増やす", "例: りんご +10"),
    (1, 0, "⚠️", "在庫不足確認", "閾値以下の商品を表示"),
    (1, 1, "🔔", "閾値を設定",   "例: りんご 閾値 5"),
    (1, 2, "❓", "ヘルプ",       "操作方法を表示"),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """日本語フォントを探してロード。見つからなければデフォルトを使う。"""
    candidates = [
        "NotoSansCJKjp-Regular.otf",
        "NotoSansJP-Regular.ttf",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/YuGothM.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate(output_path: str = "assets/richmenu.png") -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    img = Image.new("RGB", (WIDTH, HEIGHT), color=COLORS["bg_top"])
    draw = ImageDraw.Draw(img)

    font_icon  = _load_font(100)
    font_main  = _load_font(72)
    font_sub   = _load_font(44)

    for row, col, icon, label, sublabel in BUTTONS:
        # セルの左上座標
        x = sum(COL_WIDTHS[:col])
        y = row * CELL_H
        w = COL_WIDTHS[col]
        h = CELL_H

        # 背景色
        bg = COLORS["bg_top"] if row == 0 else COLORS["bg_bottom"]
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=bg)

        # 枠線
        draw.rectangle([x, y, x + w - 1, y + h - 1],
                       outline=COLORS["border"], width=3)

        cx = x + w // 2

        # アイコン
        draw.text((cx, y + h * 0.22), icon,
                  font=font_icon, fill=COLORS["text"], anchor="mm")

        # メインラベル
        draw.text((cx, y + h * 0.55), label,
                  font=font_main, fill=COLORS["text"], anchor="mm")

        # サブラベル
        draw.text((cx, y + h * 0.78), sublabel,
                  font=font_sub, fill=COLORS["subtext"], anchor="mm")

    img.save(output_path, "PNG")
    print(f"画像生成完了: {output_path}")
    return output_path


if __name__ == "__main__":
    generate()
