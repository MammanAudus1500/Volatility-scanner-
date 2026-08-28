import json
import os
import sys
import time
import urllib.parse
import urllib.request
import websocket

from datetime import datetime, timezone, timedelta


# ============================================================
# SIXSGAMES
# ONE-RUN 1H -> CUSTOM 4H STRATEGY SCANNER
# ============================================================
#
# Deriv native 4H candles can be aligned differently.
#
# Therefore we use 1H candles and construct our own candles:
#
# 02:00 -> 06:00
# 06:00 -> 10:00
# 10:00 -> 14:00
# 14:00 -> 18:00
# 18:00 -> 22:00
# 22:00 -> 02:00
#
# Timezone: Africa/Lagos (WAT, UTC+1)
#
# The scanner runs ONE TIME only.
# ============================================================


DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

HISTORY_COUNT = 1000


# ============================================================
# 42 MARKETS
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
# TELEGRAM SETTINGS
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram secrets not found.")
        return False

    try:

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

            print("📨 Telegram message sent.")
            return True

        print("❌ Telegram returned an error:")
        print(result)

    except Exception as error:

        print("❌ Telegram error:")
        print(error)

    return False


# ============================================================
# DERIV CONNECTION
# ============================================================

def connect_deriv():

    print("🔌 Connecting to Deriv...")
    sys.stdout.flush()

    ws = websocket.create_connection(
        DERIV_URL,
        timeout=20
    )

    print("✅ Connected to Deriv.")
    sys.stdout.flush()

    return ws


# ============================================================
# DERIV REQUEST
# ============================================================

def deriv_request(ws, payload):

    ws.send(
        json.dumps(payload)
    )

    while True:

        raw = ws.recv()

        if not raw:
            continue

        data = json.loads(raw)

        if data.get("error"):
            return data

        return data


# ============================================================
# GET 1-HOUR CANDLES
# ============================================================

def get_hourly_candles(ws, symbol):

    payload = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": HISTORY_COUNT,
        "end": "latest",
        "granularity": 3600,
        "style": "candles"
    }

    response = deriv_request(
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
            "message": "No hourly candles returned"
        }

    return candles, None


# ============================================================
# CONVERT DERIV CANDLE
# ============================================================

def convert_candle(raw):

    epoch = int(
        raw["epoch"]
    )

    dt = datetime.fromtimestamp(
        epoch,
        timezone.utc
    ).astimezone(WAT)

    return {
        "time": dt,
        "open": float(raw["open"]),
        "high": float(raw["high"]),
        "low": float(raw["low"]),
        "close": float(raw["close"])
    }


# ============================================================
# CUSTOM 4H START TIME
# ============================================================
#
# We want:
#
# 02
# 06
# 10
# 14
# 18
# 22
#
# Every four hours.
# ============================================================

def get_custom_start(dt):

    hour = dt.hour

    if hour in [2, 3, 4, 5]:
        start_hour = 2

    elif hour in [6, 7, 8, 9]:
        start_hour = 6

    elif hour in [10, 11, 12, 13]:
        start_hour = 10

    elif hour in [14, 15, 16, 17]:
        start_hour = 14

    elif hour in [18, 19, 20, 21]:
        start_hour = 18

    else:
        # 22, 23, 00, 01
        start_hour = 22

    date_value = dt.date()

    # 00:00 and 01:00 belong to yesterday's
    # 22:00 -> 02:00 candle.
    if hour in [0, 1]:

        date_value = (
            dt - timedelta(days=1)
        ).date()

    return (
        date_value,
        start_hour
    )


# ============================================================
# BUILD CUSTOM 4H CANDLES
# ============================================================

def build_custom_4h(hourly):

    groups = {}

    for candle in hourly:

        start_date, start_hour = get_custom_start(
            candle["time"]
        )

        key = (
            start_date,
            start_hour
        )

        if key not in groups:

            groups[key] = []

        groups[key].append(
            candle
        )

    custom = []

    for key, group in groups.items():

        group.sort(
            key=lambda x: x["time"]
        )

        # A complete 4H candle must contain exactly
        # four consecutive 1H candles.
        if len(group) != 4:
            continue

        consecutive = True

        for i in range(1, 4):

            difference = (
                group[i]["time"]
                - group[i - 1]["time"]
            )

            if difference != timedelta(hours=1):

                consecutive = False
                break

        if not consecutive:
            continue

        date_value, start_hour = key

        start_time = datetime(
            date_value.year,
            date_value.month,
            date_value.day,
            start_hour,
            0,
            0,
            tzinfo=WAT
        )

        end_time = (
            start_time
            + timedelta(hours=4)
        )

        custom_candle = {
            "start": start_time,
            "end": end_time,

            "open": group[0]["open"],

            "high": max(
                candle["high"]
                for candle in group
            ),

            "low": min(
                candle["low"]
                for candle in group
            ),

            "close": group[-1]["close"]
        }

        custom.append(
            custom_candle
        )

    custom.sort(
        key=lambda x: x["start"]
    )

    return custom


