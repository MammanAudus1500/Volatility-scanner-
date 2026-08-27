import json
import websocket
from datetime import datetime, timezone, timedelta

print("==============================================")
print("🤖 4H CANDLE SCANNER TEST")
print("==============================================")

URL = "wss://api.derivws.com/trading/v1/options/ws/public"

# We will test these first.
# Once candle retrieval works, we'll load the complete 46-market list.
TEST_MARKETS = [
    "R_10",
    "R_25",
    "R_50",
    "R_75",
    "R_100",
]


def nigeria_time(unix_time):
    """Convert Deriv Unix time to Nigeria time (WAT = UTC+1)."""
    utc_time = datetime.fromtimestamp(
        unix_time,
        timezone.utc
    )

    wat = utc_time + timedelta(hours=1)

    return wat.strftime("%Y-%m-%d %H:%M:%S")


try:

    print("")
    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        URL,
        timeout=20
    )

    print("✅ Connected!")

    for symbol in TEST_MARKETS:

        print("")
        print("----------------------------------------------")
        print(f"📊 REQUESTING 4H CANDLES: {symbol}")
        print("----------------------------------------------")

        request = {
            "ticks_history": symbol,
            "style": "candles",
            "granularity": 14400,
            "count": 10,
            "end": "latest",
            "req_id": 100
        }

        ws.send(json.dumps(request))

        while True:

            response = json.loads(ws.recv())

            if response.get("error"):

                print("❌ Deriv error:")
                print(response["error"])
                break

            if response.get("msg_type") == "candles":

                candles = response.get("candles", [])

                print(
                    f"✅ Received {len(candles)} "
                    f"completed/available 4H candles"
                )

                if candles:

                    print("")
                    print("LATEST CANDLES")
                    print("----------------------------------------------")

                    for candle in candles[-5:]:

                        candle_time = nigeria_time(
                            candle["epoch"]
                        )

                        print(
                            f"{candle_time} WAT | "
                            f"O={candle['open']} | "
                            f"H={candle['high']} | "
                            f"L={candle['low']} | "
                            f"C={candle['close']}"
                        )

                break

        # Small separator before next market
        print("")

    ws.close()

    print("==============================================")
    print("✅ 4H CANDLE TEST FINISHED")
    print("==============================================")


except Exception as e:

    print("")
    print("❌ SCANNER ERROR")
    print(str(e))
