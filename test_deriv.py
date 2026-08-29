import json
import os
import requests
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES
# TODAY-ONLY 4H STRATEGY SCANNER
#
# CUSTOM 4H STRUCTURE BUILT FROM 1H CANDLES
#
# 02:00 -> 06:00 -> ENTRY 10:00
# 06:00 -> 10:00 -> ENTRY 14:00
#
# BULLISH:
# Confirmation LOW < Reference LOW
# AND
# Confirmation CLOSE > Reference OPEN
#
# BEARISH:
# Confirmation HIGH > Reference HIGH
# AND
# Confirmation CLOSE < Reference CLOSE
#
# IMPORTANT:
# - Reference candle direction does NOT matter.
# - Opposite-side sweep does NOT matter.
# - A candle may sweep both sides and still qualify.
# - Scanner checks TODAY ONLY.
# - Scanner runs ONCE and then STOPS.
# ============================================================


DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


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

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN is missing.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID is missing.")
        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
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

        if response.status_code == 200:

            data = response.json()

            if data.get("ok"):

                print("📨 Telegram signal sent successfully.")
                return True

        print(
            "⚠️ Telegram response:",
            response.text
        )

    except Exception as e:

        print(
            "❌ Telegram error:",
            str(e)
        )

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

    ws.send(
        json.dumps(payload)
    )

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

        "count": 120,

        "end": "latest",

        "granularity": 3600,

        "style": "candles"
    }

    response = request(
        ws,
        payload
    )

    if response.get("error"):

        print(
            f"   ❌ Deriv error: "
            f"{response['error']}"
        )

        return None

    candles = response.get(
        "candles",
        []
    )

    if not candles:

        return None

    return candles


# ============================================================
# CONVERT 1H CANDLE TO WAT
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

        "open": float(
            candle["open"]
        ),

        "high": float(
            candle["high"]
        ),

        "low": float(
            candle["low"]
        ),

        "close": float(
            candle["close"]
        )
    }


# ============================================================
# FIND 1H CANDLE
# ============================================================

def find_1h(
    candles,
    date_value,
    hour
):

    for candle in candles:

        if (
            candle["time"].date()
            == date_value
            and
            candle["time"].hour
            == hour
        ):

            return candle

    return None


# ============================================================
# BUILD ONE CUSTOM 4H CANDLE
#
# Example:
#
# 02:00 candle =
#
# 02:00
# 03:00
# 04:00
# 05:00
#
# Open  = 02:00 open
# High  = highest high
# Low   = lowest low
# Close = 05:00 close
#
# Therefore our custom candles really begin at:
#
# 02, 06, 10, 14, 18, 22
# ============================================================

def build_custom_candle(
    one_hour,
    date_value,
    start_hour
):

    hourly = []

    for offset in range(4):

        total_hour = (
            start_hour
            + offset
        )

        target_date = date_value

        if total_hour >= 24:

            total_hour -= 24

            target_date = (
                date_value
                + timedelta(days=1)
            )

        candle = find_1h(
            one_hour,
            target_date,
            total_hour
        )

        if candle is None:

            return None

        hourly.append(candle)


    return {

        "time": datetime(
            date_value.year,
            date_value.month,
            date_value.day,
            start_hour,
            tzinfo=WAT
        ),

        "open":
            hourly[0]["open"],

        "high":
            max(
                c["high"]
                for c in hourly
            ),

        "low":
            min(
                c["low"]
                for c in hourly
            ),

        "close":
            hourly[-1]["close"]
    }


# ============================================================
# BUILD ALL CUSTOM 4H CANDLES
# ============================================================

def build_custom_4h(
    one_hour,
    date_value
):

    result = []

    for start_hour in [
        2,
        6,
        10,
        14,
        18,
        22
    ]:

        candle = build_custom_candle(
            one_hour,
            date_value,
            start_hour
        )

        if candle:

            result.append(
                candle
            )

    return result


# ============================================================
# CHECK IF CUSTOM CANDLE IS COMPLETED
# ============================================================

def is_completed(candle):

    now = datetime.now(WAT)

    end_time = (
        candle["time"]
        + timedelta(hours=4)
    )

    return end_time <= now


# ============================================================
# BULLISH SETUP
#
# EXACT USER STRATEGY
#
# Confirmation LOW must sweep
# Reference LOW.
#
# Confirmation CLOSE must be
# ABOVE Reference OPEN.
#
# NOTHING ELSE MATTERS.
# ============================================================

def bullish_setup(
    reference,
    confirmation
):

    sweep_low = (
        confirmation["low"]
        < reference["low"]
    )

    close_above_open = (
        confirmation["close"]
        > reference["open"]
    )

    return (
        sweep_low
        and
        close_above_open
    )


