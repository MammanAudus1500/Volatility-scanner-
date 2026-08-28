import json
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES - TODAY ONLY
# 1H DATA -> CUSTOM 4H CANDLES
#
# Strategy candles:
# 02:00-05:59
# 06:00-09:59
# 10:00-13:59
# 14:00-17:59
#
# Setup:
# 02 -> 06 -> ENTRY 10
# 06 -> 10 -> ENTRY 14
#
# IMPORTANT:
# We do NOT use Deriv's native 4H candle labels.
# We build the 4H candles from 1H candles.
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


# ============================================================
# CONNECTION
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

    response = request(ws, payload)

    if response.get("error"):

        return None, response["error"]

    candles = response.get("candles", [])

    if not candles:

        return None, {
            "message": "No 1H candles returned"
        }

    return candles, None


# ============================================================
# CONVERT 1H CANDLE TO WAT
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
# CHECK WHETHER 1H CANDLE IS COMPLETED
# ============================================================

def completed_candle(candle, now):

    end_time = candle["time"] + timedelta(hours=1)

    return end_time <= now


# ============================================================
# BUILD CUSTOM 4H CANDLE
#
# Example:
#
# 02 candle = 02,03,04,05
# 06 candle = 06,07,08,09
# 10 candle = 10,11,12,13
# 14 candle = 14,15,16,17
#
# ============================================================

def build_4h_candle(hourly_candles, date_value, start_hour):

    required_hours = [
        start_hour,
        start_hour + 1,
        start_hour + 2,
        start_hour + 3
    ]

    selected = []

    for hour in required_hours:

        found = None

        for candle in hourly_candles:

            if (
                candle["time"].date() == date_value
                and candle["time"].hour == hour
            ):
                found = candle
                break

        if found is None:

            return None

        selected.append(found)

    return {
        "date": date_value,
        "hour": start_hour,

        "open": selected[0]["open"],

        "high": max(
            candle["high"]
            for candle in selected
        ),

        "low": min(
            candle["low"]
            for candle in selected
        ),

        "close": selected[-1]["close"],

        "hours": selected
    }


# ============================================================
# BULLISH SETUP
#
# Reference direction DOES NOT matter.
#
# Only requirements:
#
# 1. Confirmation sweeps reference LOW
# 2. Confirmation closes ABOVE reference OPEN
#
# ============================================================

def bullish_setup(reference, confirmation):

    sweep = confirmation["low"] < reference["low"]

    close_condition = (
        confirmation["close"] > reference["open"]
    )

    return sweep and close_condition


# ============================================================
# BEARISH SETUP
#
# Reference direction DOES NOT matter.
#
# Only requirements:
#
# 1. Confirmation sweeps reference HIGH
# 2. Confirmation closes BELOW reference OPEN
#
# ============================================================

def bearish_setup(reference, confirmation):

    sweep = confirmation["high"] > reference["high"]

    close_condition = (
        confirmation["close"] < reference["open"]
    )

    return sweep and close_condition


# ============================================================
# PRINT CANDLE
# ============================================================

def print_candle(label, candle):

    if candle is None:

        print(f"❌ {label}: NOT AVAILABLE")

        return

    print(
        f"🕐 {label}: "
        f"O={candle['open']} "
        f"H={candle['high']} "
        f"L={candle['low']} "
        f"C={candle['close']}"
    )


# ============================================================
# CHECK TODAY'S SETUPS
# ============================================================

