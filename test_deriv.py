import json
import websocket
from datetime import datetime, timezone, timedelta

print("================================================")
print("🤖 SIXSGAMES TIME-BASED 4H STRATEGY SCANNER")
print("================================================")

URL = "wss://api.derivws.com/trading/v1/options/ws/public"

# These are the markets we requested.
# The scanner will use only markets that Deriv actually returns.
WANTED_MARKETS = [
    "Volatility 10 (1s)",
    "Volatility 15 (1s)",
    "Volatility 25 (1s)",
    "Volatility 30 (1s)",
    "Volatility 50 (1s)",
    "Volatility 75 (1s)",
    "Volatility 90 (1s)",
    "Volatility 100 (1s)",

    "Volatility 10",
    "Volatility 25",
    "Volatility 50",
    "Volatility 75",
    "Volatility 100",

    "Volatility 150",
    "Volatility 150 (1s)",
    "Volatility 5",
    "Volatility 5 (1s)",
    "Volatility 90",

    "Jump 10 Index",
    "Jump 25 Index",
    "Jump 50 Index",
    "Jump 75 Index",
    "Jump 100 Index",

    "Step Index",
    "Step Index 200",
    "Step Index 300",
    "Step Index 400",
    "Step Index 500",

    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "GBP/JPY",
    "USD/CAD",
    "EUR/CAD",
    "AUD/USD",
    "AUD/CAD",
    "NZD/JPY",
    "AUD/NZD",
    "EUR/GBP",
    "NZD/CHF",
    "CAD/CHF",
    "EUR/CHF",
    "CHF/JPY",
    "GBP/CHF",
    "NZD/CAD",
    "GBP/NZD",
    "CAD/JPY",
    "AUD/CHF",
    "GBP/AUD",
    "USD/CHF",
    "Gold/USD",
    "BTC/USD",
    "US 100"
]


def wat_datetime(epoch):
    """Convert Unix timestamp to Nigeria time."""
    return datetime.fromtimestamp(
        epoch,
        timezone.utc
    ) + timedelta(hours=1)


def get_market_list(ws):
    """Get active Deriv markets."""

    request = {
        "active_symbols": "brief",
        "req_id": 1
    }

    ws.send(json.dumps(request))

    while True:

        response = json.loads(ws.recv())

        if response.get("error"):
            raise Exception(response["error"])

        if response.get("msg_type") == "active_symbols":

            return response.get("active_symbols", [])


def get_1h_candles(ws, symbol):
    """Get recent 1-hour candles."""

    request = {
        "ticks_history": symbol,
        "style": "candles",
        "granularity": 3600,
        "count": 120,
        "end": "latest",
        "req_id": 2
    }

    ws.send(json.dumps(request))

    while True:

        response = json.loads(ws.recv())

        if response.get("error"):

            return []

        if response.get("msg_type") == "candles":

            return response.get("candles", [])


