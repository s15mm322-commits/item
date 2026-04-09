import unicodedata
import psycopg2
import psycopg2.extras
import config


def normalize(text: str) -> str:
    """全角/半角の正規化とトリム"""
    return unicodedata.normalize("NFKC", text.strip())


def get_conn():
    conn = psycopg2.connect(config.DATABASE_URL)
    return conn


# ─────────── カテゴリ・商品マスタ ───────────
CATEGORIES = {
    "バス": ["パパシャンプー", "ママシャンプー", "コンディショナー", "ボディソープ",
             "りっくんボディソープ", "バス洗剤", "入浴剤"],
    "トイレ": ["トイレットペーパー", "トイレ洗剤", "トイレ拭き"],
    "掃除用品": ["ゴミ袋", "クイックルワイパー", "キッチンシート", "食器用洗剤"],
    "衛生・医薬": ["マスク", "ティッシュ", "絆創膏"],
    "洗面所": ["歯磨き粉", "ハンドソープ", "化粧水", "乳液", "オールインワンジェル", "洗濯洗剤"],
    "りっくん関係": ["ごはん", "ガーゼ", "ごみ袋(小)", "オムツ", "オムツ入れ", "おしりふき"],
    "その他": [],
}

CATEGORY_ICONS = {
    "バス": "🚿",
    "トイレ": "🚽",
    "掃除用品": "🧹",
    "衛生・医薬": "💊",
    "洗面所": "🪥",
    "りっくん関係": "🔋",
    "その他": "📦",
}

CATEGORY_ORDER = list(CATEGORIES.keys())

DEFAULT_THRESHOLD = 2
DEFAULT_QUANTITY = 3


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT    NOT NULL UNIQUE,
                    quantity   INTEGER NOT NULL DEFAULT 0,
                    threshold  INTEGER NOT NULL DEFAULT 5,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id    TEXT PRIMARY KEY,
                    flow       TEXT,
                    step       TEXT,
                    category   TEXT,
                    product    TEXT,
                    quantity   INTEGER,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
    _seed_products()
    _update_existing_quantities()


def _seed_products():
    """商品マスタが未登録なら初期データを投入する"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            for category, products in CATEGORIES.items():
                for name in products:
                    cur.execute(
                        """
                        INSERT INTO inventory (name, quantity, threshold)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (name) DO NOTHING
                        """,
                        (name, DEFAULT_QUANTITY, DEFAULT_THRESHOLD),
                    )


def _update_existing_quantities():
    """既存商品で数量が0のものを DEFAULT_QUANTITY に更新する（一回限りのマイグレーション）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            all_products = []
            for products in CATEGORIES.values():
                all_products.extend(products)
            for name in all_products:
                cur.execute(
                    "UPDATE inventory SET quantity = %s WHERE name = %s AND quantity = 0",
                    (DEFAULT_QUANTITY, name),
                )


# ─────────── セッション管理 ───────────
def get_session(user_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM user_sessions WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def set_session(user_id: str, flow: str, step: str,
                category: str = None, product: str = None, quantity: int = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_sessions (user_id, flow, step, category, product, quantity, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    flow = EXCLUDED.flow,
                    step = EXCLUDED.step,
                    category = EXCLUDED.category,
                    product = EXCLUDED.product,
                    quantity = EXCLUDED.quantity,
                    updated_at = NOW()
                """,
                (user_id, flow, step, category, product, quantity),
            )


def clear_session(user_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))


# ─────────── 在庫操作 ───────────
def update_quantity(name: str, delta: int) -> int:
    """在庫数を delta だけ増減する。商品が存在しない場合は新規作成。
    更新後の在庫数を返す。"""
    name = normalize(name)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO inventory (name, quantity)
                VALUES (%s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    quantity   = inventory.quantity + EXCLUDED.quantity,
                    updated_at = NOW()
                RETURNING quantity
                """,
                (name, delta),
            )
            row = cur.fetchone()
    return row[0]


def get_quantity(name: str) -> int:
    """商品の現在在庫数を返す。存在しなければ0。"""
    name = normalize(name)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT quantity FROM inventory WHERE name = %s", (name,))
            row = cur.fetchone()
    return row[0] if row else 0


def get_item(name: str) -> dict | None:
    """商品情報を1件取得する。"""
    name = normalize(name)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT name, quantity, threshold FROM inventory WHERE name = %s",
                (name,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def add_product(name: str, category: str = None) -> bool:
    """商品を新規追加する。既に存在する場合はFalseを返す。"""
    name = normalize(name)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM inventory WHERE name = %s", (name,))
            if cur.fetchone():
                return False
            cur.execute(
                "INSERT INTO inventory (name, quantity, threshold) VALUES (%s, %s, %s)",
                (name, DEFAULT_QUANTITY, DEFAULT_THRESHOLD),
            )
    # CATEGORIESにも追加（ランタイムのみ）
    if category and category in CATEGORIES:
        if name not in CATEGORIES[category]:
            CATEGORIES[category].append(name)
    return True


def delete_product(name: str) -> bool:
    """商品を削除する。存在しない場合はFalseを返す。"""
    name = normalize(name)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM inventory WHERE name = %s RETURNING name", (name,))
            deleted = cur.fetchone()
    if deleted:
        # CATEGORIESからも削除（ランタイムのみ）
        for cat_products in CATEGORIES.values():
            if name in cat_products:
                cat_products.remove(name)
        return True
    return False


def rename_product(old_name: str, new_name: str) -> bool:
    """商品名を変更する。成功したらTrue。"""
    old_name = normalize(old_name)
    new_name = normalize(new_name)
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 新名前が既に存在しないかチェック
            cur.execute("SELECT 1 FROM inventory WHERE name = %s", (new_name,))
            if cur.fetchone():
                return False
            cur.execute(
                "UPDATE inventory SET name = %s, updated_at = NOW() WHERE name = %s RETURNING name",
                (new_name, old_name),
            )
            updated = cur.fetchone()
    if updated:
        # CATEGORIESも更新（ランタイムのみ）
        for cat_products in CATEGORIES.values():
            if old_name in cat_products:
                idx = cat_products.index(old_name)
                cat_products[idx] = new_name
        return True
    return False


def get_all_product_names() -> list[str]:
    """全商品名をリストで返す。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM inventory ORDER BY name")
            return [row[0] for row in cur.fetchall()]


def set_threshold(name: str, threshold: int):
    name = normalize(name)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE inventory SET threshold = %s WHERE name = %s",
                (threshold, name),
            )


def get_all_inventory() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT name, quantity, threshold FROM inventory ORDER BY name"
            )
            return [dict(r) for r in cur.fetchall()]


def get_low_stock() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT name, quantity, threshold FROM inventory WHERE quantity <= threshold ORDER BY quantity"
            )
            return [dict(r) for r in cur.fetchall()]


def get_setting(key: str) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
            row = cur.fetchone()
    return row[0] if row else None


def set_setting(key: str, value: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, value),
            )
