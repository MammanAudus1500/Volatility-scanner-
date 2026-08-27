import json
import websocket
import time
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES - TIME BASED 4H STRATEGY SCANNER
# ============================================================
#
# Strategy:
#
# BULLISH:
# Reference candle: 02:00 WAT
# Confirmation candle: 06:00 WAT
# Entry window: 10:00 WAT
#
# Conditions:
# 1. 06:00 candle LOW must go BELOW 02:00 candle LOW
# 2. 06:00 candle CLOSE must be ABOVE 02:00 candle OPEN
# 3. If close == 02:00 open -> NO SIGNAL
#
# BEARISH:
# Reference candle: 02:00 WAT
# Confirmation candle: 06:00 WAT
# Entry window: 10:00 WAT
#
# Conditions:
# 1. 06:00 candle HIGH must go ABOVE 02:00 candle HIGH
# 2. 06:00 candle CLOSE must be BELOW 02:00 candle OPEN
# 3. If close == 02:00 open -> NO SIGNAL
#
# SECOND SETUP:
#
# Reference candle: 06:00 WAT
# Confirmation candle: 10:00 WAT
# Entry window: 14:00 WAT
#
# Same bullish/bearish rules.
#
# IMPORTANT:
# This is a SIGNAL SCANNER only.
# It does NOT place trades.
# ============================================================


URL = "wss://api.derivws.com/trading/v1/options/ws/public"

# WAT = UTC + 1
WAT = timezone(timedelta(hours=1))

# How many completed 4H candles to request
CANDLE_COUNT = 50


def send_request(ws, request):
    """Send JSON request to Deriv."""
    ws.send(json.dumps(request))


def receive_response(ws, timeout=20):
    """Receive one valid JSON response."""
    ws.settimeout(timeout)

    while True:
        message = ws.recv()

        if not message:
            continue

        response = json.loads(message)

        if response.get("error"):
            raise Exception(str(response["error"]))

        return response


def get_active_markets(ws):
    """
    Discover active Deriv markets.

    Uses the current active_symbols response format:
    underlying_symbol
    underlying_symbol_name
    """

    print("\n🔎 Discovering Deriv markets...")

    send_request(ws, {
        "active_symbols": "brief",
        "req_id": 100
    })

    while True:
        response = receive_response(ws)

        if response.get("msg_type") == "active_symbols":

            markets = response.get("active_symbols", [])

            print(f"✅ Deriv returned {len(markets)} active markets")

            return markets


def normalize_name(name):
    """Make market names easier to compare."""

    return (
        name.upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
        .replace("(", "")
        .replace(")", "")
    )


def choose_markets(all_markets):
    """
    Select the markets we want to scan.

    We use the market names returned by Deriv rather than
    inventing symbol codes.
    """

    wanted = [
        "VOLATILITY5",
        "VOLATILITY10",
        "VOLATILITY15",
        "VOLATILITY25",
        "VOLATILITY30",
        "VOLATILITY50",
        "VOLATILITY75",
        "VOLATILITY90",
        "VOLATILITY100",
        "VOLATILITY150",

        "JUMP10INDEX",
        "JUMP25INDEX",
        "JUMP50INDEX",
        "JUMP75INDEX",
        "JUMP100INDEX",

        "STEPINDEX",
        "STEPINDEX200",
        "STEPINDEX300",
        "STEPINDEX400",
        "STEPINDEX500",

        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "GBPJPY",
        "USDCAD",
        "EURCAD",
        "AUDUSD",
        "AUDCAD",
        "NZDJPY",
        "AUDNZD",
        "EURGBP",
        "NZDCHF",
        "CADCHF",
        "EURCHF",
        "CHFJPY",
        "GBPCHF",
        "NZDCAD",
        "GBPNZD",
        "CADJPY",
        "AUDCHF",
        "GBPAUD",
        "USDCHF",

        "XAUUSD",
        "BTCUSD",
        "US100"
    ]

    selected = []

    for market in all_markets:

        name = market.get(
            "underlying_symbol_name",
            market.get("display_name", "")
        )

        symbol = market.get(
            "underlying_symbol",
            market.get("symbol", "")
        )

        normalized = normalize_name(name)

        if normalized in wanted:

            selected.append({
                "name": name,
                "symbol": symbol
            })

    return selected