def build_4h_candles(hourly_candles):
    """
    Build our own 4-hour candles.

    The 4H candles are aligned to:

    02:00
    06:00
    10:00
    14:00
    18:00
    22:00 WAT
    """

    groups = {}

    for candle in hourly_candles:

        dt = wat_datetime(candle["epoch"])

        hour = dt.hour

        # We only use 4H blocks beginning at
        # 02, 06, 10, 14, 18 and 22.
        block_start = ((hour - 2) // 4) * 4 + 2

        if block_start >= 24:
            block_start -= 24

        # Determine the trading date of the block.
        date = dt.date()

        # 00:00 and 01:00 belong to the previous 22:00 block.
        if hour < 2:
            date = date - timedelta(days=1)

        key = (date, block_start)

        if key not in groups:
            groups[key] = []

        groups[key].append(candle)

    result = []

    for (date, start_hour), candles in groups.items():

        candles = sorted(
            candles,
            key=lambda x: x["epoch"]
        )

        # We need exactly 4 hourly candles.
        if len(candles) != 4:
            continue

        opens = float(candles[0]["open"])
        highs = max(float(c["high"]) for c in candles)
        lows = min(float(c["low"]) for c in candles)
        closes = float(candles[-1]["close"])

        result.append({
            "date": date,
            "hour": start_hour,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes
        })

    result.sort(
        key=lambda x: (x["date"], x["hour"])
    )

    return result


def find_candle(candles, date, hour):

    for candle in candles:

        if (
            candle["date"] == date
            and candle["hour"] == hour
        ):
            return candle

    return None


def check_10am_setup(candles):
    """
    10 AM setup:

    Reference = 2 AM candle
    Sweep      = 6 AM candle

    Bullish:
        6AM Low < 2AM Low
        AND
        6AM Close > 2AM Open

    Bearish:
        6AM High > 2AM High
        AND
        6AM Close < 2AM Open
    """

    signals = []

    dates = sorted(
        set(c["date"] for c in candles)
    )

    for date in dates:

        reference = find_candle(
            candles,
            date,
            2
        )

        sweep = find_candle(
            candles,
            date,
            6
        )

        if not reference or not sweep:
            continue

        # BULLISH
        if (
            sweep["low"] < reference["low"]
            and
            sweep["close"] > reference["open"]
        ):

            signals.append({
                "date": date,
                "entry_time": "10:00 WAT",
                "direction": "BULLISH",
                "reference": "02:00",
                "sweep": "06:00",
                "reference_open": reference["open"],
                "reference_low": reference["low"],
                "sweep_low": sweep["low"],
                "sweep_close": sweep["close"]
            })

        # BEARISH
        elif (
            sweep["high"] > reference["high"]
            and
            sweep["close"] < reference["open"]
        ):

            signals.append({
                "date": date,
                "entry_time": "10:00 WAT",
                "direction": "BEARISH",
                "reference": "02:00",
                "sweep": "06:00",
                "reference_open": reference["open"],
                "reference_high": reference["high"],
                "sweep_high": sweep["high"],
                "sweep_close": sweep["close"]
            })

    return signals


def check_2pm_setup(candles):
    """
    2 PM setup:

    Reference = 6 AM candle
    Sweep      = 10 AM candle

    Bullish:
        10AM Low < 6AM Low
        AND
        10AM Close > 6AM Open

    Bearish:
        10AM High > 6AM High
        AND
        10AM Close < 6AM Open
    """

    signals = []

    dates = sorted(
        set(c["date"] for c in candles)
    )

    for date in dates:

        reference = find_candle(
            candles,
            date,
            6
        )

        sweep = find_candle(
            candles,
            date,
            10
        )

        if not reference or not sweep:
            continue

        # BULLISH
        if (
            sweep["low"] < reference["low"]
            and
            sweep["close"] > reference["open"]
        ):

            signals.append({
                "date": date,
                "entry_time": "14:00 WAT",
                "direction": "BULLISH",
                "reference": "06:00",
                "sweep": "10:00",
                "reference_open": reference["open"],
                "reference_low": reference["low"],
                "sweep_low": sweep["low"],
                "sweep_close": sweep["close"]
            })

        # BEARISH
        elif (
            sweep["high"] > reference["high"]
            and
            sweep["close"] < reference["open"]
        ):

            signals.append({
                "date": date,
                "entry_time": "14:00 WAT",
                "direction": "BEARISH",
                "reference": "06:00",
                "sweep": "10:00",
                "reference_open": reference["open"],
                "reference_high": reference["high"],
                "sweep_high": sweep["high"],
                "sweep_close": sweep["close"]
            })

    return signals


try:

    print("")
    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        URL,
        timeout=20
    )

    print("✅ Connected successfully!")

    print("")
    print("📡 Discovering available markets...")

    active_markets = get_market_list(ws)

    # Match requested display names to Deriv symbols.
    market_map = {}

    for market in active_markets:

        name = market.get(
            "display_name",
            ""
        ).strip()

        symbol = market.get(
            "symbol",
            ""
        )

        if name in WANTED_MARKETS:

            market_map[name] = symbol

    print(
        f"✅ Requested markets available: "
        f"{len(market_map)}"
    )

    print("")
    print("==============================================")
    print("🚨 SCANNING FOR YOUR TIME-BASED SETUPS")
    print("==============================================")

    total_signals = 0

    for name, symbol in sorted(
        market_map.items()
    ):

        print("")
        print(f"🔎 {name} → {symbol}")

        hourly = get_1h_candles(
            ws,
            symbol
        )

        if len(hourly) < 20:

            print("⚠️ Not enough candle data")
            continue

        four_hour = build_4h_candles(
            hourly
        )

        signals_10am = check_10am_setup(
            four_hour
        )

        signals_2pm = check_2pm_setup(
            four_hour
        )

        signals = (
            signals_10am
            +
            signals_2pm
        )

        if not signals:

            print("   No valid setup found.")

            continue

        for signal in signals:

            total_signals += 1

            print("")
            print("   🚨🚨 SIGNAL FOUND 🚨🚨")
            print(
                f"   PAIR: {name}"
            )
            print(
                f"   DATE: {signal['date']}"
            )
            print(
                f"   ENTRY TIME: "
                f"{signal['entry_time']}"
            )
            print(
                f"   DIRECTION: "
                f"{signal['direction']}"
            )

            print(
                f"   REFERENCE CANDLE: "
                f"{signal['reference']} WAT"
            )

            print(
                f"   SWEEP CANDLE: "
                f"{signal['sweep']} WAT"
            )

            print(
                "   ✅ Sweep confirmed"
            )

            print(
                "   ✅ Close crossed "
                "reference open"
            )

            print(
                "   👉 LOOK FOR ENTRY"
            )

    print("")
    print("==============================================")
    print("📊 SCAN COMPLETE")
    print("==============================================")
    print(
        f"Total valid setups found: "
        f"{total_signals}"
    )

    if total_signals == 0:

        print(
            "ℹ️ No valid setups found "
            "in the available historical data."
        )

    print("")
    print("🤖 Scanner finished successfully.")

    ws.close()


except Exception as e:

    print("")
    print("❌ SCANNER ERROR")
    print(str(e))