# ============================================================
# KEEP ONLY COMPLETED CUSTOM CANDLES
# ============================================================

def get_completed_custom_candles(custom):

    now = datetime.now(WAT)

    completed = []

    for candle in custom:

        if candle["end"] <= now:

            completed.append(
                candle
            )

    return completed


# ============================================================
# FIND CANDLE
# ============================================================

def find_candle(
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
# BUY SETUP
# ============================================================
#
# Reference direction DOES NOT MATTER.
#
# Confirmation must:
#
# 1. Sweep the reference LOW
# 2. Close STRICTLY ABOVE reference OPEN
#
# Equal to reference open = INVALID.
# ============================================================

def is_buy_setup(
    reference,
    confirmation
):

    sweep = (
        confirmation["low"]
        < reference["low"]
    )

    close_condition = (
        confirmation["close"]
        > reference["open"]
    )

    return (
        sweep
        and close_condition
    )


# ============================================================
# SELL SETUP
# ============================================================
#
# Reference direction DOES NOT MATTER.
#
# Confirmation must:
#
# 1. Sweep the reference HIGH
# 2. Close STRICTLY BELOW reference OPEN
#
# Equal to reference open = INVALID.
# ============================================================

def is_sell_setup(
    reference,
    confirmation
):

    sweep = (
        confirmation["high"]
        > reference["high"]
    )

    close_condition = (
        confirmation["close"]
        < reference["open"]
    )

    return (
        sweep
        and close_condition
    )


# ============================================================
# SCAN STRATEGY
# ============================================================

def scan_strategy(
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

    for date_value in dates:

        # ====================================================
        # SETUP 1
        #
        # 02 -> 06 -> ENTRY 10
        # ====================================================

        candle_02 = find_candle(
            candles,
            date_value,
            2
        )

        candle_06 = find_candle(
            candles,
            date_value,
            6
        )

        if candle_02 and candle_06:

            if is_buy_setup(
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
                    "reference_candle": candle_02,
                    "confirmation_candle": candle_06
                })

            if is_sell_setup(
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
                    "reference_candle": candle_02,
                    "confirmation_candle": candle_06
                })

        # ====================================================
        # SETUP 2
        #
        # 06 -> 10 -> ENTRY 14
        # ====================================================

        candle_10 = find_candle(
            candles,
            date_value,
            10
        )

        if candle_06 and candle_10:

            if is_buy_setup(
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
                    "reference_candle": candle_06,
                    "confirmation_candle": candle_10
                })

            if is_sell_setup(
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
                    "reference_candle": candle_06,
                    "confirmation_candle": candle_10
                })

    return signals


# ============================================================
# PRINT CANDLE
# ============================================================

def print_candle(
    label,
    candle
):

    print(
        f"{label} "
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
    print("🚨" * 20)
    print("🚨 VALID SIXSGAMES SETUP")
    print("🚨" * 20)

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
        f"🕐 Reference: "
        f"{signal['reference']} WAT"
    )

    print(
        f"🕐 Confirmation: "
        f"{signal['confirmation']} WAT"
    )

    print(
        f"🎯 LOOK FOR ENTRY: "
        f"{signal['entry']} WAT"
    )

    print("")

    print_candle(
        "Reference    :",
        signal["reference_candle"]
    )

    print_candle(
        "Confirmation :",
        signal["confirmation_candle"]
    )

    print("")

    print("✅ Sweep condition passed.")
    print("✅ Close condition passed.")
    print("👀 LOOK FOR YOUR ENTRY.")

    print("")


# ============================================================
# TELEGRAM SIGNAL
# ============================================================

