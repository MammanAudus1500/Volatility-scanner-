import os
import json
import time
import requests
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES LIVE 4H TIME-BASED STRATEGY SCANNER
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

SCAN_INTERVAL = 60

MARKETS = [
    "1HZ10V",
    "1HZ15V",
    "1HZ25V",
    "1HZ30V",
    "1HZ50V",
    "1HZ75V",
    "1HZ90V",
    "1HZ100V",

    "R_10",
    "R_25",
    "R_50",
    "R_75",
    "R_100",

    "JD10",
    "JD25",
    "JD50",
    "JD75",
    "JD100",

    "stpRNG",
    "stpRNG2",
    "stpRNG3",
    "stpRNG4",
    "stpRNG5",

    "frxEURUSD",
    "frxGBPUSD",
    "frxUSDJPY",
    "frxGBPJPY",
    "frxUSDCAD",
    "frxEURCAD",
    "frxAUDUSD",
    "frxAUDCAD",
    "frxNZDJPY",
    "frxAUDNZD",
    "frxEURGBP",
    "frxEURCHF",
    "frxGBPCHF",
    "frxGBPNZD",
    "frxAUDCHF",
    "frxGBPAUD",
    "frxUSDCHF",
    "frxXAUUSD",
    "cryBTCUSD"
]


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram configuration missing.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=20
        )

        data = response.json()

        if response.status_code == 200 and data.get("ok"):

            print("📱 Telegram alert sent successfully.")

            return True

        print("❌ Telegram error:")
        print(response.text)

    except Exception as e:

        print("❌ Telegram connection error:")
        print(str(e))

    return False


# ============================================================
# CONNECT TO DERIV
# ============================================================

def connect():

    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        DERIV_URL,
        timeout=20
    )

    print("✅ Connected successfully!")

    return ws


# ============================================================
# DERIV REQUEST
# ============================================================

def request(ws, payload):

    ws.send(json.dumps(payload))

    while True:

        message = ws.recv()

        if not message:
            continue

        data = json.loads(message)

        if data.get("error"):
            return data

        return data


# ============================================================
# GET 4H CANDLES
# ============================================================

def get_candles(ws, symbol):

    payload = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": 20,
        "end": "latest",
        "granularity": 14400,
        "style": "candles"
    }

    response = request(ws, payload)

    if response.get("error"):
        return None

    candles = response.get("candles", [])

    if not candles:
        return None

    converted = []

    for candle in candles:

        try:

            timestamp = int(candle["epoch"])

            dt = datetime.fromtimestamp(
                timestamp,
                timezone.utc
            ).astimezone(WAT)

            converted.append({
                "time": dt,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"])
            })

        except Exception:
            continue

    return converted


# ============================================================
# FIND CANDLE
# ============================================================

def find_candle(candles, date_value, hour):

    for candle in candles:

        if (
            candle["time"].date() == date_value
            and candle["time"].hour == hour
        ):
            return candle

    return None


# ============================================================
# BULLISH RULE
#
# IMPORTANT:
# Reference candle direction DOES NOT MATTER.
#
# Only:
# 1. Confirmation low < reference low
# 2. Confirmation close > reference open
#
# ============================================================

def bullish_setup(reference, confirmation):

    # Confirmation must sweep BELOW reference low
    if confirmation["low"] >= reference["low"]:
        return False

    # Confirmation must close STRICTLY ABOVE reference open
    if confirmation["close"] <= reference["open"]:
        return False

    return True


# ============================================================
# BEARISH RULE
#
# Reference candle direction DOES NOT MATTER.
#
# Only:
# 1. Confirmation high > reference high
# 2. Confirmation close < reference open
#
# ============================================================

def bearish_setup(reference, confirmation):

    # Confirmation must sweep ABOVE reference high
    if confirmation["high"] <= reference["high"]:
        return False

    # Confirmation must close STRICTLY BELOW reference open
    if confirmation["close"] >= reference["open"]:
        return False

    return True


# ============================================================
# CREATE SIGNAL
# ============================================================

def check_setup(
    symbol,
    date_value,
    reference,
    confirmation,
    entry_hour,
    reference_hour,
    confirmation_hour
):

    if bullish_setup(reference, confirmation):

        return {
            "symbol": symbol,
            "date": date_value,
            "direction": "BUY",
            "entry": entry_hour,
            "reference_hour": reference_hour,
            "confirmation_hour": confirmation_hour,
            "reference": reference,
            "confirmation": confirmation
        }


    if bearish_setup(reference, confirmation):

        return {
            "symbol": symbol,
            "date": date_value,
            "direction": "SELL",
            "entry": entry_hour,
            "reference_hour": reference_hour,
            "confirmation_hour": confirmation_hour,
            "reference": reference,
            "confirmation": confirmation
        }


    return None


# ============================================================
# SCAN ONE MARKET
# ============================================================

