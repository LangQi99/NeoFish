"""Quick diagnostic for NapCat WebSocket connection."""
import asyncio
import json
import sys

async def diagnose():
    import aiohttp

    url = "ws://127.0.0.1:3001"
    token = "483FcqWsABmkqsjs"

    # Try with access_token in query
    test_url = f"{url}?access_token={token}" if token else url
    print(f"Connecting to: {test_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(test_url) as ws:
                print(f"Connected! Type={type(ws).__name__}")

                # Read the first 5 messages
                for i in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                        print(f"\n--- Message {i+1} ---")
                        print(f"Type: {msg.type}")
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            print(f"Data keys: {list(data.keys())}")
                            print(f"Data: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print(f"CLOSED: code={msg.data}, extra={msg.extra}")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"ERROR: {msg.data}")
                            break
                        else:
                            print(f"Raw: {msg}")
                    except asyncio.TimeoutError:
                        print(f"\n--- Timeout after {i} messages ---")
                        break

                print("\nDone receiving. Connection seems stable.")
    except Exception as e:
        print(f"Connection failed: {type(e).__name__}: {e}")

asyncio.run(diagnose())