def get_4h_candles(ws, symbol):
    """
    Request completed 4-hour candles.

    Granularity:
    14400 seconds = 4 hours
    """

    send_request(ws, {
    "ticks_history": symbol,
    "count": CANDLE_COUNT,
    "end": "latest",
    "style": "candles",
    "granularity": 14400,
    "req_id": 200
})
    })

    while True:

        response = receive_response(ws)

        if response.get("msg_type") == "candles":

            candles = response.get("candles", [])

            return candles


def candle_wat_time(candle):
    """Convert candle epoch to WAT datetime."""

    epoch = int(candle["epoch"])

    return datetime.fromtimestamp(
        epoch,
        timezone.utc
    ).astimezone(WAT)


def find_candle(candles, hour):
    """
    Find a completed 4H candle beginning at the requested
    WAT hour.
    """

    for candle in candles:

        dt = candle_wat_time(candle)

        if dt.hour == hour and dt.minute == 0:

            return candle

    return None


def bullish_setup(reference, confirmation):
    """
    Bullish rules:

    Confirmation LOW < reference LOW
    Confirmation CLOSE > reference OPEN

    Strict comparisons are intentional.
    """

    reference_low = float(reference["low"])
    reference_open = float(reference["open"])

    confirmation_low = float(confirmation["low"])
    confirmation_close = float(confirmation["close"])

    swept_low = confirmation_low < reference_low
    closed_above_open = confirmation_close > reference_open

    return swept_low and closed_above_open


def bearish_setup(reference, confirmation):
    """
    Bearish rules:

    Confirmation HIGH > reference HIGH
    Confirmation CLOSE < reference OPEN

    Strict comparisons are intentional.
    """

    reference_high = float(reference["high"])
    reference_open = float(reference["open"])

    confirmation_high = float(confirmation["high"])
    confirmation_close = float(confirmation["close"])

    swept_high = confirmation_high > reference_high
    closed_below_open = confirmation_close < reference_open

    return swept_high and closed_below_open


def analyze_setup(candles, reference_hour, confirmation_hour, entry_hour):
    """
    Analyze one 4H time-based setup.
    """

    reference = find_candle(candles, reference_hour)
    confirmation = find_candle(candles, confirmation_hour)

    if reference is None or confirmation is None:
        return None

    # Make sure the confirmation candle is later than
    # the reference candle.
    reference_time = candle_wat_time(reference)
    confirmation_time = candle_wat_time(confirmation)

    if confirmation_time <= reference_time:
        return None

    # -------------------------
    # BULLISH
    # -------------------------

    if bullish_setup(reference, confirmation):

        return {
            "direction": "BULLISH",
            "reference": reference,
            "confirmation": confirmation,
            "entry_hour": entry_hour
        }

    # -------------------------
    # BEARISH
    # -------------------------

    if bearish_setup(reference, confirmation):

        return {
            "direction": "BEARISH",
            "reference": reference,
            "confirmation": confirmation,
            "entry_hour": entry_hour
        }

    return None


def print_signal(market, signal, reference_hour, confirmation_hour):

    reference = signal["reference"]
    confirmation = signal["confirmation"]

    direction = signal["direction"]

    print("\n")
    print("🚨" + "=" * 55)
    print("🚨 SIXSGAMES SIGNAL FOUND")
    print("🚨" + "=" * 55)

    print(f"📊 Market: {market['name']}")
    print(f"🔑 Symbol: {market['symbol']}")
    print(f"📈 Direction: {direction}")

    print(
        f"🕐 Reference candle: "
        f"{reference_hour:02d}:00 WAT"
    )

    print(
        f"🕐 Confirmation candle: "
        f"{confirmation_hour:02d}:00 WAT"
    )

    print(
        f"🎯 Entry window: "
        f"{signal['entry_hour']:02d}:00 WAT"
    )

    print("\nREFERENCE CANDLE")

    print(f"Open : {reference['open']}")
    print(f"High : {reference['high']}")
    print(f"Low  : {reference['low']}")
    print(f"Close: {reference['close']}")

    print("\nCONFIRMATION CANDLE")

    print(f"Open : {confirmation['open']}")
    print(f"High : {confirmation['high']}")
    print(f"Low  : {confirmation['low']}")
    print(f"Close: {confirmation['close']}")

    if direction == "BULLISH":

        print("\n✅ LOW SWEPT")
        print("✅ CLOSE ABOVE REFERENCE OPEN")

    else:

        print("\n✅ HIGH SWEPT")
        print("✅ CLOSE BELOW REFERENCE OPEN")

    print(
        f"\n🎯 LOOK FOR YOUR ENTRY AT "
        f"{signal['entry_hour']:02d}:00 WAT"
    )

    print("🚨" + "=" * 55)


