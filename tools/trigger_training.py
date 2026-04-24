"""Trigger manual training by sending a chat message via WebSocket."""

import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def send():
    try:
        import websockets
    except ImportError:
        import subprocess

        subprocess.run(["pip", "install", "websockets", "--quiet"])
        import websockets

    async with websockets.connect("ws://localhost:8000/ws") as ws:
        msg = json.dumps({"type": "admin_chat", "text": "train all agents now", "target": "ALL"})
        await ws.send(msg)
        print("Training command sent!")
        try:
            while True:
                resp = await asyncio.wait_for(ws.recv(), timeout=90)
                data = json.loads(resp)
                extra = data.get("extra", {})
                if extra.get("training") or extra.get("chat_reply"):
                    agent = data.get("agent", "?")
                    message = data.get("message", "")[:200]
                    print(f"[{agent}] {message}")
        except asyncio.TimeoutError:
            print("Timeout - done listening")
        except Exception as e:
            print(f"Done: {e}")


asyncio.run(send())
