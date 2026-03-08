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

CHAT_SYSTEM_PROMPT = (
    "You are ClaudeCraft, a helpful Minecraft assistant. "
    "Answer questions about Minecraft clearly and concisely. "
    "If the user asks to build something, say you are generating the schematic now. "
    "Keep replies short (2-3 sentences max)."
)

BUILD_SYSTEM_PROMPT = """You are a Minecraft block placement AI. The user wants to build something.
Return ONLY a valid JSON object — no explanation, no markdown, no code fences.

The JSON must look like this:
{
  "name": "structure name",
  "layers": [
    {
      "y_level": 0,
      "blocks": [
        {"x": 0, "y": 0, "z": 0, "block": "minecraft:stone"},
        {"x": 1, "y": 0, "z": 0, "block": "minecraft:stone"}
      ]
    },
    {
      "y_level": 1,
      "blocks": [
        {"x": 0, "y": 1, "z": 0, "block": "minecraft:oak_planks"}
      ]
    }
  ]
}

Rules:
- Use only valid Minecraft 1.21 block IDs (prefixed with "minecraft:")
- Keep structures small (max 10x10x10 blocks) — quality over quantity
- Each y_level layer must have at least 1 block
- x/z range: 0-9, y matches y_level
- Return ONLY the JSON object, nothing else."""


def ask_gemini(user_message: str) -> str:
    """Call Gemini for chat and return a plain-text response."""
    try:
        prompt = f"{CHAT_SYSTEM_PROMPT}\n\nPlayer: {user_message}\nClaudeCraft:"
        response = _gemini.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini chat error: {e}")
        return f"(AI unavailable: {e})"


def ask_gemini_build(build_request: str) -> dict | None:
    """Call Gemini to generate a block structure. Returns parsed JSON dict or None."""
    try:
        prompt = f"{BUILD_SYSTEM_PROMPT}\n\nUser wants to build: {build_request}\n\nJSON:"
        response = _gemini.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip()
        # Strip markdown code fences if Gemini added them anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        logger.error(f"Gemini build error: {e}")
        return None

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
    global _active_websocket
    await websocket.accept()
    _active_websocket = websocket
    logger.info("Minecraft client connected.")

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f">>> CLIENT: {data}")

            is_build = data.strip().startswith("[BUILD]")

            if is_build:
                # ── BUILD path: use Gemini to generate a block structure ───
                build_msg = data.strip()[len("[BUILD]"):].strip()

                # Send a quick acknowledgement first
                await websocket.send_text(f"Generating '{build_msg}' now...")

                # Ask Gemini to generate JSON block data
                build_data = await asyncio.get_event_loop().run_in_executor(
                    None, ask_gemini_build, build_msg
                )

                if build_data and "layers" in build_data:
                    layers = build_data["layers"]
                    total_layers = len(layers)
                    schematic_name = build_data.get("name", build_msg)

                    # BUILD_START
                    await websocket.send_text(json.dumps({
                        "type": "BUILD_START",
                        "name": schematic_name,
                        "totalLayers": total_layers,
                    }))
                    logger.info(f"<<< BUILD_START: {schematic_name} ({total_layers} layers)")

                    # BUILD_LAYER × N
                    for i, layer in enumerate(layers):
                        await websocket.send_text(json.dumps({
                            "type": "BUILD_LAYER",
                            "layerIndex": i,
                            "yLevel": layer.get("y_level", i),
                            "blocks": layer.get("blocks", []),
                        }))
                        logger.info(
                            f"<<< BUILD_LAYER {i}/{total_layers}: "
                            f"Y={layer.get('y_level', i)}, {len(layer.get('blocks', []))} blocks"
                        )
                        await asyncio.sleep(LAYER_DELAY)

                    # BUILD_DONE
                    await websocket.send_text(json.dumps({"type": "BUILD_DONE"}))
                    logger.info("<<< BUILD_DONE")
                else:
                    logger.error("Gemini build returned no usable data.")
                    await websocket.send_text("Sorry, I couldn't generate that structure. Try describing it differently.")

            else:
                # ── CHAT path: Gemini for fast conversational replies ──────
                ai_reply = await asyncio.get_event_loop().run_in_executor(
                    None, ask_gemini, data
                )
                await websocket.send_text(ai_reply)
                logger.info(f"<<< GEMINI: {ai_reply[:80]}")

    except WebSocketDisconnect:
        _active_websocket = None
        logger.info("Minecraft client disconnected.")


