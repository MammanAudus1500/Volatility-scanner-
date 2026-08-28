import json
import os
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES
# ONE-RUN 1H -> CUSTOM 4H SCANNER
#
# IMPORTANT:
# Deriv's native 4H candles may start at 01:00, 05:00, 09:00...
# Our strategy requires:
#
# 02:00 -> 06:00
# 06:00 -> 10:00
# 10:00 -> 14:00
# 14:00 -> 18:00
#
# Therefore we download 1H candles and construct our own
# 4-hour candles aligned to Africa/Lagos time.
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

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

# ------------------------------------------------------------
# How many 1H candles to request.
#
# 2000 hours gives us plenty of historical data for testing.
# ------------------------------------------------------------

HISTORY_COUNT = 2000


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def telegram_send(message):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram secrets not available.")
        return False

    try:

        import urllib.request
        import urllib.parse

        url = (
            "https://api.telegram.org/bot"
            + TELEGRAM_TOKEN
            + "/sendMessage"
        )

        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method="POST"
        )

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            result = json.loads(
                response.read().decode("utf-8")
            )

            if result.get("ok"):
                print("📨 Telegram signal sent.")
                return True

            print("❌ Telegram rejected message:")
            print(result)

    except Exception as e:

        print("❌ Telegram error:")
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

        raw = ws.recv()

        if not raw:
            continue

        data = json.loads(raw)

        if data.get("error"):
            return data

        return data


# ============================================================
# GET 1H CANDLES
# ============================================================

def get_1h_candles(ws, symbol):

    payload = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": HISTORY_COUNT,
        "end": "latest",
        "granularity": 3600,
        "style": "candles",
        "req_id": 100
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
            "message": "No 1H candles returned"
        }

    return candles, None


# ============================================================
# CONVERT 1H CANDLE
# ============================================================

def convert_1h_candle(candle):

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
# BUILD CUSTOM 4H CANDLES
#
# We deliberately DO NOT use Deriv's native 4H candles.
#
# A custom candle beginning at 02:00 contains:
#
# 02:00 hour
# 03:00 hour
# 04:00 hour
# 05:00 hour
#
# It closes at 06:00.
#
# Then:
#
# 06:00 -> 10:00
# 10:00 -> 14:00
# 14:00 -> 18:00
# ============================================================

def build_custom_4h_candles(hourly_candles):

    groups = {}

    for candle in hourly_candles:

        dt = candle["time"]

        # ----------------------------------------------------
        # Custom 4H windows start at:
        # 02, 06, 10, 14, 18, 22
        # ----------------------------------------------------

        hour = dt.hour

        if hour in [2, 6, 10, 14, 18, 22]:

            start_hour = hour

        elif hour in [3, 7, 11, 15, 19, 23]:

            start_hour = hour - 1

        elif hour in [0, 4, 8, 12, 16, 20]:

            start_hour = hour - 2

            if start_hour < 0:
                start_hour += 24

        else:

            continue

        # ----------------------------------------------------
        # Determine the actual start date.
        #
        # For 00:00 and 01:00, they belong to the previous
        # day's 22:00 -> 02:00 candle.
        # ----------------------------------------------------

        date_value = dt.date()

        if hour in [0, 1]:
            start_hour = 22
            date_value = (
                dt - timedelta(days=1)
            ).date()

        key = (
            date_value,
            start_hour
        )

        if key not in groups:
            groups[key] = []

        groups[key].append(candle)

    custom = []

    for key, candles in groups.items():

        date_value, start_hour = key

        # ----------------------------------------------------
        # We need exactly four hourly candles.
        # ----------------------------------------------------

        if len(candles) != 4:
            continue

        candles.sort(
            key=lambda x: x["time"]
        )

        first = candles[0]
        last = candles[-1]

        # Verify the four candles are consecutive.
        valid = True

        for i in range(1, 4):

            difference = (
                candles[i]["time"]
                - candles[i - 1]["time"]
            )

            if difference != timedelta(hours=1):

                valid = False
                break

        if not valid:
            continue

        start_dt = datetime(
            date_value.year,
            date_value.month,
            date_value.day,
            start_hour,
            0,
            0,
            tzinfo=WAT
        )

        end_dt = start_dt + timedelta(
            hours=4
        )

        custom_candle = {
            "start": start_dt,
            "end": end_dt,
            "open": first["open"],
            "high": max(
                c["high"]
                for c in candles
            ),
            "low": min(
                c["low"]
                for c in candles
            ),
            "close": last["close"]
        }

        custom.append(
            custom_candle
        )

    custom.sort(
        key=lambda x: x["start"]
    )

    return custom


# ============================================================
# REMOVE CURRENTLY FORMING CUSTOM CANDLE
# ============================================================