def scan_market(ws, market):

    symbol = market["symbol"]

    try:

        candles = get_4h_candles(ws, symbol)

        if not candles:
            return []

        signals = []

        # ------------------------------------------------
        # SETUP 1
        #
        # 02:00 -> 06:00 -> 10:00
        # ------------------------------------------------

        signal_1 = analyze_setup(
            candles,
            reference_hour=2,
            confirmation_hour=6,
            entry_hour=10
        )

        if signal_1:
            signals.append(
                (
                    signal_1,
                    2,
                    6
                )
            )

        # ------------------------------------------------
        # SETUP 2
        #
        # 06:00 -> 10:00 -> 14:00
        # ------------------------------------------------

        signal_2 = analyze_setup(
            candles,
            reference_hour=6,
            confirmation_hour=10,
            entry_hour=14
        )

        if signal_2:
            signals.append(
                (
                    signal_2,
                    6,
                    10
                )
            )

        return signals

    except Exception as e:

        print(
            f"⚠️ {market['name']} "
            f"({symbol}) error: {e}"
        )

        return []


def main():

    print("=" * 65)
    print("🤖 SIXSGAMES TIME-BASED 4H STRATEGY SCANNER")
    print("=" * 65)

    ws = None

    try:

        print("\n🔌 Connecting to Deriv...")

        ws = websocket.create_connection(
            URL,
            timeout=20
        )

        print("✅ Connected successfully!")

        # ------------------------------------------------
        # DISCOVER MARKETS
        # ------------------------------------------------

        all_markets = get_active_markets(ws)

        markets = choose_markets(all_markets)

        print(
            f"\n📊 Requested markets available: "
            f"{len(markets)}"
        )

        if not markets:

            print(
                "\n❌ No requested markets were found."
            )

            print(
                "Check the active_symbols response "
                "and market-name mapping."
            )

            return

        # ------------------------------------------------
        # SHOW MARKETS
        # ------------------------------------------------

        print("\n📋 MARKETS TO SCAN")
        print("-" * 65)

        for i, market in enumerate(markets, 1):

            print(
                f"{i:02d}. "
                f"{market['name']} "
                f"→ {market['symbol']}"
            )

        print("-" * 65)

        # ------------------------------------------------
        # SCAN
        # ------------------------------------------------

        print("\n🔍 STARTING STRATEGY SCAN...")
        print(
            "Timezone: WAT (UTC+1)"
        )

        print(
            "Setup 1: 02:00 → 06:00 → 10:00"
        )

        print(
            "Setup 2: 06:00 → 10:00 → 14:00"
        )

        total_signals = 0

        for market in markets:

            print(
                f"\n🔎 Scanning "
                f"{market['name']} "
                f"({market['symbol']})..."
            )

            signals = scan_market(
                ws,
                market
            )

            if signals:

                for signal, ref_hour, conf_hour in signals:

                    print_signal(
                        market,
                        signal,
                        ref_hour,
                        conf_hour
                    )

                    total_signals += 1

            else:

                print("   No valid setup found.")

        # ------------------------------------------------
        # SUMMARY
        # ------------------------------------------------

        print("\n")
        print("=" * 65)
        print("📊 SCAN COMPLETE")
        print("=" * 65)

        print(
            f"Markets scanned: {len(markets)}"
        )

        print(
            f"Valid signals found: {total_signals}"
        )

        if total_signals == 0:

            print(
                "\nℹ️ No valid setups were found "
                "in the requested historical candles."
            )

        else:

            print(
                "\n🚨 Review the signals above "
                "for your manual entries."
            )

        print("\n🤖 Scanner finished successfully.")

    except Exception as e:

        print("\n❌ SCANNER ERROR")
        print(str(e))

    finally:

        if ws:

            try:
                ws.close()
            except:
                pass


if __name__ == "__main__":
    main()
