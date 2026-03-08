"""
test_main.py — Litematica-only test server for ClaudeCraft.

Strips out all AI / LangGraph logic from main.py and exposes only the
schematic parsing + layer-streaming pipeline over WebSocket.

Usage
-----
  python test_main.py              # start WebSocket server on ws://127.0.0.1:8080
  python test_main.py -p           # parse & print a .litematic file in the terminal
                                    # (no server, no Minecraft needed)

WebSocket protocol (same as main.py so the Minecraft client works unchanged)
-----------------------------------------------------------------------------
  Client sends any text message.
  Server replies:
    1. A plain text AI stub: "Build request received: <message>"
    2. If a schematic name is matched → streams BUILD_START, BUILD_LAYER×N, BUILD_DONE

Schematic matching
------------------
  - Looks up schematics.json for a fuzzy keyword match against the user's message.
  - Falls back to the first available schematic if no match found.
  - Schematic files must be in server/assets/*.litematic
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from google import genai

load_dotenv()

from lib.schematic_parser import parse_litematic

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

_gemini = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

SYSTEM_PROMPT = (
    "You are ClaudeCraft, a helpful Minecraft assistant. "
    "Answer questions about Minecraft clearly and concisely. "
    "If the user asks to build something, say you are loading the schematic now. "
    "Keep replies short (2-3 sentences max)."
)

def ask_gemini(user_message: str) -> str:
    """Call Gemini and return a plain-text response."""
    try:
        prompt = f"{SYSTEM_PROMPT}\n\nPlayer: {user_message}\nClaudeCraft:"
        response = _gemini.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return f"(AI unavailable: {e})"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("LitematicaTest")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR       = Path(__file__).parent
ASSETS_DIR     = BASE_DIR / "assets"
SCHEMATICS_JSON = BASE_DIR / "schematics.json"

# Delay between layer messages in seconds (set lower for faster testing)
LAYER_DELAY = 0.2

# ---------------------------------------------------------------------------
# Schematic registry
# ---------------------------------------------------------------------------

def load_schematic_registry() -> dict:
    """Load schematics.json — maps name → {description, tags}."""
    if not SCHEMATICS_JSON.exists():
        logger.warning(f"schematics.json not found at {SCHEMATICS_JSON}")
        return {}
    with open(SCHEMATICS_JSON) as f:
        return json.load(f)


def find_schematic(user_message: str, registry: dict) -> tuple[str | None, str | None]:
    """
    Try to match user_message against schematic names / tags.
    Returns (schematic_name, absolute_path) or (None, None) if nothing found.
    """
    msg_lower = user_message.lower()

    # 1. Direct name match
    for name in registry:
        if name.lower() in msg_lower:
            path = ASSETS_DIR / f"{name}.litematic"
            if path.exists():
                return name, str(path)

    # 2. Tag match
    for name, meta in registry.items():
        tags = meta.get("tags", [])
        if any(tag.lower() in msg_lower for tag in tags):
            path = ASSETS_DIR / f"{name}.litematic"
            if path.exists():
                return name, str(path)

    # 3. Keyword "build" / "load" / "schematic" → use first available file
    if any(kw in msg_lower for kw in ("build", "load", "schematic", "place")):
        for litematic in sorted(ASSETS_DIR.glob("*.litematic")):
            name = litematic.stem
            return name, str(litematic)

    return None, None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="ClaudeCraft Litematica Test Server")
schematic_registry = load_schematic_registry()


@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Minecraft client connected.")

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f">>> CLIENT: {data}")

            # ── 1. Get real AI response from Gemini ────────────────────────
            ai_reply = await asyncio.get_event_loop().run_in_executor(
                None, ask_gemini, data
            )
            await websocket.send_text(ai_reply)
            logger.info(f"<<< GEMINI: {ai_reply}")

            # ── 2. Check if this is a build request ────────────────────────
            schematic_name, schematic_path = find_schematic(data, schematic_registry)

            if not schematic_name or not schematic_path:
                logger.info("No schematic match — chat only response sent.")
                continue

            logger.info(f"Matched schematic: {schematic_name} → {schematic_path}")

            # ── 3. Parse the .litematic file ───────────────────────────────
            try:
                parsed = parse_litematic(schematic_path)
            except Exception as e:
                logger.error(f"Failed to parse schematic: {e}", exc_info=True)
                await websocket.send_text(f"Error parsing schematic '{schematic_name}': {e}")
                continue

            total_layers = parsed["total_layers"]

            # ── 4. Stream BUILD_START ──────────────────────────────────────
            start_msg = json.dumps({
                "type": "BUILD_START",
                "name": parsed["name"],
                "totalLayers": total_layers,
            })
            await websocket.send_text(start_msg)
            logger.info(f"<<< BUILD_START: {parsed['name']} ({total_layers} layers)")

            # ── 5. Stream each layer ───────────────────────────────────────
            for i, layer_data in parsed["layers"].items():
                layer_msg = json.dumps({
                    "type": "BUILD_LAYER",
                    "layerIndex": int(i),
                    "yLevel": layer_data["y_level"],
                    "blocks": layer_data["blocks"],
                })
                await websocket.send_text(layer_msg)
                logger.info(
                    f"<<< BUILD_LAYER {i}/{total_layers}: "
                    f"Y={layer_data['y_level']}, {len(layer_data['blocks'])} blocks"
                )
                await asyncio.sleep(LAYER_DELAY)

            # ── 6. Stream BUILD_DONE ───────────────────────────────────────
            done_msg = json.dumps({"type": "BUILD_DONE"})
            await websocket.send_text(done_msg)
            logger.info("<<< BUILD_DONE")

    except WebSocketDisconnect:
        logger.info("Minecraft client disconnected.")


# ---------------------------------------------------------------------------
# CLI parse mode  (-p flag)
# ---------------------------------------------------------------------------

def run_parse_mode() -> None:
    """
    No server, no Minecraft — parse a schematic and print every layer to stdout.
    Useful for quickly checking that a .litematic file is readable.
    """
    litematics = sorted(ASSETS_DIR.glob("*.litematic"))
    if not litematics:
        print(f"No .litematic files found in {ASSETS_DIR}")
        sys.exit(1)

    # Let user pick if there are multiple
    if len(litematics) == 1:
        chosen = litematics[0]
    else:
        print("Available schematics:")
        for i, f in enumerate(litematics, 1):
            print(f"  {i}. {f.name}")
        try:
            idx = int(input("Pick a number: ").strip()) - 1
            chosen = litematics[idx]
        except (ValueError, IndexError):
            print("Invalid choice.")
            sys.exit(1)

    print(f"\nParsing: {chosen}\n")
    try:
        result = parse_litematic(str(chosen))
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Name        : {result['name']}")
    print(f"Total layers: {result['total_layers']}")
    total_blocks = sum(len(ld["blocks"]) for ld in result["layers"].values())
    print(f"Total blocks: {total_blocks}")
    print()

    for layer_idx, layer_data in sorted(result["layers"].items(), key=lambda kv: int(kv[0])):
        blocks = layer_data["blocks"]
        if not blocks:
            continue
        print(f"  Layer {layer_idx:>3}  Y={layer_data['y_level']:>4}  —  {len(blocks):>5} blocks")
        # Show first 5 blocks as a sample
        for b in blocks[:5]:
            print(f"    ({b['x']:>4}, {b['y']:>4}, {b['z']:>4})  {b['block']}")
        if len(blocks) > 5:
            print(f"    ... and {len(blocks) - 5} more")

    print("\nDone.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "-p" in sys.argv:
        run_parse_mode()
    else:
        import uvicorn
        logger.info("Starting Litematica test server on ws://127.0.0.1:8080")
        uvicorn.run(app, host="127.0.0.1", port=8080)
