import json
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES - 4H TIME-BASED STRATEGY SCANNER
# ============================================================
#
# STRATEGY
#
# SETUP 1:
# 02:00 candle = reference candle
# 06:00 candle = confirmation candle
# 10:00 candle = ENTRY TIME
#
# BULLISH:
# - 02:00 candle must be bullish
# - 06:00 candle must sweep the LOW of the 02:00 candle
# - 06:00 candle must CLOSE ABOVE the 02:00 OPEN
# - Close exactly at the 02:00 open = NO SIGNAL
#
# BEARISH:
# - 02:00 candle must be bearish
# - 06:00 candle must sweep the HIGH of the 02:00 candle
# - 06:00 candle must CLOSE BELOW the 02:00 OPEN
# - Close exactly at the 02:00 open = NO SIGNAL
#
# SETUP 2:
# 06:00 candle = reference candle
# 10:00 candle = confirmation candle
# 14:00 candle = ENTRY TIME
#
# Same bullish/bearish rules, reversed in time.
# ============================================================

DERIV_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# Nigeria / West Africa Time = UTC + 1
WAT = timezone(timedelta(hours=1))

# Requested markets.
# The scanner will only use symbols that Deriv actually returns.
REQUESTED_MARKETS = [
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
    "frxNZDCHF",
    "frxCADCHF",
    "frxEURCHF",
    "frxCHFJPY",
    "frxGBPCHF",
    "frxNZDCAD",
    "frxGBPNZD",
    "frxCADJPY",
    "frxAUDCHF",
    "frxGBPAUD",
    "frxUSDCHF",
    "frxXAUUSD",

    "cryBTCUSD",

    "OTC_S100"
]


# ------------------------------------------------------------
# CONNECTION
# ------------------------------------------------------------

def connect():
    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        DERIV_URL,
        timeout=20
    )

    print("✅ Connected successfully!")

    return ws


# ------------------------------------------------------------
# SEND REQUEST / RECEIVE RESPONSE
# ------------------------------------------------------------

def send_request(ws, request):
    ws.send(json.dumps(request))

    while True:
        raw = ws.recv()

        if not raw:
            continue

        response = json.loads(raw)

        if response.get("error"):
            return response

        if (
            response.get("msg_type")
            or "candles" in response
            or "history" in response
            or "active_symbols" in response
        ):
            return response


# ------------------------------------------------------------
# GET ACTIVE SYMBOLS FROM DERIV
# ------------------------------------------------------------

def discover_markets(ws):

    print("")
    print("=" * 60)
    print("🔎 DISCOVERING DERIV MARKETS")
    print("=" * 60)

    request = {
        "active_symbols": "brief",
        "product_type": "basic",
        "req_id": 100
    }

    response = send_request(ws, request)

    if response.get("error"):
        print("❌ Market discovery error:")
        print(response["error"])
        return {}

    active_symbols = response.get("active_symbols", [])

    available = {}

    for item in active_symbols:
        symbol = item.get("symbol")

        if symbol:
            available[symbol] = item

    print(f"📊 Deriv returned {len(available)} active symbols.")

    # Match requested markets with actual Deriv symbols
    found = {}

    for requested in REQUESTED_MARKETS:

        if requested in available:
            found[requested] = available[requested]

    print(f"✅ Requested markets available: {len(found)}")

    if found:
        print("")
        print("MARKETS TO SCAN")
        print("-" * 60)

        for symbol, info in found.items():
            display = info.get("display_name", symbol)
            print(f"🟢 {display} → {symbol}")

    missing = [
        symbol for symbol in REQUESTED_MARKETS
        if symbol not in found
    ]

    if missing:
        print("")
        print("⚠️ NOT AVAILABLE ON THIS DERIV ACCOUNT/API")
        print("-" * 60)

        for symbol in missing:
            print(f"🔴 {symbol}")

    return found


# ------------------------------------------------------------
# GET 4H CANDLES
# ------------------------------------------------------------

def get_candles(ws, symbol, count=80):

    request = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest",
        "granularity": 14400,
        "style": "candles",
        "req_id": 200
    }

    response = send_request(ws, request)

    if response.get("error"):
        return None, response["error"]

    candles = response.get("candles", [])

    if not candles:
        return None, {
            "message": "No candles returned"
        }

    return candles, None


# ------------------------------------------------------------
# CONVERT DERIV CANDLE
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# FIND CANDLE BY WAT HOUR
# ------------------------------------------------------------

def find_candle(candles, date_value, hour):

    for candle in candles:

        if (
            candle["time"].date() == date_value
            and candle["time"].hour == hour
        ):
            return candle

    return None


# ------------------------------------------------------------
# CHECK BULLISH SETUP
# ------------------------------------------------------------

def bullish_setup(reference, confirmation):

    # Reference candle must be bullish
    if reference["close"] <= reference["open"]:
        return False

    # Confirmation candle must sweep reference LOW
    if confirmation["low"] >= reference["low"]:
        return False

    # Confirmation must close STRICTLY above reference OPEN
    if confirmation["close"] <= reference["open"]:
        return False

    return True


# ------------------------------------------------------------
# CHECK BEARISH SETUP
# ------------------------------------------------------------

def bearish_setup(reference, confirmation):

    # Reference candle must be bearish
    if reference["close"] >= reference["open"]:
        return False

    # Confirmation candle must sweep reference HIGH
    if confirmation["high"] <= reference["high"]:
        return False

    # Confirmation must close STRICTLY below reference OPEN
    if confirmation["close"] >= reference["open"]:
        return False

    return True


# ------------------------------------------------------------
# SCAN ONE DAY
# ------------------------------------------------------------

