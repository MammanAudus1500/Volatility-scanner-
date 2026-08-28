import json
import os
import time
import requests
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES — TODAY-ONLY 4H STRATEGY SCANNER
# Builds custom 4H candles from 1H candles
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MARKETS = [
    "1HZ10V", "1HZ15V", "1HZ25V", "1HZ30V",
    "1HZ50V", "1HZ75V", "1HZ90V", "1HZ100V",
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "JD10", "JD25", "JD50", "JD75", "JD100",
    "stpRNG", "stpRNG2", "stpRNG3", "stpRNG4", "stpRNG5",
    "frxEURUSD", "frxGBPUSD", "frxUSDJPY", "frxGBPJPY",
    "frxUSDCAD", "frxEURCAD", "frxAUDUSD", "frxAUDCAD",
    "frxNZDJPY", "frxAUDNZD", "frxEURGBP",
    "frxEURCHF", "frxGBPCHF", "frxGBPNZD",
    "frxAUDCHF", "frxGBPAUD", "frxUSDCHF",
    "frxXAUUSD", "cryBTCUSD"
]


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram secrets are missing.")
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

        print(
            f"📨 Telegram status: {response.status_code}"
        )

        if response.status_code == 200:

            data = response.json()

            if data.get("ok"):
                print("✅ Telegram signal sent!")
                return True

        print(
            f"⚠️ Telegram response: {response.text}"
        )

    except Exception as e:

        print(
            f"❌ Telegram error: {e}"
        )

    return False


# ============================================================
# DERIV CONNECTION
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
        "count": 100,
        "end": "latest",
        "granularity": 3600,
        "style": "candles"
    }

    response = request(
        ws,
        payload
    )

    if response.get("error"):
        return None

    candles = response.get(
        "candles",
        []
    )

    if not candles:
        return None

    return candles


# ============================================================
# CONVERT 1H CANDLE
# ============================================================

def convert_1h(candle):

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
# IMPORTANT:
#
# Deriv's normal 4H candles can appear as:
# 01-05-09-13...
#
# We DON'T use those.
#
# We construct our own candles:
#
# 02-06-10-14...
#
# Each custom candle contains:
#
# 02:00 → 06:00
# 06:00 → 10:00
# 10:00 → 14:00
# 14:00 → 18:00
# etc.
# ============================================================

def build_custom_4h(one_hour):

    groups = {}

    for candle in one_hour:

        dt = candle["time"]

        # Only candles whose starting hour
        # belongs to our desired 02/06/10/14 structure
        if dt.hour not in [2, 6, 10, 14, 18, 22]:

            continue

        key = (
            dt.date(),
            dt.hour
        )

        groups[key] = candle


    custom = []

    for (date_value, hour), candle in sorted(
        groups.items()
    ):

        # We need the following 4 hourly candles:
        #
        # 02 → 03 → 04 → 05
        # resulting candle timestamp = 02:00
        #
        # 06 → 07 → 08 → 09
        # resulting candle timestamp = 06:00
        #
        # etc.

        required = []

        for offset in range(4):

            target_hour = hour + offset

            target_date = date_value

            if target_hour >= 24:

                target_hour -= 24

                target_date = (
                    date_value +
                    timedelta(days=1)
                )

            found = None

            for c in one_hour:

                if (
                    c["time"].date() == target_date
                    and
                    c["time"].hour == target_hour
                ):

                    found = c
                    break

            if found is None:
                break

            required.append(found)

        if len(required) != 4:
            continue

        custom_candle = {

            "time": candle["time"],

            "open": required[0]["open"],

            "high": max(
                c["high"]
                for c in required
            ),

            "low": min(
                c["low"]
                for c in required
            ),

            "close": required[-1]["close"]
        }

        custom.append(
            custom_candle
        )

    return custom


# ============================================================
# REMOVE CURRENTLY INCOMPLETE CANDLE
# ============================================================

def completed_candles(candles):

    now = datetime.now(WAT)

    result = []

    for candle in candles:

        end_time = (
            candle["time"] +
            timedelta(hours=4)
        )

        if end_time <= now:

            result.append(candle)

    return result


# ============================================================
# FIND CUSTOM 4H CANDLE
# ============================================================

def find_candle(
    candles,
    date_value,
    hour
):

    for candle in candles:

        if (
            candle["time"].date() == date_value
            and
            candle["time"].hour == hour
        ):

            return candle

    return None


# ============================================================
# BULLISH SETUP
#
# Reference candle does NOT need to be bullish.
#
# Confirmation must:
#
# 1. Sweep reference LOW
# 2. NOT sweep reference HIGH
# 3. Close strictly ABOVE reference OPEN
# ============================================================

def bullish_setup(
    reference,
    confirmation
):

    sweep_low = (
        confirmation["low"]
        < reference["low"]
    )

    sweep_high = (
        confirmation["high"]
        > reference["high"]
    )

    close_above = (
        confirmation["close"]
        > reference["open"]
    )

    # Reject ambiguous candle
    if sweep_low and sweep_high:
        return False

    return (
        sweep_low
        and
        not sweep_high
        and
        close_above
    )


# ============================================================
# BEARISH SETUP
#
# Reference candle does NOT need to be bearish.
#
# Confirmation must:
#
# 1. Sweep reference HIGH
# 2. NOT sweep reference LOW
# 3. Close strictly BELOW reference OPEN
# ============================================================