def completed_custom_candles(candles):

    now = datetime.now(WAT)

    result = []

    for candle in candles:

        if candle["end"] <= now:
            result.append(candle)

    return result


# ============================================================
# FIND CUSTOM CANDLE
# ============================================================

def find_custom_candle(
    candles,
    date_value,
    start_hour
):

    for candle in candles:

        if (
            candle["start"].date()
            == date_value
            and candle["start"].hour
            == start_hour
        ):
            return candle

    return None


# ============================================================
# BULLISH RULE
#
# IMPORTANT:
# We DO NOT care whether the reference candle itself is
# bullish or bearish.
#
# BUY requires:
#
# confirmation LOW < reference LOW
#
# AND
#
# confirmation CLOSE > reference OPEN
#
# Strictly greater.
#
# Equal = INVALID.
# ============================================================

def bullish_setup(
    reference,
    confirmation
):

    swept = (
        confirmation["low"]
        < reference["low"]
    )

    closed_above = (
        confirmation["close"]
        > reference["open"]
    )

    return swept and closed_above


# ============================================================
# BEARISH RULE
#
# Reference candle direction is irrelevant.
#
# SELL requires:
#
# confirmation HIGH > reference HIGH
#
# AND
#
# confirmation CLOSE < reference OPEN
#
# Strictly lower.
#
# Equal = INVALID.
# ============================================================

def bearish_setup(
    reference,
    confirmation
):

    swept = (
        confirmation["high"]
        > reference["high"]
    )

    closed_below = (
        confirmation["close"]
        < reference["open"]
    )

    return swept and closed_below


# ============================================================
# CHECK ONE MARKET
#
# We scan historical completed custom candles.
#
# Setup A:
# 02 -> 06 -> entry 10
#
# Setup B:
# 06 -> 10 -> entry 14
#
# ============================================================

def scan_market(
    symbol,
    candles
):

    signals = []

    dates = sorted(
        set(
            candle["start"].date()
            for candle in candles
        )
    )

    # --------------------------------------------------------
    # SETUP A
    # 02:00 -> 06:00 -> ENTRY 10:00
    # --------------------------------------------------------

    for date_value in dates:

        candle_02 = find_custom_candle(
            candles,
            date_value,
            2
        )

        candle_06 = find_custom_candle(
            candles,
            date_value,
            6
        )

        if candle_02 and candle_06:

            if bullish_setup(
                candle_02,
                candle_06
            ):

                signals.append({
                    "symbol": symbol,
                    "date": date_value,
                    "reference": "02:00",
                    "confirmation": "06:00",
                    "entry": "10:00",
                    "direction": "BUY",
                    "ref": candle_02,
                    "conf": candle_06
                })

            if bearish_setup(
                candle_02,
                candle_06
            ):

                signals.append({
                    "symbol": symbol,
                    "date": date_value,
                    "reference": "02:00",
                    "confirmation": "06:00",
                    "entry": "10:00",
                    "direction": "SELL",
                    "ref": candle_02,
                    "conf": candle_06
                })

        # ----------------------------------------------------
        # SETUP B
        # 06:00 -> 10:00 -> ENTRY 14:00
        # ----------------------------------------------------

        candle_10 = find_custom_candle(
            candles,
            date_value,
            10
        )

        if candle_06 and candle_10:

            if bullish_setup(
                candle_06,
                candle_10
            ):

                signals.append({
                    "symbol": symbol,
                    "date": date_value,
                    "reference": "06:00",
                    "confirmation": "10:00",
                    "entry": "14:00",
                    "direction": "BUY",
                    "ref": candle_06,
                    "conf": candle_10
                })

            if bearish_setup(
                candle_06,
                candle_10
            ):

                signals.append({
                    "symbol": symbol,
                    "date": date_value,
                    "reference": "06:00",
                    "confirmation": "10:00",
                    "entry": "14:00",
                    "direction": "SELL",
                    "ref": candle_06,
                    "conf": candle_10
                })

    return signals


# ============================================================
# PRINT CANDLE
# ============================================================

def print_candle(label, candle):

    print(
        f"   {label} "
        f"O={candle['open']} "
        f"H={candle['high']} "
        f"L={candle['low']} "
        f"C={candle['close']}"
    )


# ============================================================
# PRINT SIGNAL
# ============================================================

