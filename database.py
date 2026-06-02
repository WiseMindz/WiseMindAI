import os
import aiosqlite
from datetime import datetime
from typing import Optional, List

# DB path is configurable so it can live on the Railway /data volume (persists
# across redeploys). Local default = trades.db in the project dir.
DB_PATH = os.getenv("DATABASE_PATH", "trades.db")


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

        # Trade Results — permanent outcome storage from Pine v9.23+ webhooks
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trade_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                trade_type TEXT,
                session TEXT,
                result TEXT NOT NULL,
                entry REAL,
                sl REAL,
                tp REAL,
                exit_price REAL,
                rr_planned REAL,
                rr_achieved REAL,
                version TEXT,
                trade_id INTEGER,
                timestamp TEXT NOT NULL
            )
        """)

        # Index för monthly aggregation (year-month from timestamp)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_trade_results_timestamp
            ON trade_results(timestamp DESC)
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


# ==================== TRADE RESULTS (v9.23+) ====================

async def save_trade_result(
    symbol: str,
    direction: str,
    result: str,
    entry: float,
    sl: float,
    tp: float,
    exit_price: float,
    rr_planned: float,
    rr_achieved: float,
    trade_type: str = "",
    session: str = "",
    version: str = "",
) -> dict:
    """
    Sparar ett trade-resultat (WIN/LOSS) från Pine v9.23+ outcome webhook.
    Försöker också uppdatera matchande trade i trades-tabellen.

    Returns:
        dict med id, matched_trade_id (om en existerande trade uppdaterades)
    """
    now = datetime.now().isoformat()
    matched_trade_id = None

    async with aiosqlite.connect(DB_PATH) as db:
        # Försök matcha mot senaste trade med samma symbol + direction + entry
        async with db.execute("""
            SELECT id FROM trades
            WHERE symbol = ? AND direction = ? AND abs(entry - ?) < 0.01
            AND result IS NULL
            ORDER BY id DESC LIMIT 1
        """, (symbol, direction.lower(), entry)) as cursor:
            row = await cursor.fetchone()
            if row:
                matched_trade_id = row[0]
                # Uppdatera den matchade traden med resultat
                await db.execute("""
                    UPDATE trades
                    SET exit_price = ?, rr = ?, result = ?
                    WHERE id = ?
                """, (exit_price, rr_achieved, result, matched_trade_id))

        # Spara i dedikerad trade_results-tabell (alltid)
        await db.execute("""
            INSERT INTO trade_results
            (symbol, direction, trade_type, session, result, entry, sl, tp,
             exit_price, rr_planned, rr_achieved, version, trade_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, direction.lower(), trade_type, session, result,
            entry, sl, tp, exit_price, rr_planned, rr_achieved,
            version, matched_trade_id, now,
        ))

        await db.commit()

        # Hämta det nya result-ID:t
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            result_id = (await cursor.fetchone())[0]

    return {"id": result_id, "matched_trade_id": matched_trade_id}


async def get_monthly_stats(months: int = 6) -> List[dict]:
    """
    Hämtar W/L/WR%/R-data aggregerat per månad, senaste N månader.

    Returns:
        Lista med dicts: {month, year, wins, losses, total, win_rate, total_r}
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT
                strftime('%Y', timestamp) AS year,
                strftime('%m', timestamp) AS month,
                SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN result = 'BE' THEN 1 ELSE 0 END) AS be_count,
                COUNT(*) AS total,
                ROUND(SUM(rr_achieved), 2) AS total_r
            FROM trade_results
            GROUP BY year, month
            ORDER BY year DESC, month DESC
            LIMIT ?
        """, (months,)) as cursor:
            rows = await cursor.fetchall()

    # Returnera i kronologisk ordning (äldsta först)
    stats = []
    for row in reversed(rows):
        year, month, wins, losses, be_count, total, total_r = row
        win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0
        be_rate = round((be_count / total) * 100, 1) if total > 0 else 0.0
        month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        stats.append({
            "month": month_names[int(month)],
            "year": int(year),
            "wins": wins,
            "losses": losses,
            "be_count": be_count,
            "total": total,
            "win_rate": win_rate,
            "be_rate": be_rate,
            "total_r": total_r or 0.0,
        })
    return stats


async def get_recent_results(limit: int = 10) -> List[dict]:
    """Hämtar de senaste N trade-resultaten."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT symbol, direction, trade_type, session, result,
                   entry, exit_price, rr_planned, rr_achieved, timestamp
            FROM trade_results
            ORDER BY id DESC LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in rows]
