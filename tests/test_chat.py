"""Quick test: Send a chat message and see AI agent responses."""

import asyncio, json, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def test():
    try:
        import websockets
    except ImportError:
        import subprocess

        subprocess.run(["pip", "install", "websockets", "--quiet"])
        import websockets

    async with websockets.connect("ws://localhost:8000/ws") as ws:
        # Send a test question about gold
        msg = json.dumps({"type": "admin_chat", "text": "gold ka kya scene hai? buy karu ya sell?", "target": "ALL"})
        await ws.send(msg)
        print("Message sent! Waiting for AI responses...\n")

        responses_received = 0
        try:
            while True:
                resp = await asyncio.wait_for(ws.recv(), timeout=120)
                data = json.loads(resp)

                # Broadcast format: {"type": "msg", "payload": {...}}
                if data.get("type") == "msg":
                    payload = data.get("payload", {})
                    agent = payload.get("agent", "?")
                    content = payload.get("content", "")
                    extra = payload.get("data", {})

                    if extra.get("chat_reply") or extra.get("chat"):
                        responses_received += 1
                        print(f"[{agent}] {content[:500]}")
                        print("-" * 60)

                    if responses_received >= 6:
                        break

        except asyncio.TimeoutError:
            print(f"\nTimeout - got {responses_received} responses")
        except Exception as e:
            print(f"Done: {e}")


asyncio.run(test())
