import json
import websocket
from datetime import datetime, timezone, timedelta

# ============================================================
# SIXSGAMES
# 4H TIME-BASED STRATEGY
# CANDLE ALIGNMENT TEST
# ============================================================

DERIV_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

# Africa/Lagos = UTC+1
WAT = timezone(timedelta(hours=1))

# Test ONE market first
SYMBOL = "1HZ10V"

# 1 hour data is used so we can build our own
# 4-hour candles starting exactly at:
#
# 02:00 WAT
# 06:00 WAT
# 10:00 WAT
# 14:00 WAT
# 18:00 WAT
# 22:00 WAT
#
GRANULARITY = 3600


# ============================================================
# HEADER
# ============================================================

print("")
print("=" * 70)
print("🤖 SIXSGAMES 4H STRATEGY CANDLE ALIGNMENT TEST")
print("=" * 70)

print(f"📊 Market: {SYMBOL}")
print("⏱️ Source data: 1H candles")
print("🕯️ Strategy candles: 4H")
print("🌍 Timezone: Africa/Lagos")
print("🎯 Strategy times: 02:00 / 06:00 / 10:00 / 14:00")
print("")


# ============================================================
# CONNECT TO DERIV
# ============================================================

try:

    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        DERIV_URL,
        timeout=20
    )

    print("✅ Connected successfully!")

except Exception as e:

    print("")
    print("❌ CONNECTION FAILED")
    print(str(e))
    raise SystemExit


# ============================================================
# REQUEST FUNCTION
# ============================================================

def send_request(payload):

    try:

        ws.send(
            json.dumps(payload)
        )

        while True:

            raw = ws.recv()

            if not raw:
                continue

            data = json.loads(raw)

            if data.get("error"):

                return None, data["error"]

            return data, None

    except Exception as e:

        return None, {
            "message": str(e)
        }


# ============================================================
# GET 1H CANDLES
# ============================================================

print("")
print("=" * 70)
print("📡 REQUESTING 1H CANDLES")
print("=" * 70)


request = {
    "ticks_history": SYMBOL,
    "adjust_start_time": 1,
    "count": 120,
    "end": "latest",
    "granularity": GRANULARITY,
    "style": "candles",
    "req_id": 1
}


data, error = send_request(request)


if error:

    print("")
    print("❌ DERIV ERROR")
    print("-" * 70)
    print(json.dumps(error, indent=2))
    print("-" * 70)

    ws.close()
    raise SystemExit


raw_candles = data.get(
    "candles",
    []
)


print("")
print(
    f"✅ 1H candles received: "
    f"{len(raw_candles)}"
)


if not raw_candles:

    print("")
    print("❌ No candle data returned.")

    print("")
    print("Full response:")
    print(
        json.dumps(
            data,
            indent=2
        )
    )

    ws.close()
    raise SystemExit


# ============================================================
# CONVERT 1H CANDLES TO WAT
# ============================================================

hourly = []


for candle in raw_candles:

    try:

        epoch = int(
            candle["epoch"]
        )

        dt = datetime.fromtimestamp(
            epoch,
            timezone.utc
        ).astimezone(WAT)

        hourly.append(
            {
                "time": dt,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"])
            }
        )

    except Exception:
        continue


hourly.sort(
    key=lambda x: x["time"]
)


print("")
print(
    f"✅ Converted hourly candles: "
    f"{len(hourly)}"
)


# ============================================================
# BUILD CUSTOM 4H CANDLES
# ============================================================
#
# We want candles beginning at:
#
# 02:00
# 06:00
# 10:00
# 14:00
# 18:00
# 22:00
#
# Each candle contains FOUR 1H candles.
#
# Example:
#
# 02:00 candle =
# 02, 03, 04, 05
#
# 06:00 candle =
# 06, 07, 08, 09
#
# 10:00 candle =
# 10, 11, 12, 13
#
# 14:00 candle =
# 14, 15, 16, 17
#
# ============================================================

strategy_candles = []


for i in range(
    len(hourly)
):

    first = hourly[i]

    hour = first["time"].hour

    # Only our strategy starting times
    if hour not in (
        2,
        6,
        10,
        14,
        18,
        22
    ):
        continue

    # Make sure this candle is exactly on the hour
    if first["time"].minute != 0:
        continue

    expected = []

    for offset in range(4):

        target_time = (
            first["time"]
            +
            timedelta(hours=offset)
        )

        found = None

        for candidate in hourly:

            if candidate["time"] == target_time:

                found = candidate
                break

        if found is not None:

            expected.append(found)

    # Need all four 1H candles
    if len(expected) != 4:
        continue

    # Build 4H candle
    custom = {

        "time": first["time"],

        "open": expected[0]["open"],

        "high": max(
            x["high"]
            for x in expected
        ),

        "low": min(
            x["low"]
            for x in expected
        ),

        "close": expected[-1]["close"]
    }

    strategy_candles.append(
        custom
    )


# Remove duplicates
unique = {}

for candle in strategy_candles:

    key = candle["time"]

    unique[key] = candle


strategy_candles = list(
    unique.values()
)

strategy_candles.sort(
    key=lambda x: x["time"]
)


# ============================================================
# PRINT CUSTOM 4H CANDLES
# ============================================================

print("")
print("=" * 70)
print("🕯️ CUSTOM SIXSGAMES 4H CANDLES")
print("=" * 70)


for candle in strategy_candles[-20:]:

    print("")
    print(
        f"🕐 {candle['time'].strftime('%Y-%m-%d %H:%M')} WAT"
    )

    print(
        f"   Open : {candle['open']}"
    )

    print(
        f"   High : {candle['high']}"
    )

    print(
        f"   Low  : {candle['low']}"
    )

    print(
        f"   Close: {candle['close']}"
    )


