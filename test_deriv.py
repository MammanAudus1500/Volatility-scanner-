import json
import os
import time
import requests
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES 4H TIME-BASED TELEGRAM SCANNER
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

GRANULARITY = 14400  # 4 hours

CHECK_INTERVAL = 60  # check every 60 seconds


# ============================================================
# TELEGRAM SECRETS
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# MARKETS
# ============================================================

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
# TELEGRAM MESSAGE
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:

        print("❌ Telegram secrets are missing.")

        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        data = response.json()

        if data.get("ok"):

            print("📱 Telegram notification sent.")

            return True

        print("❌ Telegram error:")
        print(data)

        return False

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
# REQUEST DATA
# ============================================================

def request(ws, payload):

    ws.send(json.dumps(payload))

    while True:

        raw = ws.recv()

        if not raw:
            continue

        data = json.loads(raw)

        if data.get("error"):

            return data

        return data


# ============================================================
# GET 4H CANDLES
# ============================================================

def get_candles(ws, symbol):

    payload = {
        "ticks_history": symbol,
        "count": 20,
        "end": "latest",
        "style": "candles",
        "granularity": GRANULARITY
    }

    response = request(
        ws,
        payload
    )

    if response.get("error"):

        print(
            f"⚠️ {symbol}: "
            f"{response['error']}"
        )

        return []

    return response.get(
        "candles",
        []
    )


# ============================================================
# CONVERT CANDLE
# ============================================================

def convert_candle(raw):

    timestamp = int(
        raw["epoch"]
    )

    dt = datetime.fromtimestamp(
        timestamp,
        timezone.utc
    ).astimezone(WAT)

    return {
        "epoch": timestamp,
        "time": dt,
        "open": float(raw["open"]),
        "high": float(raw["high"]),
        "low": float(raw["low"]),
        "close": float(raw["close"])
    }


# ============================================================
# FIND CANDLE
# ============================================================

def find_candle(
    candles,
    target_date,
    target_hour
):

    for raw in candles:

        try:

            candle = convert_candle(raw)

        except Exception:

            continue

        if (
            candle["time"].date()
            == target_date
            and
            candle["time"].hour
            == target_hour
            and
            candle["time"].minute
            == 0
        ):

            return candle

    return None


# ============================================================
# CHECK BULLISH
# ============================================================

def bullish_setup(
    reference,
    confirmation
):

    # Confirmation must sweep
    # the complete reference LOW.

    low_swept = (
        confirmation["low"]
        <
        reference["low"]
    )

    # Confirmation must CLOSE
    # strictly ABOVE reference OPEN.

    close_above = (
        confirmation["close"]
        >
        reference["open"]
    )

    return (
        low_swept
        and
        close_above
    )


# ============================================================
# CHECK BEARISH
# ============================================================

def bearish_setup(
    reference,
    confirmation
):

    # Confirmation must sweep
    # the complete reference HIGH.

    high_swept = (
        confirmation["high"]
        >
        reference["high"]
    )

    # Confirmation must CLOSE
    # strictly BELOW reference OPEN.

    close_below = (
        confirmation["close"]
        <
        reference["open"]
    )

    return (
        high_swept
        and
        close_below
    )


# ============================================================
# SIGNAL MEMORY
# ============================================================

sent_signals = set()


# ============================================================
# FORMAT TELEGRAM SIGNAL
# ============================================================

def create_message(
    symbol,
    direction,
    reference,
    confirmation,
    entry_time
):

    if direction == "BUY":

        emoji = "🟢"

        setup_text = (
            "Confirmation swept the reference LOW "
            "and CLOSED ABOVE the reference OPEN."
        )

    else:

        emoji = "🔴"

        setup_text = (
            "Confirmation swept the reference HIGH "
            "and CLOSED BELOW the reference OPEN."
        )

    message = f"""
{emoji} SIXSGAMES SIGNAL

📊 Pair: {symbol}

🎯 Direction: {direction}

🕐 Reference: {reference['time'].strftime('%H:%M')} WAT
🕐 Confirmation: {confirmation['time'].strftime('%H:%M')} WAT

{setup_text}

📌 Reference Open:
{reference['open']}

📌 Reference High:
{reference['high']}

📌 Reference Low:
{reference['low']}

📌 Confirmation Close:
{confirmation['close']}

🎯 LOOK FOR ENTRY:
{entry_time} WAT

⚠️ Signal only.
No automatic trade.
"""

    return message.strip()


# ============================================================
# CHECK 10 AM SETUP
# ============================================================

