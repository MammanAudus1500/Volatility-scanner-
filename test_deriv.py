import json
import time
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES LIVE 4H SWEEP SCANNER
# ============================================================
#
# TIMEZONE:
# Africa/Lagos / WAT = UTC + 1
#
# SETUP 1:
# 02:00 candle -> 06:00 candle -> ENTRY 10:00
#
# BULLISH:
# 06:00 LOW < 02:00 LOW
# AND
# 06:00 CLOSE > 02:00 OPEN
#
# BEARISH:
# 06:00 HIGH > 02:00 HIGH
# AND
# 06:00 CLOSE < 02:00 OPEN
#
# IMPORTANT:
# CLOSE == REFERENCE OPEN = NO SIGNAL
#
# SETUP 2:
# 06:00 candle -> 10:00 candle -> ENTRY 14:00
#
# Same rules.
#
# THIS PROGRAM DOES NOT PLACE TRADES.
# IT ONLY SCANS AND REPORTS SIGNALS.
# ============================================================


DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

GRANULARITY = 14400

# How often the scanner checks the market
CHECK_INTERVAL = 30


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
# CONNECTION
# ============================================================

def connect():

    print("")
    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        DERIV_URL,
        timeout=20
    )

    print("✅ Connected to Deriv")

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

        response = json.loads(raw)

        if response.get("error"):
            return response

        return response


# ============================================================
# GET CURRENT 4H CANDLES
# ============================================================

def get_candles(ws, symbol):

    payload = {
        "ticks_history": symbol,
        "count": 10,
        "end": "latest",
        "style": "candles",
        "granularity": GRANULARITY
    }

    response = request(ws, payload)

    if response.get("error"):

        return None

    candles = response.get("candles", [])

    return candles


# ============================================================
# CONVERT CANDLE
# ============================================================

def convert_candle(candle):

    epoch = int(candle["epoch"])

    dt = datetime.fromtimestamp(
        epoch,
        timezone.utc
    ).astimezone(WAT)

    return {
        "epoch": epoch,
        "time": dt,
        "open": float(candle["open"]),
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "close": float(candle["close"])
    }


# ============================================================
# GET TODAY'S CANDLE
# ============================================================

def find_today_candle(candles, hour):

    now = datetime.now(WAT)

    today = now.date()

    for raw in candles:

        try:

            candle = convert_candle(raw)

        except Exception:

            continue

        if (
            candle["time"].date() == today
            and candle["time"].hour == hour
            and candle["time"].minute == 0
        ):

            return candle

    return None


# ============================================================
# BULLISH CHECK
# ============================================================

def is_bullish(reference, confirmation):

    # Confirmation must sweep the FULL reference low
    swept_low = (
        confirmation["low"]
        <
        reference["low"]
    )

    # Confirmation must close STRICTLY above
    # the reference candle open.
    closed_above_open = (
        confirmation["close"]
        >
        reference["open"]
    )

    return swept_low and closed_above_open


# ============================================================
# BEARISH CHECK
# ============================================================

def is_bearish(reference, confirmation):

    # Confirmation must sweep the FULL reference high
    swept_high = (
        confirmation["high"]
        >
        reference["high"]
    )

    # Confirmation must close STRICTLY below
    # the reference candle open.
    closed_below_open = (
        confirmation["close"]
        <
        reference["open"]
    )

    return swept_high and closed_below_open


# ============================================================
# SIGNAL MEMORY
# ============================================================
#
# Prevents the same pair/setup from being reported repeatedly.
# ============================================================

sent_signals = set()


# ============================================================
# CREATE SIGNAL ID
# ============================================================

def signal_id(
    symbol,
    date,
    confirmation_hour,
    direction
):

    return (
        f"{symbol}_"
        f"{date}_"
        f"{confirmation_hour}_"
        f"{direction}"
    )


# ============================================================
# PRINT BULLISH SIGNAL
# ============================================================

def print_bullish(
    symbol,
    reference,
    confirmation,
    entry_time
):

    print("")
    print("=" * 70)
    print("🟢🟢🟢 BULLISH SETUP FOUND 🟢🟢🟢")
    print("=" * 70)

    print(f"📊 PAIR: {symbol}")

    print(
        f"🕐 Reference candle: "
        f"{reference['time'].strftime('%H:%M')} WAT"
    )

    print(
        f"🕐 Confirmation candle: "
        f"{confirmation['time'].strftime('%H:%M')} WAT"
    )

    print(
        f"🎯 LOOK FOR ENTRY AT: "
        f"{entry_time} WAT"
    )

    print("")
    print("REFERENCE CANDLE")

    print(f"Open : {reference['open']}")
    print(f"High : {reference['high']}")
    print(f"Low  : {reference['low']}")
    print(f"Close: {reference['close']}")

    print("")
    print("CONFIRMATION CANDLE")

    print(f"Open : {confirmation['open']}")
    print(f"High : {confirmation['high']}")
    print(f"Low  : {confirmation['low']}")
    print(f"Close: {confirmation['close']}")

    print("")
    print("✅ Reference LOW swept")
    print("✅ Confirmation CLOSE above reference OPEN")
    print("🎯 MANUALLY LOOK FOR YOUR ENTRY")

    print("=" * 70)
    print("")


# ============================================================
# PRINT BEARISH SIGNAL
# ============================================================

