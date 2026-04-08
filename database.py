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
