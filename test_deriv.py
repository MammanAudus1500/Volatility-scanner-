import json
import websocket

print("🤖 Connecting to Deriv...")

ws = websocket.create_connection(
    "wss://api.derivws.com/trading/v1/options/ws/public",
    timeout=15
)

print("✅ Connected to Deriv!")

request = {
    "active_symbols": "brief",
    "req_id": 1
}

ws.send(json.dumps(request))

while True:
    message = json.loads(ws.recv())

    if message.get("msg_type") == "active_symbols":
        symbols = message.get("active_symbols", [])

        print("\n📊 VOLATILITY INDICES FOUND:\n")

        found = 0

        for symbol in symbols:
            name = symbol.get("underlying_symbol_name", "")
            code = symbol.get("underlying_symbol", "")

            if "Volatility" in name:
                print(f"• {name}  →  {code}")
                found += 1

        print(f"\n✅ Total Volatility Indices found: {found}")

        break

    if "error" in message:
        print("❌ Deriv returned an error:")
        print(message["error"])
        break

ws.close()

print("\n🤖 Test finished.")