def scan_market(ws, symbol):

    candles = get_candles(
        ws,
        symbol
    )

    if not candles:
        return []


    now = datetime.now(WAT)


    # Only completely CLOSED 4H candles
    completed = []

    for candle in candles:

        candle_end = (
            candle["time"] +
            timedelta(hours=4)
        )

        if candle_end <= now:

            completed.append(candle)


    if len(completed) < 3:

        return []


    dates = sorted(
        set(
            candle["time"].date()
            for candle in completed
        ),
        reverse=True
    )


    signals = []


    # ========================================================
    # SETUP 1
    #
    # 02:00 reference
    # 06:00 confirmation
    # 10:00 entry
    # ========================================================

    for date_value in dates[:2]:

        candle_02 = find_candle(
            completed,
            date_value,
            2
        )

        candle_06 = find_candle(
            completed,
            date_value,
            6
        )

        if candle_02 and candle_06:

            signal = check_setup(
                symbol,
                date_value,
                candle_02,
                candle_06,
                "10:00",
                "02:00",
                "06:00"
            )

            if signal:

                signals.append(signal)


    # ========================================================
    # SETUP 2
    #
    # 06:00 reference
    # 10:00 confirmation
    # 14:00 entry
    # ========================================================

    for date_value in dates[:2]:

        candle_06 = find_candle(
            completed,
            date_value,
            6
        )

        candle_10 = find_candle(
            completed,
            date_value,
            10
        )

        if candle_06 and candle_10:

            signal = check_setup(
                symbol,
                date_value,
                candle_06,
                candle_10,
                "14:00",
                "06:00",
                "10:00"
            )

            if signal:

                signals.append(signal)


    return signals


# ============================================================
# TELEGRAM SIGNAL MESSAGE
# ============================================================

def build_message(signal):

    ref = signal["reference"]
    conf = signal["confirmation"]

    if signal["direction"] == "BUY":
        emoji = "🟢"
    else:
        emoji = "🔴"


    message = f"""
🚨 SIXSGAMES LIVE SIGNAL 🚨

📊 Market: {signal["symbol"]}

{emoji} Direction: {signal["direction"]}

📅 Date: {signal["date"]}

⏰ LOOK FOR ENTRY:
{signal["entry"]} WAT

━━━━━━━━━━━━━━━━━━

📌 Reference candle
Time: {signal["reference_hour"]}

Open: {ref["open"]}
High: {ref["high"]}
Low: {ref["low"]}
Close: {ref["close"]}

━━━━━━━━━━━━━━━━━━

📌 Confirmation candle
Time: {signal["confirmation_hour"]}

Open: {conf["open"]}
High: {conf["high"]}
Low: {conf["low"]}
Close: {conf["close"]}

━━━━━━━━━━━━━━━━━━

✅ Sweep condition passed
✅ Close condition passed
🚫 Reference candle direction ignored

👀 LOOK FOR YOUR ENTRY.
"""

    return message.strip()


# ============================================================
# LIVE SCANNER
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("🤖 SIXSGAMES LIVE 4H STRATEGY SCANNER")
    print("=" * 60)

    print(f"📊 Markets: {len(MARKETS)}")
    print("⏱️ Timeframe: 4H")
    print("🌍 Timezone: Africa/Lagos")
    print("🎯 Entry windows: 10:00 and 14:00")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:

        print("✅ Telegram secrets detected.")

    else:

        print("❌ Telegram secrets missing.")


    # Prevent duplicate alerts
    sent_signals = set()


    while True:

        ws = None

        try:

            ws = connect()

            print("")
            print("=" * 60)
            print("🔎 SCANNING 42 MARKETS")
            print("=" * 60)


            for symbol in MARKETS:

                print(
                    f"🔍 Checking {symbol}...",
                    flush=True
                )


                try:

                    signals = scan_market(
                        ws,
                        symbol
                    )


                    for signal in signals:

                        signal_id = (
                            f"{signal['symbol']}_"
                            f"{signal['date']}_"
                            f"{signal['entry']}_"
                            f"{signal['direction']}"
                        )


                        if signal_id in sent_signals:

                            continue


                        print("")
                        print("🚨 VALID SETUP FOUND!")
                        print(
                            f"📊 Market: "
                            f"{signal['symbol']}"
                        )
                        print(
                            f"🎯 Direction: "
                            f"{signal['direction']}"
                        )
                        print(
                            f"⏰ Entry: "
                            f"{signal['entry']} WAT"
                        )


                        message = build_message(
                            signal
                        )


                        if send_telegram(message):

                            sent_signals.add(
                                signal_id
                            )


                except Exception as e:

                    print(
                        f"⚠️ Error scanning "
                        f"{symbol}: {e}"
                    )


            print("")
            print("✅ Scan complete.")
            print(
                f"😴 Waiting "
                f"{SCAN_INTERVAL} seconds..."
            )


            if ws:

                ws.close()


            time.sleep(
                SCAN_INTERVAL
            )


        except Exception as e:

            print("")
            print("❌ Scanner connection error:")
            print(str(e))

            if ws:

                try:
                    ws.close()
                except Exception:
                    pass


            print(
                "🔄 Reconnecting in 15 seconds..."
            )

            time.sleep(15)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
