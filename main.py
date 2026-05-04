"""
BTC/USD 5-Minute Consecutive Candle Alert Bot
───────────────────────────────────────────────
Monitors BTC/USD 5m candles from Binance.
Sends a Telegram alert when 4 consecutive GREEN or RED candles form.
Runs 24/7 — checks every 30 seconds.
"""

import requests
import time
from datetime import datetime, timezone

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8393168939:AAEAAhXaMcHotbruUll36w9q4TK9WPjonUI"
TELEGRAM_CHAT_ID = "5792224870"

SYMBOL           = "BTCUSDT"
INTERVAL         = "5m"
STREAK_TRIGGER   = 4       # alert after this many consecutive same-direction candles
FETCH_LIMIT      = 10      # how many recent candles to fetch each check
CHECK_INTERVAL   = 30      # seconds between each check
# ─────────────────────────────────────────────────────────────────────────────


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  ❌ Telegram error: {e}")
        return False


def fetch_recent_candles(limit=10):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol":   SYMBOL,
        "interval": INTERVAL,
        "limit":    limit,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def classify(candle):
    o  = float(candle[1])
    cl = float(candle[4])
    if cl > o:
        return "green"
    elif cl < o:
        return "red"
    return "doji"


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def candle_summary(candle):
    o  = float(candle[1])
    h  = float(candle[2])
    l  = float(candle[3])
    cl = float(candle[4])
    return f"O: ${o:,.2f}  H: ${h:,.2f}  L: ${l:,.2f}  C: ${cl:,.2f}"


def main():
    print("=" * 55)
    print("  BTC/USD 5m Consecutive Candle Alert Bot")
    print("=" * 55)
    print(f"  Trigger  : {STREAK_TRIGGER} consecutive GREEN or RED candles")
    print(f"  Interval : Check every {CHECK_INTERVAL}s")
    print(f"  Symbol   : {SYMBOL}")
    print("=" * 55)

    # Startup Telegram message
    send_telegram(
        f"🤖 <b>BTC Alert Bot Started!</b>\n\n"
        f"📌 Monitoring <b>BTC/USD 5m</b> candles\n"
        f"⚡ Will alert when <b>{STREAK_TRIGGER} consecutive</b> green or red candles form\n"
        f"🔄 Checking every {CHECK_INTERVAL} seconds\n\n"
        f"<i>Waiting for pattern…</i>"
    )
    print("✅ Bot started. Monitoring BTC/USD 5m candles...\n")

    last_alert_candle_time = None   # open-time (ms) of the last candle we alerted on

    while True:
        try:
            candles = fetch_recent_candles(limit=FETCH_LIMIT)

            # Exclude the last (still-forming) candle — use only closed candles
            closed = candles[:-1]

            if len(closed) < STREAK_TRIGGER:
                time.sleep(CHECK_INTERVAL)
                continue

            # Check the last STREAK_TRIGGER closed candles
            recent = closed[-STREAK_TRIGGER:]
            directions = [classify(c) for c in recent]
            last_candle = recent[-1]
            last_open_time = last_candle[0]

            now_str = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")

            # Determine if all same direction
            all_green = all(d == "green" for d in directions)
            all_red   = all(d == "red"   for d in directions)

            if (all_green or all_red) and last_open_time != last_alert_candle_time:
                direction   = "GREEN 🟢" if all_green else "RED 🔴"
                emoji       = "🟢" * STREAK_TRIGGER if all_green else "🔴" * STREAK_TRIGGER
                opp         = "🔴 SHORT (sell)" if all_green else "🟢 LONG (buy)"
                first_candle = recent[0]
                last_candle  = recent[-1]

                price_now = float(last_candle[4])
                price_start = float(first_candle[1])
                move_pct = ((price_now - price_start) / price_start) * 100

                alert_msg = (
                    f"{emoji}\n"
                    f"<b>⚡ {STREAK_TRIGGER} Consecutive {direction} Candles!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>Symbol  :</b> BTC/USD (5m)\n"
                    f"🕐 <b>From    :</b> {ts(first_candle[0])}\n"
                    f"🕐 <b>To      :</b> {ts(last_candle[0])}\n"
                    f"💵 <b>Price   :</b> ${price_now:,.2f}\n"
                    f"📈 <b>Move    :</b> {move_pct:+.2f}%\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>Strategy Signal:</b> {opp}\n"
                    f"💰 <b>Enter trade in opposite direction!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Next 5m candle is your entry candle</i>"
                )

                print(f"[{now_str}] 🚨 ALERT! {STREAK_TRIGGER}x {'GREEN' if all_green else 'RED'} candles → Sending Telegram...")
                send_telegram(alert_msg)
                last_alert_candle_time = last_open_time

            else:
                streak_count = 0
                last_dir = directions[-1]
                for d in reversed(directions):
                    if d == last_dir and last_dir != "doji":
                        streak_count += 1
                    else:
                        break
                print(f"[{now_str}]  Watching… current streak: {streak_count}x {last_dir.upper()}  |  BTC: ${float(closed[-1][4]):,.2f}")

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Network error: {e} — retrying in {CHECK_INTERVAL}s")

        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()