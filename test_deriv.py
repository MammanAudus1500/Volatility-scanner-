import json
import os
import time
import requests
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES - STRICT 1H -> CUSTOM 4H SCANNER
# ============================================================
#
# CUSTOM 4H CANDLES:
#
# 02:00 candle = 02,03,04,05
# 06:00 candle = 06,07,08,09
# 10:00 candle = 10,11,12,13
# 14:00 candle = 14,15,16,17
#
# STRATEGY:
#
# BUY:
# confirmation LOW < reference LOW
# AND
# confirmation CLOSE > reference OPEN
#
# SELL:
# confirmation HIGH > reference HIGH
# AND
# confirmation CLOSE < reference OPEN
#
# If the confirmation candle sweeps BOTH sides:
# direction is decided ONLY by the CLOSE relative
# to the reference OPEN.
#
# If close == reference open:
# NO SIGNAL.
#
# IMPORTANT:
# - Uses TODAY automatically.
# - Does NOT search previous months.
# - Scans once and stops.
# - Checks both:
#       02 -> 06 -> ENTRY 10
#       06 -> 10 -> ENTRY 14
# - Does NOT require reference candle to be bullish/bearish.
# ============================================================


DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

GRANULARITY_1H = 3600

# Number of 1H candles requested.
# Enough to cover today and a little history for safety.
CANDLE_COUNT = 72


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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram secrets not available.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
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

        if response.ok:

            print("📨 Telegram signal sent successfully.")

            return True

        print(
            f"⚠️ Telegram error: "
            f"{response.status_code} "
            f"{response.text}"
        )

        return False

    except Exception as e:

        print(
            f"⚠️ Telegram connection error: {e}"
        )

        return False


# ============================================================
# DERIV CONNECTION
# ============================================================

def connect_deriv():

    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        DERIV_URL,
        timeout=20
    )

    print("✅ Connected successfully!")

    return ws


# ============================================================
# REQUEST
# ============================================================

def request(ws, payload):

    ws.send(json.dumps(payload))

    while True:

        raw = ws.recv()

        if not raw:
            continue

        data = json.loads(raw)

        if "error" in data:
            return data

        return data


# ============================================================
# GET 1H CANDLES
# ============================================================

def get_1h_candles(ws, symbol):

    payload = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": CANDLE_COUNT,
        "end": "latest",
        "granularity": GRANULARITY_1H,
        "style": "candles"
    }

    response = request(
        ws,
        payload
    )

    if response.get("error"):

        return None, response["error"]

    candles = response.get(
        "candles",
        []
    )

    if not candles:

        return None, {
            "message": "No candles returned"
        }

    return candles, None


# ============================================================
# CONVERT 1H CANDLE
# ============================================================

def convert_candle(candle):

    timestamp = int(
        candle["epoch"]
    )

    dt = datetime.fromtimestamp(
        timestamp,
        timezone.utc
    ).astimezone(WAT)

    return {
        "time": dt,
        "open": float(candle["open"]),
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "close": float(candle["close"])
    }


# ============================================================
# CHECK IF 1H CANDLE IS COMPLETED
# ============================================================

def is_completed(candle, now):

    end_time = (
        candle["time"] +
        timedelta(hours=1)
    )

    return end_time <= now


# ============================================================
# FIND EXACT 1H CANDLE
# ============================================================

def find_hour(candles, date_value, hour):

    for candle in candles:

        if (
            candle["time"].date() == date_value
            and candle["time"].hour == hour
        ):
            return candle

    return None


# ============================================================
# BUILD CUSTOM 4H CANDLE
# ============================================================
#
# start 02:
#   02,03,04,05
#
# start 06:
#   06,07,08,09
#
# start 10:
#   10,11,12,13
#
# start 14:
#   14,15,16,17
#
# OHLC:
# Open  = first candle open
# High  = highest high
# Low   = lowest low
# Close = last candle close
# ============================================================

