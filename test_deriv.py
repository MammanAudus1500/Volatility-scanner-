import json
import websocket

print("==============================================")
print("🤖 SIXSGAMES - FULL MARKET DISCOVERY TEST")
print("==============================================")

URL = "wss://api.derivws.com/trading/v1/options/ws/public"

# Markets we want the scanner to watch
WANTED_MARKETS = [
    # Volatility
    "Volatility 5",
    "Volatility 5 (1s)",
    "Volatility 10",
    "Volatility 10 (1s)",
    "Volatility 15",
    "Volatility 15 (1s)",
    "Volatility 25",
    "Volatility 25 (1s)",
    "Volatility 30",
    "Volatility 30 (1s)",
    "Volatility 50",
    "Volatility 50 (1s)",
    "Volatility 75",
    "Volatility 75 (1s)",
    "Volatility 90",
    "Volatility 90 (1s)",
    "Volatility 100",
    "Volatility 100 (1s)",
    "Volatility 150",
    "Volatility 150 (1s)",

    # Jump
    "Jump 10 Index",
    "Jump 25 Index",
    "Jump 50 Index",
    "Jump 75 Index",
    "Jump 100 Index",

    # Step
    "Step Index",
    "Step Index 200",
    "Step Index 300",
    "Step Index 400",
    "Step Index 500",

    # Forex
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

    # Other
    "Gold/USD",
    "BTC/USD",
    "US 100"
]


def clean_name(name):
    """Make names easier to compare."""
    return (
        name.lower()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
        .replace("index", "")
        .replace("usd", "usd")
    )


try:

    print("")
    print("🔌 Connecting to Deriv...")

    ws = websocket.create_connection(
        URL,
        timeout=20
    )

    print("✅ Connected successfully!")

    request = {
        "active_symbols": "brief",
        "req_id": 1
    }

    print("📡 Downloading ALL active markets...")

    ws.send(json.dumps(request))

    while True:

        response = json.loads(ws.recv())

        if response.get("error"):

            print("")
            print("❌ DERIV ERROR")
            print(response["error"])
            break

        if response.get("msg_type") == "active_symbols":

            symbols = response.get("active_symbols", [])

            print("")
            print(f"📊 Deriv returned {len(symbols)} active markets")

            # Build searchable market database
            available = {}

            for market in symbols:

                name = market.get(
                    "underlying_symbol_name",
                    ""
                )

                code = market.get(
                    "underlying_symbol",
                    ""
                )

                if name and code:

                    available[clean_name(name)] = {
                        "name": name,
                        "code": code
                    }

            print("")
            print("==============================================")
            print("🎯 OUR REQUESTED MARKETS")
            print("==============================================")

            found = []
            missing = []

            for wanted in WANTED_MARKETS:

                wanted_clean = clean_name(wanted)

                match = None

                # Exact normalized match
                if wanted_clean in available:
                    match = available[wanted_clean]

                # Partial matching
                if match is None:

                    for key, item in available.items():

                        if (
                            wanted_clean in key
                            or key in wanted_clean
                        ):
                            match = item
                            break

                if match:

                    found.append(match)

                    print(
                        f"🟢 {wanted} "
                        f"→ {match['name']} "
                        f"→ {match['code']}"
                    )

                else:

                    missing.append(wanted)

                    print(
                        f"🔴 NOT FOUND → {wanted}"
                    )

            print("")
            print("==============================================")
            print("📊 DISCOVERY SUMMARY")
            print("==============================================")

            print(
                f"🟢 Requested markets found: "
                f"{len(found)}"
            )

            print(
                f"🔴 Requested markets missing: "
                f"{len(missing)}"
            )

            if missing:

                print("")
                print("⚠️ MARKETS NOT FOUND:")
                print("----------------------------------------------")

                for item in missing:
                    print(f"   {item}")

            print("")
            print("==============================================")
            print("🤖 MARKET DISCOVERY FINISHED")
            print("==============================================")

            break

    ws.close()

except Exception as e:

    print("")
    print("❌ CONNECTION FAILED")
    print(str(e))