# ============================================================
# BEARISH SETUP
#
# EXACT USER STRATEGY
#
# Confirmation HIGH must sweep
# Reference HIGH.
#
# Confirmation CLOSE must be
# BELOW Reference CLOSE.
#
# NOTHING ELSE MATTERS.
# ============================================================

def bearish_setup(
    reference,
    confirmation
):

    sweep_high = (
        confirmation["high"]
        > reference["high"]
    )

    close_below_close = (
        confirmation["close"]
        < reference["close"]
    )

    return (
        sweep_high
        and
        close_below_close
    )


# ============================================================
# CREATE SIGNAL
# ============================================================

def create_signal(
    symbol,
    date_value,
    reference_hour,
    confirmation_hour,
    entry_hour,
    direction,
    reference,
    confirmation
):

    return {

        "symbol": symbol,

        "date": date_value,

        "reference_hour":
            reference_hour,

        "confirmation_hour":
            confirmation_hour,

        "entry_hour":
            entry_hour,

        "direction":
            direction,

        "reference":
            reference,

        "confirmation":
            confirmation
    }


# ============================================================
# SCAN TODAY
# ============================================================

def scan_today(
    symbol,
    one_hour
):

    today = datetime.now(
        WAT
    ).date()

    custom = build_custom_4h(
        one_hour,
        today
    )


    completed = [

        candle

        for candle in custom

        if is_completed(candle)
    ]


    print(
        f"   🕯️ Completed custom candles today: "
        f"{len(completed)}"
    )


    signals = []


    # ========================================================
    # SETUP 1
    #
    # 02 → 06 → ENTRY 10
    # ========================================================

    candle_02 = next(
        (
            c for c in completed
            if c["time"].hour == 2
        ),
        None
    )

    candle_06 = next(
        (
            c for c in completed
            if c["time"].hour == 6
        ),
        None
    )


    if candle_02 and candle_06:

        # BUY

        if bullish_setup(
            candle_02,
            candle_06
        ):

            signals.append(
                create_signal(
                    symbol,
                    today,
                    2,
                    6,
                    10,
                    "BUY",
                    candle_02,
                    candle_06
                )
            )


        # SELL

        if bearish_setup(
            candle_02,
            candle_06
        ):

            signals.append(
                create_signal(
                    symbol,
                    today,
                    2,
                    6,
                    10,
                    "SELL",
                    candle_02,
                    candle_06
                )
            )


    # ========================================================
    # SETUP 2
    #
    # 06 → 10 → ENTRY 14
    # ========================================================

    candle_10 = next(
        (
            c for c in completed
            if c["time"].hour == 10
        ),
        None
    )

    if candle_06 and candle_10:

        # BUY

        if bullish_setup(
            candle_06,
            candle_10
        ):

            signals.append(
                create_signal(
                    symbol,
                    today,
                    6,
                    10,
                    14,
                    "BUY",
                    candle_06,
                    candle_10
                )
            )


        # SELL

        if bearish_setup(
            candle_06,
            candle_10
        ):

            signals.append(
                create_signal(
                    symbol,
                    today,
                    6,
                    10,
                    14,
                    "SELL",
                    candle_06,
                    candle_10
                )
            )


    return signals


# ============================================================
# PRINT SIGNAL
# ============================================================

def print_signal(signal):

    ref = signal["reference"]

    conf = signal["confirmation"]


    print("")
    print("=" * 70)

    print(
        "🚨 VALID SIXSGAMES SIGNAL"
    )

    print("=" * 70)

    print(
        f"📊 Market: "
        f"{signal['symbol']}"
    )

    print(
        f"📅 Date: "
        f"{signal['date']}"
    )

    print(
        f"🎯 Direction: "
        f"{signal['direction']}"
    )

    print(
        f"🕐 Reference: "
        f"{signal['reference_hour']:02d}:00 WAT"
    )

    print(
        f"🕐 Confirmation: "
        f"{signal['confirmation_hour']:02d}:00 WAT"
    )

    print(
        f"🎯 ENTRY: "
        f"{signal['entry_hour']:02d}:00 WAT"
    )

    print("")
    print("REFERENCE CANDLE")

    print(
        f"Open : {ref['open']}"
    )

    print(
        f"High : {ref['high']}"
    )

    print(
        f"Low  : {ref['low']}"
    )

    print(
        f"Close: {ref['close']}"
    )

    print("")
    print("CONFIRMATION CANDLE")

    print(
        f"Open : {conf['open']}"
    )

    print(
        f"High : {conf['high']}"
    )

    print(
        f"Low  : {conf['low']}"
    )

    print(
        f"Close: {conf['close']}"
    )

    print("")
    print("=" * 70)