def build_custom_4h(candles, date_value, start_hour):

    hours = [
        start_hour,
        start_hour + 1,
        start_hour + 2,
        start_hour + 3
    ]

    parts = []

    for hour in hours:

        candle = find_hour(
            candles,
            date_value,
            hour
        )

        if candle is None:
            return None

        parts.append(candle)

    custom = {
        "time": datetime(
            date_value.year,
            date_value.month,
            date_value.day,
            start_hour,
            0,
            tzinfo=WAT
        ),

        "open": parts[0]["open"],

        "high": max(
            x["high"]
            for x in parts
        ),

        "low": min(
            x["low"]
            for x in parts
        ),

        "close": parts[-1]["close"],

        "parts": parts
    }

    return custom


# ============================================================
# STRICT SETUP CHECK
# ============================================================

def check_setup(reference, confirmation):

    # --------------------------------------------------------
    # BUY CONDITIONS
    # --------------------------------------------------------

    buy_sweep = (
        confirmation["low"] <
        reference["low"]
    )

    buy_close = (
        confirmation["close"] >
        reference["open"]
    )

    buy_valid = (
        buy_sweep and
        buy_close
    )


    # --------------------------------------------------------
    # SELL CONDITIONS
    # --------------------------------------------------------

    sell_sweep = (
        confirmation["high"] >
        reference["high"]
    )

    sell_close = (
        confirmation["close"] <
        reference["open"]
    )

    sell_valid = (
        sell_sweep and
        sell_close
    )


    # --------------------------------------------------------
    # BOTH COMPLETE CONDITIONS
    # --------------------------------------------------------
    #
    # This should mathematically be impossible because
    # the same close cannot be both above and below the
    # reference open.
    #
    # Nevertheless, we explicitly reject it.
    # --------------------------------------------------------

    if buy_valid and sell_valid:

        return {
            "direction": None,
            "status": "AMBIGUOUS",
            "buy_sweep": buy_sweep,
            "buy_close": buy_close,
            "sell_sweep": sell_sweep,
            "sell_close": sell_close
        }


    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if buy_valid:

        return {
            "direction": "BUY",
            "status": "VALID",
            "buy_sweep": buy_sweep,
            "buy_close": buy_close,
            "sell_sweep": sell_sweep,
            "sell_close": sell_close
        }


    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    if sell_valid:

        return {
            "direction": "SELL",
            "status": "VALID",
            "buy_sweep": buy_sweep,
            "buy_close": buy_close,
            "sell_sweep": sell_sweep,
            "sell_close": sell_close
        }


    # --------------------------------------------------------
    # NO SETUP
    # --------------------------------------------------------

    return {
        "direction": None,
        "status": "NO_SETUP",
        "buy_sweep": buy_sweep,
        "buy_close": buy_close,
        "sell_sweep": sell_sweep,
        "sell_close": sell_close
    }


# ============================================================
# PRINT CANDLE
# ============================================================

def print_candle(label, candle):

    print("")
    print(label)

    print(
        f"   Open : {candle['open']}"
    )

    print(
        f"   High : {candle['high']}"
    )

    print(
        f"   Low  : {candle['low']}"
    )

    print(
        f"   Close: {candle['close']}"
    )


# ============================================================
# CREATE TELEGRAM SIGNAL
# ============================================================

def create_signal_message(
    symbol,
    date_value,
    reference_hour,
    confirmation_hour,
    entry_hour,
    direction,
    reference,
    confirmation
):

    if direction == "BUY":

        emoji = "🟢"
        word = "BUY"

    else:

        emoji = "🔴"
        word = "SELL"


    message = f"""
🚨 SIXSGAMES SIGNAL 🚨

📊 Market: {symbol}
📅 Date: {date_value}

🎯 Direction: {emoji} {word}

🕐 Reference: {reference_hour:02d}:00 WAT
🕐 Confirmation: {confirmation_hour:02d}:00 WAT
🎯 ENTRY: {entry_hour:02d}:00 WAT

✅ Sweep confirmed
✅ Close condition confirmed

📌 REFERENCE CANDLE
Open: {reference['open']}
High: {reference['high']}
Low: {reference['low']}
Close: {reference['close']}

📌 CONFIRMATION CANDLE
Open: {confirmation['open']}
High: {confirmation['high']}
Low: {confirmation['low']}
Close: {confirmation['close']}

👀 LOOK FOR YOUR ENTRY.
""".strip()

    return message


