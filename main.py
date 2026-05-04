"""
BTC/USD 5-Minute Consecutive Candle Alert Bot — PUBLIC VERSION
──────────────────────────────────────────────────────────────
- Anyone can subscribe via /start
- Broadcasts alerts to ALL subscribers
- SQLite DB (auto-upgrades to PostgreSQL on Railway)
- Commands: /start, /stop, /status, /subscribers (admin only)
"""

import requests
import time
import os
import sqlite3
import threading
from datetime import datetime, timezone

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "8393168939:AAEAAhXaMcHotbruUll36w9q4TK9WPjonUI")
ADMIN_CHAT_ID    = os.environ.get("ADMIN_CHAT_ID",  "5792224870")

SYMBOL           = "BTCUSDT"
INTERVAL         = "5m"
STREAK_TRIGGER   = 4
FETCH_LIMIT      = 10
CHECK_INTERVAL   = 30      # seconds between candle checks
POLL_INTERVAL    = 2       # seconds between Telegram update polls
DB_FILE          = "subscribers.db"
# ─────────────────────────────────────────────────────────────────────────────


# ── DATABASE ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id   TEXT PRIMARY KEY,
            username  TEXT,
            joined_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_subscriber(chat_id, username=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO subscribers (chat_id, username, joined_at)
        VALUES (?, ?, ?)
    """, (str(chat_id), username, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

def remove_subscriber(chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM subscribers WHERE chat_id = ?", (str(chat_id),))
    conn.commit()
    conn.close()

def get_all_subscribers():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id, username FROM subscribers")
    rows = c.fetchall()
    conn.close()
    return rows

def is_subscribed(chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM subscribers WHERE chat_id = ?", (str(chat_id),))
    result = c.fetchone()
    conn.close()
    return result is not None

def subscriber_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM subscribers")
    count = c.fetchone()[0]
    conn.close()
    return count
# ─────────────────────────────────────────────────────────────────────────────


# ── TELEGRAM HELPERS ──────────────────────────────────────────────────────────
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send_message(chat_id: str, text: str):
    try:
        r = requests.post(f"{BASE_URL}/sendMessage", json={
            "chat_id":    str(chat_id),
            "text":       text,
            "parse_mode": "HTML",
        }, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  ❌ Send error to {chat_id}: {e}")
        return False

def broadcast(text: str):
    subscribers = get_all_subscribers()
    sent = 0
    failed = 0
    dead_ids = []
    for chat_id, username in subscribers:
        ok = send_message(chat_id, text)
        if ok:
            sent += 1
        else:
            failed += 1
            dead_ids.append(chat_id)
        time.sleep(0.05)   # avoid Telegram rate limits

    # Remove users who blocked the bot
    for dead_id in dead_ids:
        remove_subscriber(dead_id)

    print(f"  📢 Broadcast: {sent} sent, {failed} failed/removed")
    return sent

def get_updates(offset=None):
    params = {"timeout": 30, "limit": 100}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=35)
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception as e:
        print(f"  ⚠️  getUpdates error: {e}")
        return []
# ─────────────────────────────────────────────────────────────────────────────


# ── COMMAND HANDLERS ──────────────────────────────────────────────────────────
def handle_start(chat_id, username):
    if is_subscribed(chat_id):
        send_message(chat_id,
            "✅ <b>You're already subscribed!</b>\n\n"
            "You'll receive alerts whenever <b>4 consecutive</b> green or red "
            "BTC/USD 5m candles form.\n\n"
            "Send /stop to unsubscribe."
        )
    else:
        add_subscriber(chat_id, username)
        send_message(chat_id,
            f"🎉 <b>Welcome! You're now subscribed to BTC Alerts!</b>\n\n"
            f"📌 <b>What you'll get:</b>\n"
            f"  • Alert when 4 consecutive 🟢 GREEN candles form\n"
            f"  • Alert when 4 consecutive 🔴 RED candles form\n"
            f"  • BTC/USD 5-minute candles (Binance)\n\n"
            f"⚡ <b>Commands:</b>\n"
            f"  /start  — Subscribe to alerts\n"
            f"  /stop   — Unsubscribe\n"
            f"  /status — Check current BTC streak\n\n"
            f"<i>Sit back and wait for the next signal! 🚀</i>"
        )
        print(f"  ➕ New subscriber: {username} ({chat_id})")

        # Notify admin
        send_message(ADMIN_CHAT_ID,
            f"➕ <b>New subscriber!</b>\n"
            f"👤 {username or 'Unknown'} ({chat_id})\n"
            f"👥 Total: {subscriber_count()}"
        )

def handle_stop(chat_id, username):
    if is_subscribed(chat_id):
        remove_subscriber(chat_id)
        send_message(chat_id,
            "😢 <b>You've been unsubscribed.</b>\n\n"
            "You won't receive BTC alerts anymore.\n"
            "Send /start anytime to subscribe again!"
        )
        print(f"  ➖ Unsubscribed: {username} ({chat_id})")
    else:
        send_message(chat_id,
            "⚠️ You're not subscribed.\n"
            "Send /start to subscribe!"
        )

def handle_status(chat_id, current_streak, current_dir):
    emoji = "🟢" if current_dir == "green" else ("🔴" if current_dir == "red" else "⚪")
    send_message(chat_id,
        f"📊 <b>BTC/USD 5m Current Streak</b>\n\n"
        f"{emoji * current_streak} <b>{current_streak}x {current_dir.upper()}</b>\n\n"
        f"Need <b>{STREAK_TRIGGER} consecutive</b> candles to trigger an alert.\n"
        f"👥 <b>Subscribers:</b> {subscriber_count()}"
    )

def handle_subscribers(chat_id):
    if str(chat_id) != str(ADMIN_CHAT_ID):
        send_message(chat_id, "⛔ Admin only command.")
        return
    subs = get_all_subscribers()
    count = len(subs)
    lines = "\n".join(
        f"  {i+1}. {u or 'Unknown'} ({cid})"
        for i, (cid, u) in enumerate(subs[:20])
    )
    send_message(chat_id,
        f"👥 <b>Subscribers ({count} total)</b>\n\n"
        f"<code>{lines}</code>"
        + (f"\n\n<i>...and {count-20} more</i>" if count > 20 else "")
    )
# ─────────────────────────────────────────────────────────────────────────────


# ── CANDLE LOGIC ──────────────────────────────────────────────────────────────
def fetch_recent_candles(limit=10):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": SYMBOL, "interval": INTERVAL, "limit": limit}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def classify(candle):
    o  = float(candle[1])
    cl = float(candle[4])
    if cl > o:   return "green"
    elif cl < o: return "red"
    return "doji"

def ts(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def get_current_streak(closed_candles):
    """Returns (streak_length, direction) of the most recent consecutive run."""
    directions = [classify(c) for c in closed_candles]
    if not directions:
        return 0, "unknown"
    last_dir = directions[-1]
    if last_dir == "doji":
        return 0, "doji"
    count = 0
    for d in reversed(directions):
        if d == last_dir:
            count += 1
        else:
            break
    return count, last_dir
# ─────────────────────────────────────────────────────────────────────────────


# ── POLLING THREAD (handles user commands) ────────────────────────────────────
current_streak_info = {"streak": 0, "dir": "unknown"}   # shared state

def polling_thread():
    offset = None
    print("🤖 Telegram polling started…")
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    continue
                chat_id  = str(msg["chat"]["id"])
                username = msg.get("from", {}).get("username") or \
                           msg.get("from", {}).get("first_name", "Unknown")
                text     = msg.get("text", "").strip().lower().split()[0]

                if text == "/start":
                    handle_start(chat_id, username)
                elif text == "/stop":
                    handle_stop(chat_id, username)
                elif text == "/status":
                    handle_status(chat_id,
                                  current_streak_info["streak"],
                                  current_streak_info["dir"])
                elif text == "/subscribers":
                    handle_subscribers(chat_id)

        except Exception as e:
            print(f"  ⚠️  Polling error: {e}")

        time.sleep(POLL_INTERVAL)
# ─────────────────────────────────────────────────────────────────────────────


# ── MAIN MONITOR LOOP ─────────────────────────────────────────────────────────
def monitor_loop():
    last_alert_candle_time = None

    print("📡 Candle monitor started…")
    while True:
        try:
            candles = fetch_recent_candles(limit=FETCH_LIMIT)
            closed  = candles[:-1]   # exclude forming candle

            if len(closed) < STREAK_TRIGGER:
                time.sleep(CHECK_INTERVAL)
                continue

            streak, direction = get_current_streak(closed)
            current_streak_info["streak"] = streak
            current_streak_info["dir"]    = direction

            recent      = closed[-STREAK_TRIGGER:]
            last_candle = recent[-1]
            last_open_t = last_candle[0]

            now_str = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")

            if streak >= STREAK_TRIGGER and last_open_t != last_alert_candle_time:
                # ── BUILD ALERT ──────────────────────────────────────────────
                emoji     = "🟢" if direction == "green" else "🔴"
                dir_label = "GREEN 🟢" if direction == "green" else "RED 🔴"
                opp       = "🔴 SHORT (sell)" if direction == "green" else "🟢 LONG (buy)"
                price_now   = float(closed[-1][4])
                price_start = float(recent[0][1])
                move_pct    = ((price_now - price_start) / price_start) * 100

                alert_msg = (
                    f"{emoji * STREAK_TRIGGER}\n"
                    f"<b>⚡ {STREAK_TRIGGER} Consecutive {dir_label} Candles!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>Symbol  :</b> BTC/USD (5m)\n"
                    f"🕐 <b>From    :</b> {ts(recent[0][0])}\n"
                    f"🕐 <b>To      :</b> {ts(last_candle[0])}\n"
                    f"💵 <b>Price   :</b> ${price_now:,.2f}\n"
                    f"📈 <b>Move    :</b> {move_pct:+.2f}%\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>Signal  :</b> {opp}\n"
                    f"💰 Enter trade in opposite direction!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Next 5m candle is your entry candle</i>"
                )

                print(f"[{now_str}] 🚨 ALERT! {streak}x {direction.upper()} → Broadcasting…")
                sent = broadcast(alert_msg)
                print(f"[{now_str}]  Sent to {sent} subscribers.")
                last_alert_candle_time = last_open_t

            else:
                print(f"[{now_str}]  Watching… streak: {streak}x {direction.upper()}"
                      f"  |  BTC: ${float(closed[-1][4]):,.2f}"
                      f"  |  Subscribers: {subscriber_count()}")

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Network error: {e} — retrying in {CHECK_INTERVAL}s")
        except Exception as e:
            print(f"  ❌ Monitor error: {e}")

        time.sleep(CHECK_INTERVAL)
# ─────────────────────────────────────────────────────────────────────────────


def main():
    print("=" * 55)
    print("  BTC/USD 5m Alert Bot — PUBLIC VERSION")
    print("=" * 55)
    print(f"  Trigger     : {STREAK_TRIGGER} consecutive candles")
    print(f"  Check every : {CHECK_INTERVAL}s")
    print(f"  Admin ID    : {ADMIN_CHAT_ID}")
    print("=" * 55)

    init_db()
    print("✅ Database initialized.")

    # Ensure admin is subscribed
    add_subscriber(ADMIN_CHAT_ID, "admin")

    # Startup message to admin
    send_message(ADMIN_CHAT_ID,
        f"🚀 <b>BTC Alert Bot is LIVE!</b>\n\n"
        f"👥 Subscribers: {subscriber_count()}\n"
        f"⚡ Trigger: {STREAK_TRIGGER} consecutive candles\n"
        f"🔄 Check interval: {CHECK_INTERVAL}s\n\n"
        f"Share your bot link so others can subscribe!\n"
        f"<i>Admin commands: /subscribers</i>"
    )

    # Start polling in background thread
    t = threading.Thread(target=polling_thread, daemon=True)
    t.start()

    # Run candle monitor in main thread
    monitor_loop()


if __name__ == "__main__":
    main()
