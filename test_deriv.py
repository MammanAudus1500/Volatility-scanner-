import os
import json
import time
import requests
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES - 4H DIAGNOSTIC + LIVE STRATEGY SCANNER
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

SCAN_INTERVAL = 60

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
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram secrets are missing.")
        return False

    url = (
        "https://api.telegram.org/"
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

        if data.get("ok"):

            print("📱 Telegram signal sent.")
            return True

        print("❌ Telegram returned an error:")
        print(response.text)

    except Exception as e:

        print("❌ Telegram request failed:")
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
        "count": 30,
        "end": "latest",
        "granularity": 14400,
        "style": "candles"
    }

    response = request(ws, payload)

    if response.get("error"):

        print(
            f"⚠️ Deriv error for {symbol}: "
            f"{response['error']}"
        )

        return []

    raw_candles = response.get("candles", [])

    candles = []

    for candle in raw_candles:

        try:

            epoch = int(candle["epoch"])

            dt = datetime.fromtimestamp(
                epoch,
                timezone.utc
            ).astimezone(WAT)

            candles.append({
                "time": dt,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"])
            })

        except Exception:
            continue

    return candles


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
# CHECK BULLISH SETUP
#
# Reference candle direction DOES NOT MATTER.
#
# BUY:
# confirmation LOW < reference LOW
# AND
# confirmation CLOSE > reference OPEN
#
# ============================================================

def check_buy(reference, confirmation):

    sweep = confirmation["low"] < reference["low"]

    close = confirmation["close"] > reference["open"]

    return sweep, close


# ============================================================
# CHECK BEARISH SETUP
#
# Reference candle direction DOES NOT MATTER.
#
# SELL:
# confirmation HIGH > reference HIGH
# AND
# confirmation CLOSE < reference OPEN
#
# ============================================================

def check_sell(reference, confirmation):

    sweep = confirmation["high"] > reference["high"]

    close = confirmation["close"] < reference["open"]

    return sweep, close


# ============================================================
# PRINT CANDLE
# ============================================================

def print_candle(label, candle):

    print("")
    print(f"📌 {label}")
    print(
        f"Time : "
        f"{candle['time'].strftime('%Y-%m-%d %H:%M')} WAT"
    )
    print(f"Open : {candle['open']}")
    print(f"High : {candle['high']}")
    print(f"Low  : {candle['low']}")
    print(f"Close: {candle['close']}")


# ============================================================
# CHECK ONE SETUP
# ============================================================

def evaluate_setup(
    symbol,
    reference,
    confirmation,
    entry_time,
    reference_time,
    confirmation_time
):

    buy_sweep, buy_close = check_buy(
        reference,
        confirmation
    )

    sell_sweep, sell_close = check_sell(
        reference,
        confirmation
    )

    print("")
    print("------------------------------------------------------------")
    print(
        f"🧪 {symbol} | "
        f"{reference_time} → "
        f"{confirmation_time} → "
        f"{entry_time}"
    )
    print("------------------------------------------------------------")

    print_candle(
        f"REFERENCE {reference_time}",
        reference
    )

    print_candle(
        f"CONFIRMATION {confirmation_time}",
        confirmation
    )

    print("")
    print("🟢 BUY CHECK")
    print(
        f"Sweep below reference low: "
        f"{'✅' if buy_sweep else '❌'}"
    )
    print(
        f"Close above reference open: "
        f"{'✅' if buy_close else '❌'}"
    )

    print("")
    print("🔴 SELL CHECK")
    print(
        f"Sweep above reference high: "
        f"{'✅' if sell_sweep else '❌'}"
    )
    print(
        f"Close below reference open: "
        f"{'✅' if sell_close else '❌'}"
    )

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if buy_sweep and buy_close:

        print("")
        print("🚨🚨🚨 VALID BUY SETUP 🚨🚨🚨")
        print(
            f"📊 Market: {symbol}"
        )
        print(
            f"⏰ LOOK FOR ENTRY: {entry_time} WAT"
        )

        return {
            "symbol": symbol,
            "direction": "BUY",
            "entry": entry_time,
            "reference_time": reference_time,
            "confirmation_time": confirmation_time,
            "reference": reference,
            "confirmation": confirmation
        }

    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    if sell_sweep and sell_close:

        print("")
        print("🚨🚨🚨 VALID SELL SETUP 🚨🚨🚨")
        print(
            f"📊 Market: {symbol}"
        )
        print(
            f"⏰ LOOK FOR ENTRY: {entry_time} WAT"
        )

        return {
            "symbol": symbol,
            "direction": "SELL",
            "entry": entry_time,
            "reference_time": reference_time,
            "confirmation_time": confirmation_time,
            "reference": reference,
            "confirmation": confirmation
        }

    print("")
    print("⚪ No valid setup for this candle pair.")

    return None