# ============================================================
# SCAN TODAY FOR ONE MARKET
# ============================================================

def scan_today(
    ws,
    symbol,
    today,
    now
):

    raw_candles, error = get_1h_candles(
        ws,
        symbol
    )

    if error:

        print(
            f"⚠️ {symbol} candle error: {error}"
        )

        return []


    converted = []

    for raw in raw_candles:

        try:

            candle = convert_candle(
                raw
            )

            if is_completed(
                candle,
                now
            ):

                converted.append(
                    candle
                )

        except Exception:

            continue


    # ========================================================
    # BUILD TODAY'S CUSTOM CANDLES
    # ========================================================

    candle_02 = build_custom_4h(
        converted,
        today,
        2
    )

    candle_06 = build_custom_4h(
        converted,
        today,
        6
    )

    candle_10 = build_custom_4h(
        converted,
        today,
        10
    )

    candle_14 = build_custom_4h(
        converted,
        today,
        14
    )


    print("")
    print(
        f"📅 TODAY: {today}"
    )

    print(
        f"   02:00 custom 4H: "
        f"{'✅' if candle_02 else '❌'}"
    )

    print(
        f"   06:00 custom 4H: "
        f"{'✅' if candle_06 else '❌'}"
    )

    print(
        f"   10:00 custom 4H: "
        f"{'✅' if candle_10 else '❌'}"
    )

    print(
        f"   14:00 custom 4H: "
        f"{'✅' if candle_14 else '❌'}"
    )


    signals = []


    # ========================================================
    # SETUP 1
    #
    # 02 -> 06 -> ENTRY 10
    # ========================================================

    if candle_02 and candle_06:

        print("")
        print(
            "🧪 TESTING 02:00 → 06:00 → 10:00"
        )

        result = check_setup(
            candle_02,
            candle_06
        )

        print(
            f"   BUY sweep: "
            f"{'✅' if result['buy_sweep'] else '❌'}"
        )

        print(
            f"   BUY close > 02 open: "
            f"{'✅' if result['buy_close'] else '❌'}"
        )

        print(
            f"   SELL sweep: "
            f"{'✅' if result['sell_sweep'] else '❌'}"
        )

        print(
            f"   SELL close < 02 open: "
            f"{'✅' if result['sell_close'] else '❌'}"
        )


        if result["status"] == "VALID":

            print("")
            print(
                f"🚨 {result['direction']} SETUP FOUND"
            )

            print(
                "🎯 ENTRY: 10:00 WAT"
            )

            print_candle(
                "📌 REFERENCE 02:00",
                candle_02
            )

            print_candle(
                "📌 CONFIRMATION 06:00",
                candle_06
            )


            signals.append({
                "symbol": symbol,
                "date": today,
                "reference_hour": 2,
                "confirmation_hour": 6,
                "entry_hour": 10,
                "direction": result["direction"],
                "reference": candle_02,
                "confirmation": candle_06
            })


        elif result["status"] == "AMBIGUOUS":

            print(
                "⚪ AMBIGUOUS → NO SIGNAL"
            )

        else:

            print(
                "⚪ No valid 10:00 setup."
            )


    else:

        print("")
        print(
            "⚪ 02 → 06 setup cannot be tested yet."
        )


    # ========================================================
    # SETUP 2
    #
    # 06 -> 10 -> ENTRY 14
    # ========================================================

    if candle_06 and candle_10:

        print("")
        print(
            "🧪 TESTING 06:00 → 10:00 → 14:00"
        )

        result = check_setup(
            candle_06,
            candle_10
        )

        print(
            f"   BUY sweep: "
            f"{'✅' if result['buy_sweep'] else '❌'}"
        )

        print(
            f"   BUY close > 06 open: "
            f"{'✅' if result['buy_close'] else '❌'}"
        )

        print(
            f"   SELL sweep: "
            f"{'✅' if result['sell_sweep'] else '❌'}"
        )

        print(
            f"   SELL close < 06 open: "
            f"{'✅' if result['sell_close'] else '❌'}"
        )


        if result["status"] == "VALID":

            print("")
            print(
                f"🚨 {result['direction']} SETUP FOUND"
            )

            print(
                "🎯 ENTRY: 14:00 WAT"
            )

            print_candle(
                "📌 REFERENCE 06:00",
                candle_06
            )

            print_candle(
                "📌 CONFIRMATION 10:00",
                candle_10
            )


            signals.append({
                "symbol": symbol,
                "date": today,
                "reference_hour": 6,
                "confirmation_hour": 10,
                "entry_hour": 14,
                "direction": result["direction"],
                "reference": candle_06,
                "confirmation": candle_10
            })


        elif result["status"] == "AMBIGUOUS":

            print(
                "⚪ AMBIGUOUS → NO SIGNAL"
            )

        else:

            print(
                "⚪ No valid 14:00 setup."
            )


    else:

        print("")
        print(
            "⚪ 06 → 10 setup cannot be tested yet."
        )


    return signals


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("🤖 SIXSGAMES STRICT 1H → CUSTOM 4H SCANNER")
    print("=" * 70)

    now = datetime.now(WAT)

    today = now.date()

    print(
        f"🕐 Current WAT time: "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print(
        f"📅 Automatic scan date: {today}"
    )

    print(
        "⏱️ Custom candles: 02 / 06 / 10 / 14 WAT"
    )

    print(
        "🎯 Entry windows: 10:00 and 14:00 WAT"
    )

    print(
        "🔎 Scan mode: TODAY ONLY"
    )

    print(
        "🛑 Run mode: ONE SCAN THEN STOP"
    )


    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:

        print(
            "✅ Telegram secrets detected."
        )

    else:

        print(
            "⚠️ Telegram secrets missing."
        )


    ws = None

    total_signals = []

    try:

        ws = connect_deriv()

        print("")
        print("=" * 70)
        print("🔎 SCANNING ALL 42 MARKETS")
        print("=" * 70)


        for index, symbol in enumerate(
            MARKETS,
            start=1
        ):

            print("")
            print(
                f"[{index}/{len(MARKETS)}] "
                f"🔍 CHECKING {symbol}"
            )

            try:

                signals = scan_today(
                    ws,
                    symbol,
                    today,
                    now
                )

                for signal in signals:

                    total_signals.append(
                        signal
                    )


                    message = create_signal_message(
                        symbol=signal["symbol"],
                        date_value=signal["date"],
                        reference_hour=signal["reference_hour"],
                        confirmation_hour=signal["confirmation_hour"],
                        entry_hour=signal["entry_hour"],
                        direction=signal["direction"],
                        reference=signal["reference"],
                        confirmation=signal["confirmation"]
                    )

                    send_telegram(
                        message
                    )


            except Exception as e:

                print(
                    f"⚠️ Error scanning "
                    f"{symbol}: {e}"
                )

                continue


        # ====================================================
        # FINAL SUMMARY
        # ====================================================

        print("")
        print("=" * 70)
        print("📊 FINAL SCAN SUMMARY")
        print("=" * 70)

        print(
            f"📅 Date scanned: {today}"
        )

        print(
            f"📊 Markets checked: {len(MARKETS)}"
        )

        print(
            f"🚨 Valid setups: {len(total_signals)}"
        )


        if total_signals:

            print("")
            print(
                "🚨 VALID SETUPS FO