def print_signal(signal):

    print("")
    print("=" * 70)
    print("🚨 VALID SIXSGAMES SETUP")
    print("=" * 70)

    print(
        f"📊 Market: {signal['symbol']}"
    )

    print(
        f"📅 Date: {signal['date']}"
    )

    print(
        f"🎯 Direction: {signal['direction']}"
    )

    print(
        f"🎯 LOOK FOR ENTRY: "
        f"{signal['entry']} WAT"
    )

    print(
        f"Reference candle: "
        f"{signal['reference']}"
    )

    print(
        f"Confirmation candle: "
        f"{signal['confirmation']}"
    )

    print("")

    print_candle(
        "Reference:",
        signal["ref"]
    )

    print_candle(
        "Confirm  :",
        signal["conf"]
    )

    print("")
    print("✅ Sweep condition passed.")
    print("✅ Close condition passed.")
    print("👀 LOOK FOR YOUR ENTRY.")
    print("=" * 70)


# ============================================================
# TELEGRAM FORMAT
# ============================================================

def telegram_signal_message(signal):

    direction = signal["direction"]

    emoji = (
        "🟢 BUY"
        if direction == "BUY"
        else "🔴 SELL"
    )

    return (
        "🚨 SIXSGAMES SIGNAL 🚨\n\n"
        f"📊 Market: {signal['symbol']}\n"
        f"📅 Date: {signal['date']}\n"
        f"🎯 Direction: {emoji}\n\n"
        f"🕐 Reference: {signal['reference']} WAT\n"
        f"🕐 Confirmation: {signal['confirmation']} WAT\n"
        f"🎯 LOOK FOR ENTRY: {signal['entry']} WAT\n\n"
        "✅ Sweep confirmed\n"
        "✅ Close beyond reference OPEN confirmed\n\n"
        "👀 LOOK FOR YOUR ENTRY."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("🤖 SIXSGAMES ONE-RUN CUSTOM 4H SCANNER")
    print("=" * 70)

    print(
        "📊 Markets:",
        len(MARKETS)
    )

    print(
        "⏱️ Source timeframe: 1H"
    )

    print(
        "⏱️ Custom strategy timeframe: 4H"
    )

    print(
        "🌍 Timezone: Africa/Lagos"
    )

    print(
        "🎯 Custom candles: "
        "02, 06, 10, 14, 18, 22"
    )

    print(
        "🛑 Mode: ONE RUN ONLY"
    )

    print("=" * 70)

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:

        print(
            "✅ Telegram secrets detected."
        )

    else:

        print(
            "⚠️ Telegram secrets NOT detected."
        )

    ws = None

    total_signals = 0
    telegram_sent = 0
    markets_completed = 0

    try:

        ws = connect()

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
                f"🔍 {symbol}"
            )

            try:

                raw_candles, error = get_1h_candles(
                    ws,
                    symbol
                )

                if error:

                    print(
                        "   ❌ Candle error:",
                        error
                    )

                    continue

                hourly = []

                for raw in raw_candles:

                    try:

                        hourly.append(
                            convert_1h_candle(raw)
                        )

                    except Exception:
                        continue

                print(
                    f"   📥 1H candles: "
                    f"{len(hourly)}"
                )

                custom = build_custom_4h_candles(
                    hourly
                )

                print(
                    f"   🧱 Custom 4H candles: "
                    f"{len(custom)}"
                )

                completed = completed_custom_candles(
                    custom
                )

                print(
                    f"   ✅ Completed custom candles: "
                    f"{len(completed)}"
                )

                signals = scan_market(
                    symbol,
                    completed
                )

                markets_completed += 1

                if signals:

                    print(
                        f"   🚨 SETUPS FOUND: "
                        f"{len(signals)}"
                    )

                    for signal in signals:

                        total_signals += 1

                        print_signal(
                            signal
                        )

                        if telegram_send(
                            telegram_signal_message(
                                signal
                            )
                        ):

                            telegram_sent += 1

                else:

                    print(
                        "   ⚪ No valid setup found."
                    )

            except Exception as e:

                print(
                    f"   ❌ Market error: {e}"
                )

        print("")
        print("=" * 70)
        print("📊 FINAL SCAN RESULT")
        print("=" * 70)

        print(
            f"Markets requested: "
            f"{len(MARKETS)}"
        )

        print(
            f"Markets completed: "
            f"{markets_completed}"
        )

        print(
            f"Total valid setups: "
            f"{total_signals}"
        )

        print(
            f"Telegram messages sent: "
            f"{telegram_sent}"
        )

        print("")
        print(
            "🛑 ONE-RUN SCAN FINISHED."
        )

        print(
            "🛑 The scanner will now stop."
        )

        print("=" * 70)

    except Exception as e:

        print("")
        print("=" * 70)
        print("❌ SCANNER ERROR")
        print("=" * 70)

        print(str(e))

    finally:

        if ws:

            try:
                ws.close()
                print("🔌 Deriv connection closed.")
            except Exception:
                pass


# ====================================================