# ============================================================
# TELEGRAM FORMAT
# ============================================================

def telegram_message(signal):

    ref = signal["reference"]

    conf = signal["confirmation"]

    if signal["direction"] == "BUY":

        direction = "🟢 BUY"

    else:

        direction = "🔴 SELL"


    return (
        "🚨 SIXSGAMES SIGNAL 🚨\n"
        "\n"
        f"📊 Market: {signal['symbol']}\n"
        f"📅 Date: {signal['date']}\n"
        f"🎯 Direction: {direction}\n"
        "\n"
        f"🕐 Reference: "
        f"{signal['reference_hour']:02d}:00 WAT\n"
        f"   Open: {ref['open']}\n"
        f"   High: {ref['high']}\n"
        f"   Low: {ref['low']}\n"
        f"   Close: {ref['close']}\n"
        "\n"
        f"🕐 Confirmation: "
        f"{signal['confirmation_hour']:02d}:00 WAT\n"
        f"   Open: {conf['open']}\n"
        f"   High: {conf['high']}\n"
        f"   Low: {conf['low']}\n"
        f"   Close: {conf['close']}\n"
        "\n"
        f"🎯 ENTRY: "
        f"{signal['entry_hour']:02d}:00 WAT\n"
        "\n"
        "✅ Sweep condition confirmed\n"
        "✅ Close condition confirmed\n"
        "\n"
        "👀 LOOK FOR YOUR ENTRY."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)

    print(
        "🤖 SIXSGAMES TODAY-ONLY 4H SCANNER"
    )

    print("=" * 70)

    now = datetime.now(WAT)

    print(
        f"🕐 Current WAT time: "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print(
        f"📅 Scanning TODAY ONLY: "
        f"{now.date()}"
    )

    print(
        "🕯️ Custom structure: "
        "02 → 06 → 10 → 14"
    )

    print(
        "🟢 BUY: sweep LOW + close > reference OPEN"
    )

    print(
        "🔴 SELL: sweep HIGH + close < reference CLOSE"
    )

    print(
        f"📊 Markets: {len(MARKETS)}"
    )

    print("=" * 70)


    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ Telegram bot token missing."
        )

        return


    if not TELEGRAM_CHAT_ID:

        print(
            "❌ Telegram chat ID missing."
        )

        return


    print(
        "✅ Telegram secrets detected."
    )


    ws = None

    total_signals = 0

    telegram_sent = 0


    try:

        ws = connect()


        print("")
        print("=" * 70)

        print(
            "🔎 STARTING TODAY-ONLY 42-MARKET SCAN"
        )

        print("=" * 70)


        for symbol in MARKETS:

            print("")
            print(
                f"🔍 Checking {symbol}..."
            )

            try:

                raw = get_1h_candles(
                    ws,
                    symbol
                )

                if not raw:

                    print(
                        "   ⚠️ No candles returned."
                    )

                    continue


                one_hour = []

                for candle in raw:

                    try:

                        one_hour.append(
                            convert_candle(
                                candle
                            )
                        )

                    except Exception:

                        continue


                signals = scan_today(
                    symbol,
                    one_hour
                )


                if not signals:

                    print(
                        "   ⚪ No valid setup."
                    )

                    continue


                print(
                    f"   🚨 "
                    f"{len(signals)} VALID SETUP(S)!"
                )


                for signal in signals:

                    total_signals += 1

                    print_signal(
                        signal
                    )


                    message = telegram_message(
                        signal
                    )


                    if send_telegram(
                        message
                    ):

                        telegram_sent += 1


            except Exception as e:

                print(
                    f"   ⚠️ Error: {e}"
                )


        print("")
        print("=" * 70)

        print(
            "📊 FINAL SCAN SUMMARY"
        )

        print("=" * 70)

        print(
            f"📊 Markets checked: "
            f"{len(MARKETS)}"
        )

        print(
            f"🚨 Valid setups found: "
            f"{total_signals}"
        )

        print(
            f"📨 Telegram signals sent: "
            f"{telegram_sent}"
        )

        print("")
        print(
            "✅ SCAN FINISHED."
        )

        print(
            "🛑 Scanner stopped."
        )

        print(
            "💡 Run the GitHub Action manually "
            "again whenever you want to scan."
        )

        print("=" * 70)


    except Exception as e:

        print("")
        print("=" * 70)

        print(
            "❌ SCANNER ERROR"
        )

        print("=" * 70)

        print(
            str(e)
        )


    finally:

        if ws:

            try:

                ws.close()

                print(
                    "🔌 Deriv connection closed."
                )

            except Exception:

                pass


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