# ============================================================
# BUILD TELEGRAM MESSAGE
# ============================================================

def build_message(signal):

    ref = signal["reference"]
    conf = signal["confirmation"]

    if signal["direction"] == "BUY":

        emoji = "🟢"

    else:

        emoji = "🔴"


    return f"""
🚨 SIXSGAMES LIVE SIGNAL 🚨

📊 MARKET: {signal['symbol']}

{emoji} DIRECTION: {signal['direction']}

⏰ LOOK FOR ENTRY:
{signal['entry']} WAT

━━━━━━━━━━━━━━━━━━

📌 REFERENCE CANDLE
{signal['reference_time']}

Open: {ref['open']}
High: {ref['high']}
Low: {ref['low']}
Close: {ref['close']}

━━━━━━━━━━━━━━━━━━

📌 CONFIRMATION CANDLE
{signal['confirmation_time']}

Open: {conf['open']}
High: {conf['high']}
Low: {conf['low']}
Close: {conf['close']}

━━━━━━━━━━━━━━━━━━

✅ Sweep confirmed
✅ Close condition confirmed

🚫 Reference candle direction
does NOT matter.

👀 LOOK FOR YOUR ENTRY.
""".strip()


# ============================================================
# SCAN MARKET
# ============================================================

def scan_market(ws, symbol):

    candles = get_candles(
        ws,
        symbol
    )

    if not candles:

        return []


    # --------------------------------------------------------
    # Only completed candles
    # --------------------------------------------------------

    now = datetime.now(WAT)

    completed = []

    for candle in candles:

        end_time = (
            candle["time"] +
            timedelta(hours=4)
        )

        if end_time <= now:

            completed.append(candle)


    if len(completed) < 3:

        print(
            "⚠️ Not enough completed 4H candles."
        )

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
    # 02:00 → 06:00 → 10:00
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

            signal = evaluate_setup(
                symbol,
                candle_02,
                candle_06,
                "10:00",
                "02:00",
                "06:00"
            )

            if signal:

                signal["date"] = date_value

                signals.append(signal)


    # ========================================================
    # SETUP 2
    #
    # 06:00 → 10:00 → 14:00
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

            signal = evaluate_setup(
                symbol,
                candle_06,
                candle_10,
                "14:00",
                "06:00",
                "10:00"
            )

            if signal:

                signal["date"] = date_value

                signals.append(signal)


    return signals


# ============================================================
# MAIN LIVE LOOP
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("🤖 SIXSGAMES 4H DIAGNOSTIC + LIVE SCANNER")
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


    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:

        print(
            "✅ Telegram secrets detected."
        )

    else:

        print(
            "❌ Telegram secrets missing."
        )


    # Prevent duplicate Telegram alerts
    sent_signals = set()


    while True:

        ws = None

        try:

            ws = connect()

            print("")
            print("=" * 60)
            print("🔎 STARTING 42-MARKET SCAN")
            print("=" * 60)


            total_signals = 0


            for symbol in MARKETS:

                print("")
                print("=" * 60)
                print(
                    f"🔍 CHECKING {symbol}"
                )
                print("=" * 60)


                try:

                    signals = scan_market(
                        ws,
                        symbol
                    )


                    for signal in signals:

                        total_signals += 1


                        signal_id = (
                            f"{signal['symbol']}_"
                            f"{signal['date']}_"
                            f"{signal['entry']}_"
                            f"{signal['direction']}"
                        )


                        if signal_id in sent_signals:

                            print(
                                "ℹ️ Signal already sent."
                            )

                            continue


                        message = build_message(
                            signal
                        )


                        if send_telegram(
                            message
                        ):

                            sent_signals.add(
                                signal_id
                            )


                except Exception as e:

                    print(
                        f"⚠️ Error checking "
                        f"{symbol}: {e}"
                    )


            print("")
            print("=" * 60)
            print("📊 SCAN COMPLETE")
            print("=" * 60)

            print(
                f"Total valid setups: "
                f"{total_signals}"
            )

            print(
                f"😴 Waiting {SCAN_INTERVAL} seconds..."
            )


            if ws:

                ws.close()


            time.sleep(
                SCAN_INTERVAL
            )


        except Exception as e:

            print("")
            print("=" * 60)
            print("❌ SCANNER ERROR")
            print("=" * 60)

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