# ---------------------------------------------------------------------------
# Interactive prompt mode  (-p flag)
# ---------------------------------------------------------------------------

_active_websocket: WebSocket | None = None

_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_GREEN = "\033[32m"
_RESET = "\033[0m"


async def _prompt_loop() -> None:
    """Read build prompts from stdin and stream results to the connected Minecraft client."""
    print(f"\n{_BOLD}ClaudeCraft prompt mode{_RESET}")
    print(f"{_DIM}Type a build request below and press Enter.")
    print(f"The pipeline will run and stream results to the connected Minecraft client.")
    print(f"Ctrl-C to quit.{_RESET}\n")

    loop = asyncio.get_event_loop()

    while True:
        try:
            user_input = await loop.run_in_executor(
                None, lambda: input(f"{_GREEN}Build>{_RESET} ").strip()
            )
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        ws = _active_websocket
        if ws is None:
            print(f"{_DIM}  (no Minecraft client connected — waiting…){_RESET}")
            continue

        print(f"{_DIM}  → asking Gemini to generate '{user_input}'…{_RESET}")
        asyncio.create_task(_run_build_for_prompt(ws, user_input))


async def _run_build_for_prompt(websocket: WebSocket, build_request: str) -> None:
    """Ask Gemini to generate block data and stream BUILD_* packets to Minecraft."""
    try:
        await websocket.send_text(f"Generating '{build_request}' now...")

        build_data = await asyncio.get_event_loop().run_in_executor(
            None, ask_gemini_build, build_request
        )

        if build_data and "layers" in build_data:
            layers = build_data["layers"]
            total_layers = len(layers)
            schematic_name = build_data.get("name", build_request)

            await websocket.send_text(json.dumps({
                "type": "BUILD_START",
                "name": schematic_name,
                "totalLayers": total_layers,
            }))
            print(f"{_GREEN}✓ BUILD_START: {schematic_name} ({total_layers} layers){_RESET}")

            for i, layer in enumerate(layers):
                await websocket.send_text(json.dumps({
                    "type": "BUILD_LAYER",
                    "layerIndex": i,
                    "yLevel": layer.get("y_level", i),
                    "blocks": layer.get("blocks", []),
                }))
                await asyncio.sleep(LAYER_DELAY)

            await websocket.send_text(json.dumps({"type": "BUILD_DONE"}))
            print(f"{_GREEN}✓ BUILD_DONE — streamed to Minecraft{_RESET}\n")
        else:
            print(f"  (Gemini returned no usable data)\n")
            await websocket.send_text("Sorry, I couldn't generate that structure. Try describing it differently.")

    except Exception as e:
        print(f"{_BOLD}Build error:{_RESET} {e}")
        logger.error("Prompt build error", exc_info=True)


# ---------------------------------------------------------------------------
# CLI parse mode  (--parse flag)
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
    if "--parse" in sys.argv:
        run_parse_mode()
    elif "-p" in sys.argv:
        # Prompt mode: server + terminal input loop running together
        import uvicorn

        async def _serve_with_prompt():
            config = uvicorn.Config(app, host="127.0.0.1", port=8080, log_level="warning")
            server = uvicorn.Server(config)
            print(f"{_BOLD}Starting server on ws://127.0.0.1:8080{_RESET}")
            print(f"{_DIM}Open Minecraft first, then type your build prompt below.{_RESET}\n")
            await asyncio.gather(server.serve(), _prompt_loop())

        asyncio.run(_serve_with_prompt())
    else:
        import uvicorn
        logger.info("Starting Litematica test server on ws://127.0.0.1:8080")
        uvicorn.run(app, host="127.0.0.1", port=8080)
