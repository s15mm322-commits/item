import sqlite3
import unicodedata
import config


def normalize(text: str) -> str:
    """全角/半角の正規化とトリム"""
    return unicodedata.normalize("NFKC", text.strip())


def get_conn():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                quantity   INTEGER NOT NULL DEFAULT 0,
                threshold  INTEGER NOT NULL DEFAULT 5,
                updated_at TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)


def update_quantity(name: str, delta: int) -> int:
    """在庫数を delta だけ増減する。商品が存在しない場合は新規作成。
    新規の場合は delta が初期在庫数になる。負になる場合もそのまま保存する。
    更新後の在庫数を返す。"""
    name = normalize(name)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO inventory (name, quantity)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET
                quantity   = quantity + excluded.quantity,
                updated_at = datetime('now')
            """,
            (name, delta),
        )
        row = conn.execute(
            "SELECT quantity FROM inventory WHERE name = ?", (name,)
        ).fetchone()
    return row["quantity"]


def set_threshold(name: str, threshold: int):
    name = normalize(name)
    with get_conn() as conn:
        conn.execute(
            "UPDATE inventory SET threshold = ? WHERE name = ?",
            (threshold, name),
        )


def get_all_inventory() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, quantity, threshold FROM inventory ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_low_stock() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, quantity, threshold FROM inventory WHERE quantity <= threshold ORDER BY quantity"
        ).fetchall()
    return [dict(r) for r in rows]


def get_setting(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