def print_bearish(
    symbol,
    reference,
    confirmation,
    entry_time
):

    print("")
    print("=" * 70)
    print("🔴🔴🔴 BEARISH SETUP FOUND 🔴🔴🔴")
    print("=" * 70)

    print(f"📊 PAIR: {symbol}")

    print(
        f"🕐 Reference candle: "
        f"{reference['time'].strftime('%H:%M')} WAT"
    )

    print(
        f"🕐 Confirmation candle: "
        f"{confirmation['time'].strftime('%H:%M')} WAT"
    )

    print(
        f"🎯 LOOK FOR ENTRY AT: "
        f"{entry_time} WAT"
    )

    print("")
    print("REFERENCE CANDLE")

    print(f"Open : {reference['open']}")
    print(f"High : {reference['high']}")
    print(f"Low  : {reference['low']}")
    print(f"Close: {reference['close']}")

    print("")
    print("CONFIRMATION CANDLE")

    print(f"Open : {confirmation['open']}")
    print(f"High : {confirmation['high']}")
    print(f"Low  : {confirmation['low']}")
    print(f"Close: {confirmation['close']}")

    print("")
    print("✅ Reference HIGH swept")
    print("✅ Confirmation CLOSE below reference OPEN")
    print("🎯 MANUALLY LOOK FOR YOUR ENTRY")

    print("=" * 70)
    print("")


# ============================================================
# CHECK 10 AM SETUP
# ============================================================

def check_10am_setup(
    symbol,
    candles
):

    candle_02 = find_today_candle(
        candles,
        2
    )

    candle_06 = find_today_candle(
        candles,
        6
    )

    # Both candles must exist
    if not candle_02 or not candle_06:

        return

    # Make sure 06:00 candle is finished
    now = datetime.now(WAT)

    if now < candle_06["time"] + timedelta(hours=4):

        return

    # -----------------------------------------
    # BULLISH
    # -----------------------------------------

    if is_bullish(
        candle_02,
        candle_06
    ):

        sid = signal_id(
            symbol,
            now.date(),
            6,
            "BUY10"
        )

        if sid not in sent_signals:

            sent_signals.add(sid)

            print_bullish(
                symbol,
                candle_02,
                candle_06,
                "10:00"
            )

            return


    # -----------------------------------------
    # BEARISH
    # -----------------------------------------

    if is_bearish(
        candle_02,
        candle_06
    ):

        sid = signal_id(
            symbol,
            now.date(),
            6,
            "SELL10"
        )

        if sid not in sent_signals:

            sent_signals.add(sid)

            print_bearish(
                symbol,
                candle_02,
                candle_06,
                "10:00"
            )

            return


# ============================================================
# CHECK 2 PM SETUP
# ============================================================

def check_2pm_setup(
    symbol,
    candles
):

    candle_06 = find_today_candle(
        candles,
        6
    )

    candle_10 = find_today_candle(
        candles,
        10
    )

    if not candle_06 or not candle_10:

        return

    # Make sure 10:00 candle is finished
    now = datetime.now(WAT)

    if now < candle_10["time"] + timedelta(hours=4):

        return


    # -----------------------------------------
    # BULLISH
    # -----------------------------------------

    if is_bullish(
        candle_06,
        candle_10
    ):

        sid = signal_id(
            symbol,
            now.date(),
            10,
            "BUY14"
        )

        if sid not in sent_signals:

            sent_signals.add(sid)

            print_bullish(
                symbol,
                candle_06,
                candle_10,
                "14:00"
            )

            return


    # -----------------------------------------
    # BEARISH
    # -----------------------------------------

    if is_bearish(
        candle_06,
        candle_10
    ):

        sid = signal_id(
            symbol,
            now.date(),
            10,
            "SELL14"
        )

        if sid not in sent_signals:

            sent_signals.add(sid)

            print_bearish(
                symbol,
                candle_06,
                candle_10,
                "14:00"
            )

            return


# ============================================================
# SCAN ALL MARKETS
# ============================================================

def scan_all_markets(ws):

    print("")
    print(
        f"🔄 Scan started at "
        f"{datetime.now(WAT).strftime('%Y-%m-%d %H:%M:%S')} WAT"
    )

    for symbol in MARKETS:

        try:

            candles = get_candles(
                ws,
                symbol
            )

            if not candles:

                print(
                    f"⚠️ {symbol}: no candle data"
                )

                continue

            check_10am_setup(
                symbol,
                candles
            )

            check_2pm_setup(
                symbol,
                candles
            )

        except Exception as e:

            print(
                f"⚠️ {symbol}: {e}"
            )


# ============================================================
# MAIN LIVE LOOP
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("🤖 SIXSGAMES LIVE 4H SWEEP SCANNER")
    print("=" * 70)

    print("")
    print("Timezone: Africa/Lagos (WAT)")
    print("Markets:", len(MARKETS))
    print("Timeframe: 4 Hours")

    print("")
    print("10 AM SETUP:")
    print("02:00 → 06:00 → ENTRY 10:00")

    print("")
    print("2 PM SETUP:")
    print("06:00 → 10:00 → ENTRY 14:00")

    print("")
    print("🚫 No trade execution")
    print("📢 Signal scanner only")

    ws = None

    while True:

        try:

            if ws is None:

                ws = connect()

            scan_all_markets(ws)

            print("")
            print(
                f"😴 Waiting {CHECK_INTERVAL} seconds "
                f"before next scan..."
            )

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:

            print("")
            print("🛑 Scanner stopped manually.")

            break

        except Exception as e:

            print("")
            print("⚠️ CONNECTION/SCANNER ERROR")
            print(str(e))

            try:

                if ws:
                    ws.close()

            except Exception:
                pass

            ws = None

            print(
                "🔄 Reconnecting in 10 seconds..."
            )

            time.sleep(10)


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
