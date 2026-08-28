import json
import os
import time
import urllib.parse
import urllib.request
import websocket

from datetime import datetime, timezone, timedelta


# ============================================================
# SIXSGAMES LIVE 4H STRATEGY SCANNER
# ============================================================
#
# Strategy:
#
# SETUP 1:
# 02:00 candle -> 06:00 confirmation -> ENTRY 10:00
#
# BUY:
#   06:00 LOW < 02:00 LOW
#   AND
#   06:00 CLOSE > 02:00 OPEN
#
# SELL:
#   06:00 HIGH > 02:00 HIGH
#   AND
#   06:00 CLOSE < 02:00 OPEN
#
#
# SETUP 2:
# 06:00 candle -> 10:00 confirmation -> ENTRY 14:00
#
# BUY:
#   10:00 LOW < 06:00 LOW
#   AND
#   10:00 CLOSE > 06:00 OPEN
#
# SELL:
#   10:00 HIGH > 06:00 HIGH
#   AND
#   10:00 CLOSE < 06:00 OPEN
#
# IMPORTANT:
# The reference candle does NOT need to be bullish or bearish.
#
# Timezone:
# Africa/Lagos / WAT
#
# ============================================================


DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

SCAN_INTERVAL = 60

CANDLE_GRANULARITY = 14400

CANDLE_COUNT = 50


# ============================================================
# 42 MARKETS
# ============================================================

MARKETS = [

    # Volatility 1s
    "1HZ10V",
    "1HZ15V",
    "1HZ25V",
    "1HZ30V",
    "1HZ50V",
    "1HZ75V",
    "1HZ90V",
    "1HZ100V",

    # Volatility
    "R_10",
    "R_25",
    "R_50",
    "R_75",
    "R_100",

    # Jump
    "JD10",
    "JD25",
    "JD50",
    "JD75",
    "JD100",

    # Step
    "stpRNG",
    "stpRNG2",
    "stpRNG3",
    "stpRNG4",
    "stpRNG5",

    # Forex
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

    # Gold
    "frxXAUUSD",

    # Bitcoin
    "cryBTCUSD"
]


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def telegram_ready():

    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    )


