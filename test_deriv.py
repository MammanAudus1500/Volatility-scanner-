import json
import websocket

print("================================")
print("🤖 DERIV CONNECTION TEST")
print("================================")

URL = "wss://api.derivws.com/trading/v1/options/ws/public"

try:
    print("Connecting to Deriv...")

    ws = websocket.create_connection(
        URL,
        timeout=15
    )

    print("✅ Connected successfully!")

    request = {
        "active_symbols": "brief",
        "req_id": 1
    }

    print("📡 Asking Deriv for active markets...")

    ws.send(json.dumps(request))

    while True:
        response = json.loads(ws.recv())

        if response.get("error"):
            print("❌ Deriv returned an error:")
            print(response["error"])
            break

        if response.get("msg_type") == "active_symbols":

            symbols = response.get("active_symbols", [])

            print("")
            print("📊 ACTIVE MARKETS")
            print("----------------------------")

            volatility_count = 0

            for symbol in symbols:

                name = symbol.get("display_name", "")
                code = symbol.get("symbol", "")

                if "Volatility" in name:
                    print(f"🟢 {name} → {code}")
                    volatility_count += 1

            print("----------------------------")
            print(f"✅ Volatility markets found: {volatility_count}")

            break

    ws.close()

    print("")
    print("🤖 Test finished successfully!")

except Exception as e:

    print("")
    print("❌ CONNECTION FAILED")
    print(str(e))
