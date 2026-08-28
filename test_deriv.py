import json
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES - SINGLE MARKET 4H CANDLE DIAGNOSTIC TEST
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

WAT = timezone(timedelta(hours=1))

# Test ONE market first
SYMBOL = "1HZ10V"


print("")
print("=" * 60)
print("🤖 SIXSGAMES 4H CANDLE DIAGNOSTIC TEST")
print("=" * 60)

print(f"📊 Market: {SYMBOL}")
print("⏱️ Timeframe: 4H")
print("🌍 Timezone: Africa/Lagos")
print("")


# ============================================================
# CONNECT
# ============================================================

try:

    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        DERIV_URL,
        timeout=20
    )

    print("✅ Connected successfully!")

except Exception as e:

    print("❌ Connection failed:")
    print(str(e))
    raise SystemExit


# ============================================================
# REQUEST 4H CANDLES
# ============================================================

print("")
print("📡 Requesting 4H candles...")


request = {
    "ticks_history": SYMBOL,
    "adjust_start_time": 1,
    "count": 20,
    "end": "latest",
    "granularity": 14400,
    "style": "candles",
    "req_id": 1
}


try:

    ws.send(json.dumps(request))

    response = ws.recv()

    data = json.loads(response)

except Exception as e:

    print("❌ Failed receiving candle data:")
    print(str(e))

    ws.close()
    raise SystemExit


# ============================================================
# CHECK DERIV RESPONSE
# ============================================================

print("")
print("📥 Deriv response received.")


if data.get("error"):

    print("")
    print("❌ DERIV RETURNED AN ERROR")
    print("-" * 60)
    print(json.dumps(data["error"], indent=2))
    print("-" * 60)

    ws.close()
    raise SystemExit


# ============================================================
# GET CANDLES
# ============================================================

candles = data.get("candles", [])


print("")
print(f"📊 Candles returned: {len(candles)}")


if not candles:

    print("")
    print("❌ NO CANDLES WERE RETURNED.")
    print("")
    print("Full response:")
    print(json.dumps(data, indent=2))

    ws.close()
    raise SystemExit


# ============================================================
# PRINT CANDLES
# ============================================================

print("")
print("=" * 60)
print("🕯️ 4H CANDLES — AFRICA/LAGOS TIME")
print("=" * 60)


converted = []


for candle in candles:

    try:

        epoch = int(candle["epoch"])

        dt = datetime.fromtimestamp(
            epoch,
            timezone.utc
        ).astimezone(WAT)

        item = {
            "time": dt,
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"])
        }

        converted.append(item)

        print("")
        print(
            f"🕐 {dt.strftime('%Y-%m-%d %H:%M')} WAT"
        )

        print(
            f"   Open : {item['open']}"
        )

        print(
            f"   High : {item['high']}"
        )

        print(
            f"   Low  : {item['low']}"
        )

        print(
            f"   Close: {item['close']}"
        )

    except Exception as e:

        print(
            f"⚠️ Could not convert candle: {e}"
        )


# ============================================================
# FIND TODAY'S IMPORTANT CANDLES
# ============================================================

now = datetime.now(WAT)

today = now.date()


print("")
print("=" * 60)
print("🎯 IMPORTANT CANDLES")
print("=" * 60)

print(
    f"Today according to scanner: "
    f"{today}"
)


def find_candle(hour):

    for candle in converted:

        if (
            candle["time"].date() == today
            and candle["time"].hour == hour
        ):

            return candle

    return None


candle_02 = find_candle(2)
candle_06 = find_candle(6)
candle_10 = find_candle(10)
candle_14 = find_candle(14)


print("")


if candle_02:

    print("✅ 02:00 candle FOUND")

else:

    print("❌ 02:00 candle NOT FOUND")


if candle_06:

    print("✅ 06:00 candle FOUND")

else:

    print("❌ 06:00 candle NOT FOUND")


if candle_10:

    print("✅ 10:00 candle FOUND")

else:

    print("❌ 10:00 candle NOT FOUND")


if candle_14:

    print("✅ 14:00 candle FOUND")

else:

    print("❌ 14:00 candle NOT FOUND")


# ============================================================
# TEST 02 → 06
# ============================================================

print("")
print("=" * 60)
print("🧪 TESTING 02:00 → 06:00")
print("=" * 60)


if candle_02 and candle_06:

    print("")
    print("02:00 candle:")
    print(
        f"Open = {candle_02['open']}"
    )
    print(
        f"High = {candle_02['high']}"
    )
    print(
        f"Low = {candle_02['low']}"
    )
    print(
        f"Close = {candle_02['close']}"
    )


    print("")
    print("06:00 candle:")
    print(
        f"Open = {candle_06['open']}"
    )
    print(
        f"High = {candle_06['high']}"
    )
    print(
        f"Low = {candle_06['low']}"
    )
    print(
        f"Close = {candle_06['close']}"
    )


    # BUY CONDITIONS

    buy_sweep = (
        candle_06["low"]
        <
        candle_02["low"]
    )

    buy_close = (
        candle_06["close"]
        >
        candle_02["open"]
    )


    print("")
    print("🟢 BUY CONDITIONS")

    print(
        "06 Low < 02 Low : "
        f"{'✅' if buy_sweep else '❌'}"
    )

    print(
        "06 Close > 02 Open : "
        f"{'✅' if buy_close else '❌'}"
    )


    if buy_sweep and buy_close:

        print("")
        print(
            "🚨 BUY SETUP CONFIRMED!"
        )

        print(
            "🎯 LOOK FOR ENTRY AT 10:00 WAT"
        )

    else:

        print("")
        print(
            "⚪ No BUY setup."
        )


    # SELL CONDITIONS

    sell_sweep = (
        candle_06["high"]
        >
        candle_02["high"]
    )

    sell_close = (
        candle_06["close"]
        <
        candle_02["open"]
    )


    print("")
    print("🔴 SELL CONDITIONS")

    print(
        "06 High > 02 High : "
        f"{'✅' if sell_sweep else '❌'}"
    )

    print(
        "06 Close < 02 Open : "
        f"{'✅' if sell_close else '❌'}"
    )


    if sell_sweep and sell_close:

        print("")
        print(
            "🚨 SELL SETUP CONFIRMED!"
        )

        print(
            "🎯 LOOK FOR ENTRY AT 10:00 WAT"
        )

    else:

        print("")
        print(
            "⚪ No SELL setup."
        )


else:

    print("")
    print(
        "⚠️ Cannot test 02 → 06 because "
        "one or both candles are unavailable."
    )


# ============================================================
# CLOSE
# ============================================================

ws.close()


print("")
print("=" * 60)
print("✅ DIAGNOSTIC TEST FINISHED")
print("=" * 60)
print("")