# ============================================================
# GET COMPLETED CANDLES
# ============================================================

now = datetime.now(WAT)

completed = []


for candle in strategy_candles:

    candle_end = (
        candle["time"]
        +
        timedelta(hours=4)
    )

    if candle_end <= now:

        completed.append(
            candle
        )


print("")
print("=" * 70)
print("📊 COMPLETED STRATEGY CANDLES")
print("=" * 70)

print(
    f"Current WAT time: "
    f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
)

print(
    f"Completed 4H candles: "
    f"{len(completed)}"
)


# ============================================================
# FIND CANDLE
# ============================================================

def find_candle(
    date_value,
    hour
):

    for candle in completed:

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
# TEST RECENT DAYS
# ============================================================

dates = sorted(
    set(
        candle["time"].date()
        for candle in completed
    )
)


print("")
print("=" * 70)
print("🎯 TESTING 02 → 06 → 10 → 14")
print("=" * 70)


total_buy = 0
total_sell = 0


for date_value in dates[-7:]:

    candle_02 = find_candle(
        date_value,
        2
    )

    candle_06 = find_candle(
        date_value,
        6
    )

    candle_10 = find_candle(
        date_value,
        10
    )

    candle_14 = find_candle(
        date_value,
        14
    )


    print("")
    print(
        f"📅 DATE: {date_value}"
    )

    print(
        f"   02:00 = "
        f"{'✅' if candle_02 else '❌'}"
    )

    print(
        f"   06:00 = "
        f"{'✅' if candle_06 else '❌'}"
    )

    print(
        f"   10:00 = "
        f"{'✅' if candle_10 else '❌'}"
    )

    print(
        f"   14:00 = "
        f"{'✅' if candle_14 else '❌'}"
    )


    # ========================================================
    # 02 → 06 → 10
    # ========================================================

    if candle_02 and candle_06:

        print("")
        print("   🧪 02:00 → 06:00")


        # BUY
        #
        # 06 low must sweep entire
        # 02 candle low.
        #
        # 06 close must be STRICTLY
        # above 02 open.
        #

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


        # SELL
        #
        # 06 high must sweep entire
        # 02 candle high.
        #
        # 06 close must be STRICTLY
        # below 02 open.
        #

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


        print(
            f"      BUY sweep: "
            f"{'✅' if buy_sweep else '❌'}"
        )

        print(
            f"      BUY close > 02 open: "
            f"{'✅' if buy_close else '❌'}"
        )

        print(
            f"      SELL sweep: "
            f"{'✅' if sell_sweep else '❌'}"
        )

        print(
            f"      SELL close < 02 open: "
            f"{'✅' if sell_close else '❌'}"
        )


        if buy_sweep and buy_close:

            print("")
            print(
                "      🚨 BUY SETUP!"
            )

            print(
                "      🎯 LOOK FOR ENTRY AT 10:00 WAT"
            )

            total_buy += 1


        elif sell_sweep and sell_close:

            print("")
            print(
                "      🚨 SELL SETUP!"
            )

            print(
                "      🎯 LOOK FOR ENTRY AT 10:00 WAT"
            )

            total_sell += 1

        else:

            print(
                "      ⚪ No valid 10:00 setup."
            )


    # ========================================================
    # 06 → 10 → 14
    # ========================================================

    if candle_06 and candle_10:

        print("")
        print("   🧪 06:00 → 10:00")


        buy_sweep = (
            candle_10["low"]
            <
            candle_06["low"]
        )

        buy_close = (
            candle_10["close"]
            >
            candle_06["open"]
        )


        sell_sweep = (
            candle_10["high"]
            >
            candle_06["high"]
        )

        sell_close = (
            candle_10["close"]
            <
            candle_06["open"]
        )


        print(
            f"      BUY sweep: "
            f"{'✅' if buy_sweep else '❌'}"
        )

        print(
            f"      BUY close > 06 open: "
            f"{'✅' if buy_close else '❌'}"
        )

        print(
            f"      SELL sweep: "
            f"{'✅' if sell_sweep else '❌'}"
        )

        print(
            f"      SELL close < 06 open: "
            f"{'✅' if sell_close else '❌'}"
        )


        if buy_sweep and buy_close:

            print("")
            print(
                "      🚨 BUY SETUP!"
            )

            print(
                "      🎯 LOOK FOR ENTRY AT 14:00 WAT"
            )

            total_buy += 1


        elif sell_sweep and sell_close:

            print("")
            print(
                "      🚨 SELL SETUP!"
            )

            print(
                "      🎯 LOOK FOR ENTRY AT 14:00 WAT"
            )

            total_sell += 1

        else:

            print(
                "      ⚪ No valid 14:00 setup."
            )


# ============================================================
# FINAL SUMMARY
# ============================================================

print("")
print("=" * 70)
print("📊 FINAL DIAGNOSTIC SUMMARY")
print("=" * 70)

print(
    f"📊 Market tested: {SYMBOL}"
)

print(
    f"🕯️ Custom 4H candles: "
    f"{len(strategy_candles)}"
)

print(
    f"🟢 BUY setups found: "
    f"{total_buy}"
)

print(
    f"🔴 SELL setups found: "
    f"{total_sell}"
)


print("")
print("=" * 70)
print("✅ CANDLE ALIGNMENT TEST FINISHED")
print("=" * 70)

print("")
print(
    "Next step: use this verified candle structure "
    "for the 42-market live Telegram scanner."
)


# ============================================================
# CLOSE CONNECTION
# ============================================================

try:

    ws.close()

except Exception:

    pass