def bearish_setup(
    reference,
    confirmation
):

    sweep_high = (
        confirmation["high"]
        > reference["high"]
    )

    sweep_low = (
        confirmation["low"]
        < reference["low"]
    )

    close_below = (
        confirmation["close"]
        < reference["open"]
    )

    # Reject ambiguous candle
    if sweep_high and sweep_low:
        return False

    return (
        sweep_high
        and
        not sweep_low
        and
        close_below
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
# SCAN TODAY ONLY
# ============================================================

def scan_today(
    symbol,
    candles
):

    today = datetime.now(WAT).date()

    signals = []

    # --------------------------------------------------------
    # 02 → 06 → ENTRY 10
    # --------------------------------------------------------

    candle_02 = find_candle(
        candles,
        today,
        2
    )

    candle_06 = find_candle(
        candles,
        today,
        6
    )

    candle_10 = find_candle(
        candles,
        today,
        10
    )

    if candle_02 and candle_06:

        if bullish_setup(
            candle_02,
            candle_06
        ):

            # Only send when 10:00 candle exists.
            if candle_10:

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

        elif bearish_setup(
            candle_02,
            candle_06
        ):

            if candle_10:

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


    # --------------------------------------------------------
    # 06 → 10 → ENTRY 14
    # --------------------------------------------------------

    candle_14 = find_candle(
        candles,
        today,
        14
    )

    if candle_06 and candle_10:

        if bullish_setup(
            candle_06,
            candle_10
        ):

            if candle_14:

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

        elif bearish_setup(
            candle_06,
            candle_10
        ):

            if candle_14:

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
# FORMAT TELEGRAM SIGNAL
# ============================================================

def format_signal(signal):

    ref = signal["reference"]

    conf = signal["confirmation"]

    direction = signal["direction"]

    emoji = (
        "🟢"
        if direction == "BUY"
        else "🔴"
    )

    return f"""
🚨 SIXSGAMES SIGNAL 🚨

📊 Market: {signal["symbol"]}
📅 Date: {signal["date"]}

🎯 Direction: {emoji} {direction}

🕐 Reference:
{signal["reference_hour"]:02d}:00 WAT

Open:  {ref["open"]}
High:  {ref["high"]}
Low:   {ref["low"]}
Close: {ref["close"]}

🕐 Confirmation:
{signal["confirmation_hour"]:02d}:00 WAT

Open:  {conf["open"]}
High:  {conf["high"]}
Low:   {conf["low"]}
Close: {conf["close"]}

🎯 ENTRY:
{signal["entry_hour"]:02d}:00 WAT

✅ Sweep confirmed
✅ Close condition confirmed
❌ Opposite-side sweep: NO

👀 LOOK FOR YOUR ENTRY.
""".strip()


# ============================================================
# PRINT SIGNAL
# ============================================================

def print_signal(signal):

    print("")
    print("=" * 70)
    print("🚨 VALID SIXSGAMES SIGNAL")
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
        f"🕐 Reference: "
        f"{signal['reference_hour']:02d}:00 WAT"
    )

    print(
        f"🕐 Confirmation: "
        f"{signal['confirmation_hour']:02d}:00 WAT"
    )

    print(
        f"🎯 Entry: "
        f"{signal['entry_hour']:02d}:00 WAT"
    )

    ref = signal["reference"]
    conf = signal["confirmation"]

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
    print("✅ VALID — OPPOSITE-SIDE SWEEP REJECTED")
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("🤖 SIXSGAMES TODAY-ONLY 4H STRATEGY SCANNER")
    print("=" * 70)

    now = datetime.now(WAT)

    print(
        f"🕐 Current WAT time: "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print(
        f"📅 Scanning ONLY TODAY: "
        f"{now.date()}"
    )

    print(
        "⏱️ Custom candles: "
        "02 → 06 → 10 → 14 → 18 → 22"
    )

    print(
        "🎯 Entry windows: 10:00 and 14:00"
    )

    print(
        f"📊 Markets: {len(MARKETS)}"
    )

    print("=" * 70)

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN missing.")
        return

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID missing.")
        return

    print("✅ Telegram secrets detected.")

    ws = None

    total_signals = 0
    telegram_sent = 0

    try:

        ws = connect()

        print("")
        print("=" * 70)
        print("🔎 SCANNING TODAY")
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
                        "⚠️ No 1H candles returned."
                    )

                    continue

                one_hour = []

                for candle in raw:

                    try:

                        one_hour.append(
                            convert_1h(candle)
                        )

                    except Exception:
                        continue

                custom_4h = build_custom_4h(
                    one_hour
                )

                custom_4h = completed_candles(
                    custom_4h
                )

                today = datetime.now(
                    WAT
                ).date()

                today_candles = [
                    c for c in custom_4h
                    if c["time"].date() == today
                ]

                print(
                    f"   🕯️ Today's custom 4H candles: "
                    f"{len(today_candles)}"
                )

                signals = scan_today(
                    symbol,
                    custom_4h
                )

                if not signals:

                    print(
                        "   ⚪ No valid setup."
                    )

                    continue

                for signal in signals:

                    total_signals += 1

                    print_signal(
                        signal
                    )

                    message = format_signal(
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
        print("📊 FINAL SCAN SUMMARY")
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
            f"📨 Telegram messages sent: "
            f"{telegram_sent}"
        )

        print("")
        print(
            "✅ TODAY-ONLY SCAN FINISHED."
        )

        print(
            "🛑 Scanner will now stop."
        )

        print(
            "💡 Run the GitHub Action manually "
            "again whenever you want another scan."
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