def scan_day(candles, date_value):

    signals = []

    # ========================================================
    # SETUP 1
    # 02:00 -> 06:00 -> ENTRY 10:00
    # ========================================================

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

        # Bullish
        if bullish_setup(candle_02, candle_06):

            signals.append({
                "date": date_value,
                "entry_time": "10:00",
                "direction": "BUY",
                "reference": "02:00",
                "confirmation": "06:00",
                "reference_candle": candle_02,
                "confirmation_candle": candle_06
            })

        # Bearish
        elif bearish_setup(candle_02, candle_06):

            signals.append({
                "date": date_value,
                "entry_time": "10:00",
                "direction": "SELL",
                "reference": "02:00",
                "confirmation": "06:00",
                "reference_candle": candle_02,
                "confirmation_candle": candle_06
            })

    # ========================================================
    # SETUP 2
    # 06:00 -> 10:00 -> ENTRY 14:00
    # ========================================================

    candle_10 = find_candle(
        candles,
        date_value,
        10
    )

    if candle_06 and candle_10:

        # Bullish
        if bullish_setup(candle_06, candle_10):

            signals.append({
                "date": date_value,
                "entry_time": "14:00",
                "direction": "BUY",
                "reference": "06:00",
                "confirmation": "10:00",
                "reference_candle": candle_06,
                "confirmation_candle": candle_10
            })

        # Bearish
        elif bearish_setup(candle_06, candle_10):

            signals.append({
                "date": date_value,
                "entry_time": "14:00",
                "direction": "SELL",
                "reference": "06:00",
                "confirmation": "10:00",
                "reference_candle": candle_06,
                "confirmation_candle": candle_10
            })

    return signals


# ------------------------------------------------------------
# SCAN MARKET
# ------------------------------------------------------------

def scan_market(ws, symbol):

    candles, error = get_candles(ws, symbol)

    if error:

        return [], error

    converted = []

    for candle in candles:

        try:
            converted.append(
                convert_candle(candle)
            )
        except Exception:
            continue

    if len(converted) < 5:

        return [], {
            "message": "Not enough candles"
        }

    # Remove incomplete current candle.
    # A 4H candle is considered complete only when
    # another candle has already started.
    now = datetime.now(WAT)

    completed = []

    for candle in converted:

        candle_end = candle["time"] + timedelta(hours=4)

        if candle_end <= now:
            completed.append(candle)

    if len(completed) < 3:

        return [], {
            "message": "Not enough completed candles"
        }

    # Get unique dates
    dates = sorted(
        set(
            candle["time"].date()
            for candle in completed
        )
    )

    all_signals = []

    for date_value in dates:

        daily_signals = scan_day(
            completed,
            date_value
        )

        for signal in daily_signals:

            signal["symbol"] = symbol

            all_signals.append(signal)

    return all_signals, None


# ------------------------------------------------------------
# PRINT SIGNAL
# ------------------------------------------------------------

def print_signal(signal):

    ref = signal["reference_candle"]
    conf = signal["confirmation_candle"]

    print("")
    print("🚨" * 25)
    print("🔥 VALID SETUP FOUND!")
    print("🚨" * 25)

    print(f"📊 Market: {signal['symbol']}")
    print(f"📅 Date: {signal['date']}")
    print(f"🎯 Direction: {signal['direction']}")
    print(f"⏰ ENTRY: {signal['entry_time']} WAT")

    print("")
    print(
        f"Reference candle {signal['reference']}: "
        f"O={ref['open']} "
        f"H={ref['high']} "
        f"L={ref['low']} "
        f"C={ref['close']}"
    )

    print(
        f"Confirmation candle {signal['confirmation']}: "
        f"O={conf['open']} "
        f"H={conf['high']} "
        f"L={conf['low']} "
        f"C={conf['close']}"
    )

    print("")
    print("✅ Conditions satisfied.")
    print("👀 Look for your entry at the indicated entry time.")
    print("🚨" * 25)
    print("")


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    print("")
    print("=" * 60)
    print("🤖 SIXSGAMES TIME-BASED 4H STRATEGY SCANNER")
    print("=" * 60)

    ws = None

    try:

        ws = connect()

        markets = discover_markets(ws)

        if not markets:

            print("")
            print("❌ No requested markets are available.")
            return

        print("")
        print("=" * 60)
        print("🔎 STARTING STRATEGY SCAN")
        print("=" * 60)

        total_markets = 0
        successful_markets = 0
        total_signals = 0

        for symbol in markets:

            total_markets += 1

            display_name = markets[symbol].get(
                "display_name",
                symbol
            )

            print("")
            print(f"🔍 Scanning {display_name} ({symbol})...")

            signals, error = scan_market(
                ws,
                symbol
            )

            if error:

                print(
                    f"⚠️ Could not scan {symbol}: "
                    f"{error}"
                )

                continue

            successful_markets += 1

            if signals:

                print(
                    f"🚨 {len(signals)} valid setup(s) found!"
                )

                for signal in signals:

                    total_signals += 1

                    print_signal(signal)

            else:

                print("⚪ No valid setup found.")

        print("")
        print("=" * 60)
        print("📊 SCAN SUMMARY")
        print("=" * 60)

        print(
            f"Markets requested: {len(REQUESTED_MARKETS)}"
        )

        print(
            f"Markets available: {len(markets)}"
        )

        print(
            f"Markets scanned successfully: "
            f"{successful_markets}"
        )

        print(
            f"🔥 Total historical valid setups: "
            f"{total_signals}"
        )

        print("")
        print("🤖 Scanner finished successfully.")

    except Exception as e:

        print("")
        print("=" * 60)
        print("❌ SCANNER ERROR")
        print("=" * 60)

        print(str(e))

    finally:

        if ws:

            try:
                ws.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