def check_today(hourly_candles, symbol, today, now):

    print("")
    print("=" * 70)
    print(f"📊 {symbol}")
    print(f"📅 TODAY: {today}")
    print(f"🕐 CURRENT WAT: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # --------------------------------------------------------
    # BUILD TODAY'S CUSTOM 4H CANDLES
    # --------------------------------------------------------

    candle_02 = build_4h_candle(
        hourly_candles,
        today,
        2
    )

    candle_06 = build_4h_candle(
        hourly_candles,
        today,
        6
    )

    candle_10 = build_4h_candle(
        hourly_candles,
        today,
        10
    )

    candle_14 = build_4h_candle(
        hourly_candles,
        today,
        14
    )

    print("")
    print("🎯 TODAY'S CUSTOM 4H CANDLES")
    print("-" * 70)

    print_candle("02:00 → 06:00", candle_02)
    print_candle("06:00 → 10:00", candle_06)
    print_candle("10:00 → 14:00", candle_10)
    print_candle("14:00 → 18:00", candle_14)

    signals = []

    # ========================================================
    # SETUP 1
    # 02 -> 06 -> ENTRY 10
    # ========================================================

    print("")
    print("🧪 SETUP 1: 02 → 06 → ENTRY 10")
    print("-" * 70)

    if candle_02 and candle_06:

        # Check whether 06 candle is completed
        if now >= today_start(today, 10):

            buy_sweep = (
                candle_06["low"] < candle_02["low"]
            )

            buy_close = (
                candle_06["close"] > candle_02["open"]
            )

            sell_sweep = (
                candle_06["high"] > candle_02["high"]
            )

            sell_close = (
                candle_06["close"] < candle_02["open"]
            )

            print(
                f"🟢 BUY sweep: "
                f"{'✅' if buy_sweep else '❌'}"
            )

            print(
                f"🟢 BUY close > 02 open: "
                f"{'✅' if buy_close else '❌'}"
            )

            print(
                f"🔴 SELL sweep: "
                f"{'✅' if sell_sweep else '❌'}"
            )

            print(
                f"🔴 SELL close < 02 open: "
                f"{'✅' if sell_close else '❌'}"
            )

            if buy_sweep and buy_close:

                signals.append({
                    "symbol": symbol,
                    "date": today,
                    "direction": "BUY",
                    "reference": "02:00",
                    "confirmation": "06:00",
                    "entry": "10:00"
                })

            elif sell_sweep and sell_close:

                signals.append({
                    "symbol": symbol,
                    "date": today,
                    "direction": "SELL",
                    "reference": "02:00",
                    "confirmation": "06:00",
                    "entry": "10:00"
                })

            else:

                print("⚪ No valid 10:00 setup.")

        else:

            print(
                "⏳ 10:00 entry window has not arrived yet."
            )

    else:

        print(
            "⚠️ Cannot test 02 → 06."
        )

    # ========================================================
    # SETUP 2
    # 06 -> 10 -> ENTRY 14
    # ========================================================

    print("")
    print("🧪 SETUP 2: 06 → 10 → ENTRY 14")
    print("-" * 70)

    if candle_06 and candle_10:

        if now >= today_start(today, 14):

            buy_sweep = (
                candle_10["low"] < candle_06["low"]
            )

            buy_close = (
                candle_10["close"] > candle_06["open"]
            )

            sell_sweep = (
                candle_10["high"] > candle_06["high"]
            )

            sell_close = (
                candle_10["close"] < candle_06["open"]
            )

            print(
                f"🟢 BUY sweep: "
                f"{'✅' if buy_sweep else '❌'}"
            )

            print(
                f"🟢 BUY close > 06 open: "
                f"{'✅' if buy_close else '❌'}"
            )

            print(
                f"🔴 SELL sweep: "
                f"{'✅' if sell_sweep else '❌'}"
            )

            print(
                f"🔴 SELL close < 06 open: "
                f"{'✅' if sell_close else '❌'}"
            )

            if buy_sweep and buy_close:

                signals.append({
                    "symbol": symbol,
                    "date": today,
                    "direction": "BUY",
                    "reference": "06:00",
                    "confirmation": "10:00",
                    "entry": "14:00"
                })

            elif sell_sweep and sell_close:

                signals.append({
                    "symbol": symbol,
                    "date": today,
                    "direction": "SELL",
                    "reference": "06:00",
                    "confirmation": "10:00",
                    "entry": "14:00"
                })

            else:

                print("⚪ No valid 14:00 setup.")

        else:

            print(
                "⏳ 14:00 entry window has not arrived yet."
            )

    else:

        print(
            "⚠️ Cannot test 06 → 10."
        )

    return signals


# ============================================================
# TODAY START HELPER
# ============================================================

def today_start(date_value, hour):

    return datetime(
        date_value.year,
        date_value.month,
        date_value.day,
        hour,
        0,
        0,
        tzinfo=WAT
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    import os
    import urllib.request
    import urllib.parse

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:

        print("⚠️ Telegram secrets missing.")

        return False

    url = (
        f"https://api.telegram.org/bot{token}/sendMessage"
    )

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()

    try:

        request_obj = urllib.request.Request(
            url,
            data=data,
            method="POST"
        )

        with urllib.request.urlopen(
            request_obj,
            timeout=15
        ) as response:

            result = json.loads(
                response.read().decode()
            )

        return bool(result.get("ok"))

    except Exception as e:

        print(
            f"⚠️ Telegram error: {e}"
        )

        return False


# ============================================================
# SIGNAL MESSAGE
# ============================================================

def signal_message(signal):

    emoji = (
        "🟢 BUY"
        if signal["direction"] == "BUY"
        else "🔴 SELL"
    )

    return f"""🚨 SIXSGAMES SIGNAL 🚨

📊 Market: {signal['symbol']}
📅 Date: {signal['date']}
🎯 Direction: {emoji}

🕐 Reference: {signal['reference']} WAT
🕐 Confirmation: {signal['confirmation']} WAT
🎯 ENTRY: {signal['entry']} WAT

✅ Sweep confirmed
✅ Close condition confirmed

👀 LOOK FOR YOUR ENTRY."""


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("🤖 SIXSGAMES TODAY-ONLY 4H STRATEGY SCANNER")
    print("=" * 70)
    print("📊 Markets:", len(MARKETS))
    print("⏱️ Source timeframe: 1H")
    print("🕯️ Strategy timeframe: CUSTOM 4H")
    print("🌍 Timezone: Africa/Lagos")
    print("🎯 Setup 1: 02 → 06 → ENTRY 10")
    print("🎯 Setup 2: 06 → 10 → ENTRY 14")
    print("=" * 70)

    now = datetime.now(WAT)

    today = now.date()

    print("")
    print(
        f"📅 Automatically detected today: {today}"
    )

    print(
        f"🕐 Current WAT time: "
        f"{now.strftime('%H:%M:%S')}"
    )

    ws = None

    total_signals = 0

    try:

        ws = connect()

        print("")
        print("=" * 70)
        print("🔎 SCANNING TODAY ONLY")
        print("=" * 70)

        for symbol in MARKETS:

            print("")
            print(f"🔍 Checking {symbol}...")

            hourly, error = get_1h_candles(
                ws,
                symbol
            )

            if error:

                print(
                    f"⚠️ {symbol}: {error}"
                )

                continue

            converted = []

            for raw in hourly:

                try:

                    candle = convert_candle(raw)

                    if completed_candle(
                        candle,
                        now
                    ):

                        converted.append(candle)

                except Exception:

                    continue

            signals = check_today(
                converted,
                symbol,
                today,
                now
            )

            for signal in signals:

                total_signals += 1

                print("")
                print("🚨" * 20)
                print("🔥 VALID SIXSGAMES SETUP")
                print("🚨" * 20)

                print(
                    f"📊 Market: {signal['symbol']}"
                )

                print(
                    f"📅 Date: {signal['date']}"
                )

                print(
                    f"🎯 Direction: "
                    f"{signal['direction']}"
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
                    f"🎯 ENTRY: "
                    f"{signal['entry']} WAT"
                )

                print(
                    "✅ Sweep confirmed"
                )

                print(
                    "✅ Close condition confirmed"
                )

                telegram_text = signal_message(
                    signal
                )

                if send_telegram(
                    telegram_text
                ):

                    print(
                        "📨 Telegram signal sent."
                    )

                else:

                    print(
                        "⚠️ Telegram signal was not sent."
                    )

        print("")
        print("=" * 70)
        print("📊 TODAY'S SCAN COMPLETE")
        print("=" * 70)

        print(
            f"📅 Date scanned: {today}"
        )

        print(
            f"📊 Markets checked: {len(MARKETS)}"
        )

        print(
            f"🚨 Valid setups found: {total_signals}"
        )

        print("")
        print(
            "🛑 Scanner stopped."
        )

        print(
            "💡 Run the GitHub Action again whenever you want"
            " to perform another manual scan."
        )

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

            except Exception:
                pass


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