def check_10am(
    symbol,
    candles,
    today
):

    reference = find_candle(
        candles,
        today,
        2
    )

    confirmation = find_candle(
        candles,
        today,
        6
    )

    if not reference or not confirmation:

        return

    # 06:00 candle must be completed.

    now = datetime.now(WAT)

    confirmation_end = (
        confirmation["time"]
        +
        timedelta(hours=4)
    )

    if now < confirmation_end:

        return


    # ========================================================
    # BULLISH
    # ========================================================

    if bullish_setup(
        reference,
        confirmation
    ):

        key = (
            symbol,
            today,
            "10AM",
            "BUY"
        )

        if key not in sent_signals:

            sent_signals.add(key)

            print(
                f"🟢 {symbol} "
                f"10AM BULLISH SETUP"
            )

            message = create_message(
                symbol,
                "BUY",
                reference,
                confirmation,
                "10:00"
            )

            send_telegram(
                message
            )

            return


    # ========================================================
    # BEARISH
    # ========================================================

    if bearish_setup(
        reference,
        confirmation
    ):

        key = (
            symbol,
            today,
            "10AM",
            "SELL"
        )

        if key not in sent_signals:

            sent_signals.add(key)

            print(
                f"🔴 {symbol} "
                f"10AM BEARISH SETUP"
            )

            message = create_message(
                symbol,
                "SELL",
                reference,
                confirmation,
                "10:00"
            )

            send_telegram(
                message
            )


# ============================================================
# CHECK 2 PM SETUP
# ============================================================

def check_2pm(
    symbol,
    candles,
    today
):

    reference = find_candle(
        candles,
        today,
        6
    )

    confirmation = find_candle(
        candles,
        today,
        10
    )

    if not reference or not confirmation:

        return

    # 10:00 candle must be completed.

    now = datetime.now(WAT)

    confirmation_end = (
        confirmation["time"]
        +
        timedelta(hours=4)
    )

    if now < confirmation_end:

        return


    # ========================================================
    # BULLISH
    # ========================================================

    if bullish_setup(
        reference,
        confirmation
    ):

        key = (
            symbol,
            today,
            "2PM",
            "BUY"
        )

        if key not in sent_signals:

            sent_signals.add(key)

            print(
                f"🟢 {symbol} "
                f"2PM BULLISH SETUP"
            )

            message = create_message(
                symbol,
                "BUY",
                reference,
                confirmation,
                "14:00"
            )

            send_telegram(
                message
            )

            return


    # ========================================================
    # BEARISH
    # ========================================================

    if bearish_setup(
        reference,
        confirmation
    ):

        key = (
            symbol,
            today,
            "2PM",
            "SELL"
        )

        if key not in sent_signals:

            sent_signals.add(key)

            print(
                f"🔴 {symbol} "
                f"2PM BEARISH SETUP"
            )

            message = create_message(
                symbol,
                "SELL",
                reference,
                confirmation,
                "14:00"
            )

            send_telegram(
                message
            )


# ============================================================
# SCAN EVERYTHING
# ============================================================

def scan():

    ws = None

    try:

        ws = connect()

        today = datetime.now(
            WAT
        ).date()

        print("")
        print("=" * 60)
        print(
            f"🔎 SCANNING "
            f"{len(MARKETS)} MARKETS"
        )
        print("=" * 60)

        for symbol in MARKETS:

            try:

                print(
                    f"🔍 Checking {symbol}..."
                )

                candles = get_candles(
                    ws,
                    symbol
                )

                if not candles:

                    print(
                        f"⚪ {symbol}: "
                        f"no candles"
                    )

                    continue

                check_10am(
                    symbol,
                    candles,
                    today
                )

                check_2pm(
                    symbol,
                    candles,
                    today
                )

            except Exception as e:

                print(
                    f"⚠️ {symbol}: {e}"
                )

        print("")
        print("✅ Scan complete.")

    except Exception as e:

        print("")
        print("❌ Scanner error:")
        print(str(e))

    finally:

        if ws:

            try:
                ws.close()

            except Exception:
                pass


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print(
        "🤖 SIXSGAMES LIVE TELEGRAM SCANNER"
    )
    print("=" * 60)

    print(
        f"📊 Markets: {len(MARKETS)}"
    )

    print(
        "⏱️ Timeframe: 4H"
    )

    print(
        "🌍 Timezone: Africa/Lagos"
    )

    print(
        "🎯 Entry windows: 10:00 and 14:00"
    )

    print("")

    # --------------------------------------------------------
    # Telegram configuration check
    # --------------------------------------------------------

    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ TELEGRAM_BOT_TOKEN is missing."
        )

        return

    if not TELEGRAM_CHAT_ID:

        print(
            "❌ TELEGRAM_CHAT_ID is missing."
        )

        return

    print(
        "✅ Telegram secrets detected."
    )

    # --------------------------------------------------------
    # Initial scan
    # --------------------------------------------------------

    scan()

    # --------------------------------------------------------
    # Continue scanning
    # --------------------------------------------------------

    while True:

        print("")
        print(
            f"😴 Waiting "
            f"{CHECK_INTERVAL} seconds..."
        )

        time.sleep(
            CHECK_INTERVAL
        )

        scan()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
