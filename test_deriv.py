import json
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES - 4H TIME-BASED STRATEGY SCANNER
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

# Symbols that your previous successful discovery found
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
# CONNECT
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
# SEND REQUEST
# ============================================================

def request(ws, payload):

    ws.send(json.dumps(payload))

    while True:

        message = ws.recv()

        if not message:
            continue

        data = json.loads(message)

        if "error" in data:
            return data

        return data


# ============================================================
# GET CANDLES
# ============================================================

def get_candles(ws, symbol):

    payload = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": 100,
        "end": "latest",
        "granularity": 14400,
        "style": "candles"
    }

    response = request(ws, payload)

    if response.get("error"):

        return None, response["error"]

    candles = response.get("candles", [])

    if not candles:

        return None, {
            "message": "No candles returned"
        }

    return candles, None


# ============================================================
# CONVERT CANDLE TO WAT
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
# BULLISH SETUP
# ============================================================

def bullish_setup(reference, confirmation):

    # Reference candle MUST be bullish
    if reference["close"] <= reference["open"]:
        return False

    # Confirmation MUST sweep reference low
    if confirmation["low"] >= reference["low"]:
        return False

    # Confirmation MUST close strictly above reference open
    if confirmation["close"] <= reference["open"]:
        return False

    return True


# ============================================================
# BEARISH SETUP
# ============================================================

def bearish_setup(reference, confirmation):

    # Reference candle MUST be bearish
    if reference["close"] >= reference["open"]:
        return False

    # Confirmation MUST sweep reference high
    if confirmation["high"] <= reference["high"]:
        return False

    # Confirmation MUST close strictly below reference open
    if confirmation["close"] >= reference["open"]:
        return False

    return True


# ============================================================
# CHECK ONE DAY
# ============================================================

def scan_day(candles, date_value):

    signals = []

    # --------------------------------------------------------
    # SETUP 1
    # 02:00 -> 06:00 -> ENTRY 10:00
    # --------------------------------------------------------

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

        if bullish_setup(
            candle_02,
            candle_06
        ):

            signals.append({
                "date": date_value,
                "entry": "10:00",
                "direction": "BUY",
                "reference": "02:00",
                "confirmation": "06:00",
                "ref": candle_02,
                "conf": candle_06
            })

        elif bearish_setup(
            candle_02,
            candle_06
        ):

            signals.append({
                "date": date_value,
                "entry": "10:00",
                "direction": "SELL",
                "reference": "02:00",
                "confirmation": "06:00",
                "ref": candle_02,
                "conf": candle_06
            })


    # --------------------------------------------------------
    # SETUP 2
    # 06:00 -> 10:00 -> ENTRY 14:00
    # --------------------------------------------------------

    candle_10 = find_candle(
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
                "date": date_value,
                "entry": "14:00",
                "direction": "BUY",
                "reference": "06:00",
                "confirmation": "10:00",
                "ref": candle_06,
                "conf": candle_10
            })

        elif bearish_setup(
            candle_06,
            candle_10
        ):

            signals.append({
                "date": date_value,
                "entry": "14:00",
                "direction": "SELL",
                "reference": "06:00",
                "confirmation": "10:00",
                "ref": candle_06,
                "conf": candle_10
            })

    return signals


# ============================================================
# SCAN MARKET
# ============================================================

def scan_market(ws, symbol):

    candles, error = get_candles(
        ws,
        symbol
    )

    if error:

        return [], error

    converted = []

    for candle in candles:

        try:

            converted.append(
                convert_candle(candle)
            )

        except Exception:
            pass


    # Only use completed candles
    now = datetime.now(WAT)

    completed = []

    for candle in converted:

        candle_end = (
            candle["time"] +
            timedelta(hours=4)
        )

        if candle_end <= now:

            completed.append(candle)


    if len(completed) < 3:

        return [], {
            "message": "Not enough completed candles"
        }


    dates = sorted(
        set(
            candle["time"].date()
            for candle in completed
        )
    )


    signals = []

    for date_value in dates:

        daily = scan_day(
            completed,
            date_value
        )

        for signal in daily:

            signal["symbol"] = symbol

            signals.append(signal)


    return signals, None


# ============================================================
# PRINT SIGNAL
# ============================================================

def print_signal(signal):

    ref = signal["ref"]
    conf = signal["conf"]

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
        f"🎯 Direction: {signal['direction']}"
    )

    print(
        f"⏰ ENTRY TIME: {signal['entry']} WAT"
    )

    print("")

    print(
        f"Reference {signal['reference']}: "
        f"O={ref['open']} "
        f"H={ref['high']} "
        f"L={ref['low']} "
        f"C={ref['close']}"
    )

    print(
        f"Confirmation {signal['confirmation']}: "
        f"O={conf['open']} "
        f"H={conf['high']} "
        f"L={conf['low']} "
        f"C={conf['close']}"
    )

    print("")
    print("✅ All strategy conditions passed.")
    print("👀 LOOK FOR YOUR ENTRY.")
    print("")


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("🤖 SIXSGAMES 4H TIME-BASED STRATEGY SCANNER")
    print("=" * 60)

    ws = None

    try:

        ws = connect()

        print("")
        print("=" * 60)
        print("📊 TESTING AVAILABLE MARKETS")
        print("=" * 60)

        available = []

        # First test each requested market
        for symbol in MARKETS:

            candles, error = get_candles(
                ws,
                symbol
            )

            if candles:

                print(
                    f"🟢 {symbol} → candles available"
                )

                available.append(symbol)

            else:

                print(
                    f"🔴 {symbol} → unavailable"
                )


        print("")
        print("=" * 60)
        print("📊 MARKET TEST COMPLETE")
        print("=" * 60)

        print(
            f"Markets requested: {len(MARKETS)}"
        )

        print(
            f"Markets working: {len(available)}"
        )


        if not available:

            print("")
            print("❌ No markets returned candles.")
            return


        print("")
        print("=" * 60)
        print("🔎 STARTING STRATEGY SCAN")
        print("=" * 60)


        total_signals = 0

        for symbol in available:

            print("")
            print(
                f"🔍 Scanning {symbol}..."
            )

            signals, error = scan_market(
                ws,
                symbol
            )

            if error:

                print(
                    f"⚠️ Scan error: {error}"
                )

                continue


            if signals:

                print(
                    f"🚨 {len(signals)} setup(s) found!"
                )

                for signal in signals:

                    total_signals += 1

                    print_signal(signal)

            else:

                print(
                    "⚪ No valid setup found."
                )


        print("")
        print("=" * 60)
        print("📊 FINAL SCAN SUMMARY")
        print("=" * 60)

        print(
            f"Markets working: {len(available)}"
        )

        print(
            f"Total historical setups: {total_signals}"
        )

        print("")
        print(
            "🤖 Scanner finished successfully."
        )


    except Exception as e:

        print("")
        print("=" * 60)
        print("❌ ERROR")
        print("=" * 60)

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
