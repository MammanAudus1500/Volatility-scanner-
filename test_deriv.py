import json
import websocket

print("================================")
print("🤖 DERIV VOLATILITY MARKET TEST")
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
            print("📊 VOLATILITY MARKETS")
            print("----------------------------")

            volatility_count = 0

            for market in symbols:

                # New Deriv API field names
                name = market.get("underlying_symbol_name", "")
                code = market.get("underlying_symbol", "")

                # Detect Volatility Index markets
                if "volatility" in name.lower():
                    print(f"🟢 {name} → {code}")
                    volatility_count += 1

            print("----------------------------")
            print(f"✅ Volatility markets found: {volatility_count}")

            # If none were found, show what Deriv actually sent
            if volatility_count == 0:
                print("")
                print("⚠️ No Volatility markets detected.")
                print("Showing first 20 markets received:")

                for market in symbols[:20]:
                    name = market.get("underlying_symbol_name", "")
                    code = market.get("underlying_symbol", "")
                    print(f"   {name} → {code}")

            break

    ws.close()

    print("")
    print("🤖 Test finished successfully!")

except Exception as e:

    print("")
    print("❌ CONNECTION FAILED")
    print(str(e))
