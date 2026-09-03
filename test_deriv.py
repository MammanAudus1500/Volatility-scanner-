import json
import os
import requests
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES
# TODAY-ONLY, TIME-AWARE 4H SCANNER
#
# CUSTOM 4H CANDLES ARE BUILT FROM 1H CANDLES
#
# ENTRY WINDOW 1:
# 10:00 ENTRY
# Reference:    02:00
# Confirmation: 06:00
#
# ENTRY WINDOW 2:
# 14:00 ENTRY
# Reference:    06:00
# Confirmation: 10:00
#
# IMPORTANT:
# The scanner ONLY checks the setup belonging to the
# CURRENT entry window.
#
# 10:05 -> ONLY 02 -> 06 -> 10
# 14:05 -> ONLY 06 -> 10 -> 14
#
# BUY:
# confirmation LOW < reference LOW
# AND
# confirmation CLOSE > reference OPEN
#
# SELL:
# confirmation HIGH > reference HIGH
# AND
# confirmation CLOSE < reference CLOSE
#
# Opposite-side sweep does NOT matter.
# Reference candle direction does NOT matter.
#
# Scanner runs ONCE and stops.
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

    try:

        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=15
        )

        if response.status_code == 200:

            data = response.json()

            if data.get("ok"):

                print("📨 Telegram signal sent.")
                return True

        print("⚠️ Telegram response:")
        print(response.text)

    except Exception as e:

        print("❌ Telegram error:", e)

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

    response = request(
        ws,
        {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": 120,
            "end": "latest",
            "granularity": 3600,
            "style": "candles"
        }
    )

    if response.get("error"):

        print(
            f"   ❌ Deriv error: "
            f"{response['error']}"
        )

        return None

    candles = response.get("candles", [])

    if not candles:
        return None

    return candles


# ============================================================
# CONVERT CANDLE TO WAT
# ============================================================

def convert_candle(candle):

    timestamp = int(candle["epoch"])

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
# FIND 1H CANDLE
# ============================================================

def find_1h(candles, date_value, hour):

    for candle in candles:

        if (
            candle["time"].date() == date_value
            and
            candle["time"].hour == hour
        ):

            return candle

    return None


# ============================================================
# BUILD CUSTOM 4H CANDLE
#
# 02:00 custom candle:
# 02 + 03 + 04 + 05
#
# 06:00 custom candle:
# 06 + 07 + 08 + 09
#
# 10:00 custom candle:
# 10 + 11 + 12 + 13
#
# 14:00 custom candle:
# 14 + 15 + 16 + 17
# ============================================================

def build_custom_candle(
    one_hour,
    date_value,
    start_hour
):

    hourly = []

    for offset in range(4):

        hour = start_hour + offset

        target_date = date_value

        if hour >= 24:

            hour -= 24

            target_date = (
                date_value + timedelta(days=1)
            )

        candle = find_1h(
            one_hour,
            target_date,
            hour
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

        "open": hourly[0]["open"],

        "high": max(
            candle["high"]
            for candle in hourly
        ),

        "low": min(
            candle["low"]
            for candle in hourly
        ),

        "close": hourly[-1]["close"]
    }


# ============================================================
# BUILD CUSTOM 4H CANDLE
# ============================================================

def build_candle(
    one_hour,
    date_value,
    hour
):

    return build_custom_candle(
        one_hour,
        date_value,
        hour
    )


# ============================================================
# CHECK CANDLE COMPLETED
# ============================================================

def candle_completed(
    date_value,
    start_hour
):

    now = datetime.now(WAT)

    end_time = datetime(
        date_value.year,
        date_value.month,
        date_value.day,
        start_hour,
        tzinfo=WAT
    ) + timedelta(hours=4)

    return now >= end_time


# ============================================================
# DETERMINE CURRENT ENTRY WINDOW
#
# This is the IMPORTANT part.
#
# 10:05 -> window 10
# 14:05 -> window 14
#
# Other times -> no scan
# ============================================================

def get_current_window():

    now = datetime.now(WAT)

    hour = now.hour
    minute = now.minute

    current_minutes = (
        hour * 60 + minute
    )

    # --------------------------------------------------------
    # 10:00 ENTRY WINDOW
    #
    # We only allow scanning from 10:00 until 13:59.
    #
    # Reference = 02
    # Confirmation = 06
    # Entry = 10
    # --------------------------------------------------------

    if 10 * 60 <= current_minutes < 14 * 60:

        return {
            "reference_hour": 2,
            "confirmation_hour": 6,
            "entry_hour": 10
        }

    # --------------------------------------------------------
    # 14:00 ENTRY WINDOW
    #
    # From 14:00 until midnight.
    #
    # Reference = 06
    # Confirmation = 10
    # Entry = 14
    # --------------------------------------------------------

    if current_minutes >= 14 * 60:

        return {
            "reference_hour": 6,
            "confirmation_hour": 10,
            "entry_hour": 14
        }

    # --------------------------------------------------------
    # AFTER MIDNIGHT BEFORE 02/06/10:
    #
    # There is no new setup to check.
    # --------------------------------------------------------

    return None