def make_telegram_message(signal):

    if signal["direction"] == "BUY":

        direction = "🟢 BUY"

    else:

        direction = "🔴 SELL"

    return (
        "🚨 SIXSGAMES SIGNAL 🚨\n\n"
        f"📊 Market: {signal['symbol']}\n"
        f"📅 Date: {signal['date']}\n"
        f"🎯 Direction: {direction}\n\n"
        f"🕐 Reference: {signal['reference']} WAT\n"
        f"🕐 Confirmation: {signal['confirmation']} WAT\n"
        f"🎯 ENTRY: {signal['entry']} WAT\n\n"
        "✅ Sweep confirmed\n"
        "✅ Close condition confirmed\n\n"
        "👀 LOOK FOR YOUR ENTRY."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("🤖 SIXSGAMES CUSTOM 4H CANDLE SCANNER")
    print("=" * 70)

    print(
        "📊 Markets:",
        len(MARKETS)
    )

    print(
        "📥 Source candles: 1H"
    )

    print(
        "🧱 Constructed candles: CUSTOM 4H"
    )

    print(
        "🌍 Timezone: Africa/Lagos"
    )

    print(
        "🎯 Strategy times: "
        "02 / 06 / 10 / 14 / 18 / 22"
    )

    print(
        "🛑 Mode: ONE RUN ONLY"
    )

    print("=" * 70)

    sys.stdout.flush()

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:

        print(
            "✅ Telegram secrets detected."
        )

    else:

        print(
            "⚠️ Telegram secrets are missing."
        )

    sys.stdout.flush()

    ws = None

    total_signals = 0
    telegram_sent = 0
    successful_markets = 0

    try:

        ws = connect_deriv()

        print("")
        print("=" * 70)
        print("🔎 SCANNING ALL 42 MARKETS")
        print("=" * 70)

        sys.stdout.flush()

        for number, symbol in enumerate(
            MARKETS,
            start=1
        ):

            print("")
            print(
                f"[{number}/{len(MARKETS)}] "
                f"🔍 CHECKING {symbol}"
            )

            sys.stdout.flush()

            try:

                raw, error = get_hourly_candles(
                    ws,
                    symbol
                )

                if error:

                    print(
                        "   ❌ Deriv error:",
                        error
                    )

                    sys.stdout.flush()

                    continue

                hourly = []

                for item in raw:

                    try:

                        hourly.append(
                            convert_candle(item)
                        )

                    except Exception:
                        pass

                print(
                    f"   📥 1H candles received: "
                    f"{len(hourly)}"
                )

                custom = build_custom_4h(
                    hourly
                )

                completed = (
                    get_completed_custom_candles(
                        custom
                    )
                )

                print(
                    f"   🧱 Custom 4H candles: "
                    f"{len(custom)}"
                )

                print(
                    f"   ✅ Completed custom 4H: "
                    f"{len(completed)}"
                )

                # ------------------------------------------------
                # Show the most recent custom candle alignment.
                # This is VERY IMPORTANT for this test.
                # ------------------------------------------------

                print(
                    "   🕯️ Latest custom candles:"
                )

                for candle in completed[-6:]:

                    print(
                        "      "
                        + candle["start"].strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        + " -> "
                        + candle["end"].strftime(
                            "%H:%M"
                        )
                    )

                signals = scan_strategy(
                    symbol,
                    completed
                )

                successful_markets += 1

                if signals:

                    print("")
                    print(
                        f"   🚨 "
                        f"{len(signals)} SETUP(S) FOUND"
                    )

                    for signal in signals:

                        total_signals += 1

                        print_signal(
                            signal
                        )

                        message = (
                            make_telegram_message(
                                signal
                            )
                        )

                        if send_telegram(
                            message
                        ):

                            telegram_sent += 1

                else:

                    print(
                        "   ⚪ No valid setup found."
                    )

                sys.stdout.flush()

            except Exception as error:

                print(
                    f"   ❌ Market processing error: "
                    f"{error}"
                )

                sys.stdout.flush()

        # ========================================================
        # FINAL RESULT
        # ========================================================

        print("")
        print("=" * 70)
        print("📊 FINAL SCAN RESULT")
        print("=" * 70)

        print(
            f"📊 Markets requested: "
            f"{len(MARKETS)}"
        )

        print(
            f"✅ Markets successfully scanned: "
            f"{successful_markets}"
        )

        print(
            f"🚨 Total valid setups: "
            f"{total_signals}"
        )

        print(
            f"📨 Telegram signals sent: "
            f"{telegram_sent}"
        )

        print("")
        print(
            "🛑 ONE-RUN SCAN COMPLETE."
        )

        print(
            "🛑 Scanner is stopping now."
        )

        print("=" * 70)

        sys.stdout.flush()

    except Exception as error:

        print("")
        print("=" * 70)
        print("❌ SCANNER ERROR")
        print("=" * 70)

        print(error)

        sys.stdout.flush()

    finally:

        if ws:

            try:

                ws.close()

                print(
                    "🔌 Deriv connection closed."
                )

            except Exception:
                pass

        sys.stdout.flush()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