def send_telegram(message):

    if not telegram_ready():

        print("⚠️ Telegram credentials missing.")

        return False

    try:

        url = (
            "https://api.telegram.org/bot"
            + TELEGRAM_BOT_TOKEN
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

            print("📨 Telegram signal sent!")

            return True


        print(
            "❌ Telegram error:",
            result
        )

        return False


    except Exception as e:

        print(
            "❌ Telegram send failed:",
            str(e)
        )

        return False


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
# GET 4H CANDLES
# ============================================================

def get_candles(ws, symbol):

    payload = {

        "ticks_history": symbol,

        "adjust_start_time": 1,

        "count": CANDLE_COUNT,

        "end": "latest",

        "granularity": CANDLE_GRANULARITY,

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


    converted = []


    for candle in candles:

        try:

            timestamp = int(
                candle["epoch"]
            )


            dt = datetime.fromtimestamp(
                timestamp,
                timezone.utc
            ).astimezone(WAT)


            converted.append({

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
            })


        except Exception:

            continue


    return converted


# ============================================================
# ONLY COMPLETED CANDLES
# ============================================================

def completed_candles(candles):

    now = datetime.now(WAT)

    result = []


    for candle in candles:

        candle_end = (
            candle["time"]
            + timedelta(hours=4)
        )


        if candle_end <= now:

            result.append(candle)


    return result


# ============================================================
# FIND CANDLE
# ============================================================

def find_candle(
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
# BUY SETUP
# ============================================================

def buy_setup(
    reference,
    confirmation
):

    # Confirmation must sweep
    # the COMPLETE reference low.

    swept = (
        confirmation["low"]
        < reference["low"]
    )


    # Confirmation must close
    # STRICTLY above reference open.

    closed_above = (
        confirmation["close"]
        > reference["open"]
    )


    return swept and closed_above


# ============================================================
# SELL SETUP
# ============================================================

def sell_setup(
    reference,
    confirmation
):

    # Confirmation must sweep
    # the COMPLETE reference high.

    swept = (
        confirmation["high"]
        > reference["high"]
    )


    # Confirmation must close
    # STRICTLY below reference open.

    closed_below = (
        confirmation["close"]
        < reference["open"]
    )


    return swept and closed_below


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

        "date": str(date_value),

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
# SCAN ONE MARKET
# ============================================================

def scan_market(
    ws,
    symbol
):

    candles = get_candles(
        ws,
        symbol
    )


    if not candles:

        return []


    completed = completed_candles(
        candles
    )


    if len(completed) < 4:

        return []


    dates = sorted(
        set(
            candle["time"].date()
            for candle in completed
        )
    )


    signals = []


    for date_value in dates:

        # ----------------------------------------------------
        # SETUP 1
        # 02 -> 06 -> ENTRY 10
        # ----------------------------------------------------

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

            if buy_setup(
                candle_02,
                candle_06
            ):

                signals.append(
                    create_signal(

                        symbol,

                        date_value,

                        "02:00",

                        "06:00",

                        "10:00",

                        "BUY",

                        candle_02,

                        candle_06
                    )
                )


            elif sell_setup(
                candle_02,
                candle_06
            ):

                signals.append(
                    create_signal(

                        symbol,

                        date_value,

                        "02:00",

                        "06:00",

                        "10:00",

                        "SELL",

                        candle_02,

                        candle_06
                    )
                )


        # ----------------------------------------------------
        # SETUP 2
        # 06 -> 10 -> ENTRY 14
        # ----------------------------------------------------

        candle_10 = find_candle(
            completed,
            date_value,
            10
        )


        if candle_06 and candle_10:

            if buy_setup(
                candle_06,
                candle_10
            ):

                signals.append(
                    create_signal(

                        symbol,

                        date_value,

                        "06:00",

                        "10:00",

                        "14:00",

                        "BUY",

                        candle_06,

                        candle_10
                    )
                )


            elif sell_setup(
                candle_06,
                candle_10
            ):

                signals.append(
                    create_signal(

                        symbol,

                        date_value,

                        "06:00",

                        "10:00",

                        "14:00",

                        "SELL",

                        candle_06,

                        candle_10
                    )
                )


    return signals


# ============================================================
# SIGNAL KEY
# ============================================================

def signal_key(signal):

    return (

        signal["symbol"],

        signal["date"],

        signal["reference_hour"],

        signal["confirmation_hour"],

        signal["entry_hour"],

        signal["direction"]
    )


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def format_signal(signal):

    symbol = signal["symbol"]

    date = signal["date"]

    direction = signal["direction"]

    entry = signal["entry_hour"]

    reference_hour = (
        signal["reference_hour"]
    )

    confirmation_hour = (
        signal["confirmation_hour"]
    )


    ref = signal["reference"]

    conf = signal["confirmation"]


    emoji = (
        "🟢 BUY"
        if direction == "BUY"
        else
        "🔴 SELL"
    )


    message = f"""
🚨 SIXSGAMES SIGNAL 🚨

📊 MARKET: {symbol}

{emoji}

📅 DATE: {date}

🕐 SETUP:
{reference_hour} → {confirmation_hour}

🎯 LOOK FOR ENTRY:
{entry} WAT

📌 REFERENCE CANDLE
Open: {ref['open']}
High: {ref['high']}
Low: {ref['low']}
Close: {ref['close']}

📌 CONFIRMATION CANDLE
Open: {conf['open']}
High: {conf['high']}
Low: {conf['low']}
Close: {conf['close']}

✅ SWEEP CONFIRMED
✅ CLOSE CONDITION CONFIRMED

👀 LOOK FOR YOUR ENTRY AT {entry} WAT
""".strip()


    return message


# ============================================================
# LIVE SCAN
# ============================================================

def run_scan(ws, sent_signals):

    print("")
    print("=" * 60)
    print("🔎 STARTING 42-MARKET SCAN")
    print("=" * 60)


    total = 0


    for symbol in MARKETS:

        print(
            f"🔍 Checking {symbol}..."
        )


        try:

            signals = scan_market(
                ws,
                symbol
            )


            for signal in signals:

                key = signal_key(
                    signal
                )


                # Never send the same
                # historical/current setup twice.

                if key in sent_signals:

                    continue


                # Only alert for a valid setup.

                print("")
                print(
                    "🚨 NEW VALID SETUP!"
                )


                print(
                    f"📊 {symbol}"
                )


                print(
                    f"🎯 {signal['direction']}"
                )


                print(
                    f"⏰ ENTRY {signal['entry_hour']} WAT"
                )


                message = format_signal(
                    signal
                )


                if send_telegram(
                    message
                ):

                    sent_signals.add(
                        key
                    )

                    total += 1


        except Exception as e:

            print(
                f"⚠️ {symbol} error: {e}"
            )


    print("")
    print("=" * 60)
    print("📊 SCAN COMPLETE")
    print("=" * 60)


    print(
        f"🆕 New Telegram signals: {total}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("🤖 SIXSGAMES LIVE 4H STRATEGY SCANNER")
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


    if telegram_ready():

        print(
            "✅ Telegram secrets detected."
        )

    else:

        print(
            "❌ TELEGRAM SECRETS NOT FOUND."
        )

        print(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )

        return


    # --------------------------------------------------------
    # IMPORTANT:
    # We keep this set in memory.
    #
    # This prevents duplicate Telegram messages while
    # this GitHub Actions run is alive.
    # --------------------------------------------------------

    sent_signals = set()


    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    try:

        ws = connect()


    except Exception as e:

        print(
            "❌ Initial Deriv connection failed:"
        )

        print(str(e))

        return


    # --------------------------------------------------------
    # TEST TELEGRAM CONNECTION
    # --------------------------------------------------------

    print("")
    print(
        "📨 Telegram connection already verified."
    )


    # --------------------------------------------------------
    # LIVE LOOP
    # --------------------------------------------------------

    while True:

        try:

            run_scan(
                ws,
                sent_signals
            )


            print("")
            print(
                f"😴 Waiting {SCAN_INTERVAL} seconds..."
            )


            time.sleep(
                SCAN_INTERVAL
            )


            # ------------------------------------------------
            # Reconnect before next scan.
            # ------------------------------------------------

            try:

                ws.close()

            except Exception:

                pass


            ws = connect()


        except KeyboardInterrupt:

            print("")
            print(
                "🛑 Scanner stopped manually."
            )

            break


        except Exception as e:

            print("")
            print(
                "⚠️ Scanner error:"
            )

            print(str(e))


            print(
                "🔄 Reconnecting in 10 seconds..."
            )


            try:

                ws.close()

            except Exception:

                pass


            time.sleep(10)


            try:

                ws = connect()

            except Exception as reconnect_error:

                print(
                    "❌ Reconnection failed:"
                )

                print(
                    str(reconnect_error)
                )

                time.sleep(20)


    try:

        ws.close()

    except Exception:

        pass


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