# ============================================================
# CHECK BUY
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
# CHECK SELL
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

def make_signal(
    symbol,
    date_value,
    window,
    direction,
    reference,
    confirmation
):

    return {
        "symbol": symbol,
        "date": date_value,
        "reference_hour": window["reference_hour"],
        "confirmation_hour": window["confirmation_hour"],
        "entry_hour": window["entry_hour"],
        "direction": direction,
        "reference": reference,
        "confirmation": confirmation
    }


# ============================================================
# SCAN ONE MARKET
# ============================================================

def scan_market(
    symbol,
    one_hour,
    date_value,
    window
):

    reference_hour = window["reference_hour"]
    confirmation_hour = window["confirmation_hour"]

    reference = build_candle(
        one_hour,
        date_value,
        reference_hour
    )

    confirmation = build_candle(
        one_hour,
        date_value,
        confirmation_hour
    )

    if reference is None:

        print(
            f"   ⚠️ {reference_hour:02d}:00 "
            "reference candle unavailable."
        )

        return []

    if confirmation is None:

        print(
            f"   ⚠️ {confirmation_hour:02d}:00 "
            "confirmation candle unavailable."
        )

        return []

    # Make sure confirmation candle is COMPLETE.

    if not candle_completed(
        date_value,
        confirmation_hour
    ):

        print(
            f"   ⏳ {confirmation_hour:02d}:00 "
            "confirmation candle is not complete."
        )

        return []

    print("")
    print(
        f"   🕐 {reference_hour:02d}:00 REFERENCE"
    )

    print(
        f"      Open : {reference['open']}"
    )

    print(
        f"      High : {reference['high']}"
    )

    print(
        f"      Low  : {reference['low']}"
    )

    print(
        f"      Close: {reference['close']}"
    )

    print("")
    print(
        f"   🕐 {confirmation_hour:02d}:00 CONFIRMATION"
    )

    print(
        f"      Open : {confirmation['open']}"
    )

    print(
        f"      High : {confirmation['high']}"
    )

    print(
        f"      Low  : {confirmation['low']}"
    )

    print(
        f"      Close: {confirmation['close']}"
    )

    print("")

    buy_sweep = (
        confirmation["low"]
        < reference["low"]
    )

    buy_close = (
        confirmation["close"]
        > reference["open"]
    )

    sell_sweep = (
        confirmation["high"]
        > reference["high"]
    )

    sell_close = (
        confirmation["close"]
        < reference["close"]
    )

    print(
        f"   🟢 BUY sweep low: "
        f"{'✅' if buy_sweep else '❌'}"
    )

    print(
        f"   🟢 BUY close > reference OPEN: "
        f"{'✅' if buy_close else '❌'}"
    )

    print(
        f"   🔴 SELL sweep high: "
        f"{'✅' if sell_sweep else '❌'}"
    )

    print(
        f"   🔴 SELL close < reference CLOSE: "
        f"{'✅' if sell_close else '❌'}"
    )

    signals = []

    # BUY

    if buy_sweep and buy_close:

        signals.append(
            make_signal(
                symbol,
                date_value,
                window,
                "BUY",
                reference,
                confirmation
            )
        )

    # SELL

    if sell_sweep and sell_close:

        signals.append(
            make_signal(
                symbol,
                date_value,
                window,
                "SELL",
                reference,
                confirmation
            )
        )

    return signals


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def format_telegram(signal):

    ref = signal["reference"]
    conf = signal["confirmation"]

    direction = (
        "🟢 BUY"
        if signal["direction"] == "BUY"
        else "🔴 SELL"
    )

    return (
        "🚨 SIXSGAMES SIGNAL 🚨\n"
        "\n"
        f"📊 Market: {signal['symbol']}\n"
        f"📅 Date: {signal['date']}\n"
        f"🎯 Direction: {direction}\n"
        "\n"
        f"🕐 Reference: "
        f"{signal['reference_hour']:02d}:00 WAT\n"
        f"   Open : {ref['open']}\n"
        f"   High : {ref['high']}\n"
        f"   Low  : {ref['low']}\n"
        f"   Close: {ref['close']}\n"
        "\n"
        f"🕐 Confirmation: "
        f"{signal['confirmation_hour']:02d}:00 WAT\n"
        f"   Open : {conf['open']}\n"
        f"   High : {conf['high']}\n"
        f"   Low  : {conf['low']}\n"
        f"   Close: {conf['close']}\n"
        "\n"
        f"🎯 ENTRY: "
        f"{signal['entry_hour']:02d}:00 WAT\n"
        "\n"
        "✅ Sweep confirmed\n"
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
        "🤖 SIXSGAMES TIME-AWARE 4H SCANNER"
    )

    print("=" * 70)

    now = datetime.now(WAT)

    print(
        f"🕐 Current WAT time: "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print(
        f"📅 Today: {now.date()}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # DETERMINE WHICH SETUP TO CHECK
    # --------------------------------------------------------

    window = get_current_window()

    if window is None:

        print("")
        print(
            "⏳ There is no active entry window right now."
        )

        print("")
        print(
            "Allowed scans:"
        )

        print(
            "10:00 → 13:59 WAT = 02 → 06 → 10"
        )

        print(
            "14:00 → 23:59 WAT = 06 → 10 → 14"
        )

        print("")
        print(
            "🛑 Scanner stopped."
        )

        return


    print(
        f"🎯 CURRENT ENTRY WINDOW: "
        f"{window['entry_hour']:02d}:00 WAT"
    )

    print(
        f"🕐 Reference: "
        f"{window['reference_hour']:02d}:00 WAT"
    )

    print(
        f"🕐 Confirmation: "
        f"{window['confirmation_hour']:02d}:00 WAT"
    )

    print(
        f"🎯 Entry: "
        f"{window['entry_hour']:02d}:00 WAT"
    )

    print("")
    print(
        "⚠️ IMPORTANT: Only this setup will be checked."
    )

    print(
        "⚠️ Previous entry windows will NOT be checked."
    )

    print(
        "⚠️ Previous dates will NOT be checked."
    )

    print("=" * 70)


    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ TELEGRAM_BOT_TOKEN missing."
        )

        return

    if not TELEGRAM_CHAT_ID:

        print(
            "❌ TELEGRAM_CHAT_ID missing."
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
            "🔎 SCANNING 42 MARKETS"
        )

        print("=" * 70)


        today = datetime.now(WAT).date()


        for symbol in MARKETS:

            print("")
            print(
                f"🔍 Checking {symbol}"
            )

            try:

                raw = get_1h_candles(
                    ws,
                    symbol
                )

                if not raw:

                    print(
                        "   ⚠️ No candle data."
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

                    except Exception as e:

                        print(
                            f"   ⚠️ Candle conversion error: {e}"
                        )


                signals = scan_market(
                    symbol,
                    one_hour,
                    today,
                    window
                )


                if not signals:

                    print(
                        "   ⚪ No valid setup."
                    )

                    continue


                print("")
                print(
                    f"   🚨 VALID SETUPS: "
                    f"{len(signals)}"
                )


                for signal in signals:

                    total_signals += 1

                    print("")
                    print(
                        "=" * 70
                    )

                    print(
                        "🚨 SIXSGAMES VALID SIGNAL"
                    )

                    print(
                        "=" * 70
                    )

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
                        f"{signal['reference_hour']:02d}:00"
                    )

                    print(
                        f"🕐 Confirmation: "
                        f"{signal['confirmation_hour']:02d}:00"
                    )

                    print(
                        f"🎯 ENTRY: "
                        f"{signal['entry_hour']:02d}:00 WAT"
                    )

                    print(
                        "=" * 70
                    )


                    message = format_telegram(
                        signal
                    )

                    if send_telegram(
                        message
                    ):

                        telegram_sent += 1


            except Exception as e:

                print(
                    f"   ⚠️ Error checking "
                    f"{symbol}: {e}"
                )


        print("")
        print("=" * 70)

        print(
            "📊 FINAL SCAN SUMMARY"
        )

        print("=" * 70)

        print(
            f"📅 Date checked: {today}"
        )

        print(
            f"🎯 Entry window checked: "
            f"{window['entry_hour']:02d}:00 WAT"
        )

        print(
            f"🕐 Setup checked: "
            f"{window['reference_hour']:02d}:00 → "
            f"{window['confirmation_hour']:02d}:00 → "
            f"{window['entry_hour']:02d}:00"
        )

        print(
            f"📊 Markets checked: "
            f"{len(MARKETS)}"
        )

        print(
            f"🚨 Valid setups: "
            f"{total_signals}"
        )

        print(
            f"📨 Telegram messages sent: "
            f"{telegram_sent}"
        )

        print("")
        print(
            "✅ SCAN FINISHED."
        )

        print(
            "🛑 Scanner stopped."
        )

        print("=" * 70)


    except Exception as e:

        print("")
        print(
            "❌ SCANNER ERROR:"
        )

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
