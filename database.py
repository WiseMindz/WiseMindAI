import aiosqlite
from datetime import datetime
from typing import Optional, List

DB_PATH = "trades.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Trades-tabellen (oförändrad)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                direction TEXT,
                entry REAL,
                exit_price REAL,
                rr REAL,
                result TEXT,
                timestamp TEXT,
                note TEXT
            )
        """)

        # Messages-tabellen (NY) — för konversationsminne
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        # Index för snabbare queries på chat_id + timestamp
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_time
            ON messages(chat_id, timestamp DESC)
        """)

        await db.commit()


async def save_trade(symbol: str, direction: str, entry: float, note: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO trades (symbol, direction, entry, timestamp, note)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, direction, entry, datetime.now().isoformat(), note))
        await db.commit()


async def get_last_trade():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            return dict(zip([c[0] for c in cursor.description], row)) if row else None


async def get_recent_trades(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(zip([c[0] for c in cursor.description], row)) for row in rows]


# ==================== KONVERSATIONSMINNE (NYTT) ====================

async def save_message(chat_id: int, user_id: Optional[int], username: Optional[str], role: str, text: str):
    """
    Sparar ett meddelande i databasen för konversationsminne.

    Args:
        chat_id: Telegram chat ID (för gruppchatt: negativt nummer)
        user_id: Telegram user ID (None för bot-meddelanden)
        username: Användarens namn (None om ej tillgängligt)
        role: 'user' eller 'assistant'
        text: Meddelandets text
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO messages (chat_id, user_id, username, role, text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (chat_id, user_id, username, role, text, datetime.now().isoformat()))
        await db.commit()


async def get_recent_messages(chat_id: int, limit: int = 20) -> List[dict]:
    """
    Hämtar de senaste N meddelandena från en chat, sorterade kronologiskt
    (äldsta först, för att skickas till Claude i rätt ordning).

    Args:
        chat_id: Telegram chat ID
        limit: Max antal meddelanden att hämta

    Returns:
        Lista med meddelanden i kronologisk ordning
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Hämta senaste N i omvänd ordning (DESC), sedan vänd tillbaka
        async with db.execute("""
            SELECT user_id, username, role, text, timestamp
            FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, limit)) as cursor:
            rows = await cursor.fetchall()

        # Vänd tillbaka till kronologisk ordning (äldsta först)
        rows = list(reversed(rows))

        return [
            {
                "user_id": row[0],
                "username": row[1],
                "role": row[2],
                "text": row[3],
                "timestamp": row[4]
            }
            for row in rows
        ]


async def cleanup_old_messages(chat_id: int, keep_last: int = 100):
    """
    Tar bort gamla meddelanden så databasen inte växer i evighet.
    Behåller de N senaste per chat. Anropa periodvis (t.ex. vid varje fire).

    Args:
        chat_id: Chat att rensa
        keep_last: Hur många senaste meddelanden att behålla
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            DELETE FROM messages
            WHERE chat_id = ?
            AND id NOT IN (
                SELECT id FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
        """, (chat_id, chat_id, keep_last))
        await db.commit()
