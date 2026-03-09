"""
Claude Craft — FastAPI WebSocket server powered by LangGraph.

Handles text/binary WebSocket communication with the Minecraft client.
All AI logic is delegated to the LangGraph agent pipeline.

Run modes
---------
  python main.py              — start the WebSocket server (default)
  python main.py -e           — end-to-end CLI mode: no server, interact in the
                                terminal and see the full request pipeline printed
                                step by step (images → palette → …)
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import sys
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

import asyncio
import json

from graph import build_graph, AgentState
from lib.schematic_parser import parse_litematic

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ClaudeCraftServer")

# ---------------------------------------------------------------------------
# App + graph
# ---------------------------------------------------------------------------

app = FastAPI(title="Claude Craft Server")
agent = build_graph()

# Delay between layers in seconds (controls build animation speed)
LAYER_DELAY = 0.5


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Minecraft client connected.")

    # Per-connection chat history (persists across messages in one session)
    chat_history: list[dict] = []

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f">>> CLIENT: {data}")

            # Build the initial state for this turn
            state: AgentState = {
                "user_message": data,
                "chat_history": chat_history,
                "intent": "",
                "ai_response": "",
                "schematic_name": None,
                "schematic_path": None,
                "build_plan": None,
            }

            try:
                # Run the LangGraph pipeline
                result = agent.invoke(state)

                # Persist updated history for next turn
                chat_history = result.get("chat_history", chat_history)

                # 1. Always send the text response first
                ai_response = result.get("ai_response", "")
                if ai_response:
                    logger.info(f"<<< AI: {ai_response[:80]}...")
                    await websocket.send_text(ai_response)

                # 2. If a build was matched, stream it layer by layer
                schematic_name = result.get("schematic_name")
                schematic_path = result.get("schematic_path")

                if schematic_name and schematic_path and os.path.isfile(schematic_path):
                    try:
                        parsed = parse_litematic(schematic_path)
                        total_layers = parsed["total_layers"]

                        # Send BUILD_START
                        start_msg = json.dumps({
                            "type": "BUILD_START",
                            "name": parsed["name"],
                            "totalLayers": total_layers,
                        })
                        await websocket.send_text(start_msg)
                        logger.info(f"<<< BUILD_START: {total_layers} layers")

                        # Stream each layer with a delay
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

                        # Send BUILD_DONE
                        done_msg = json.dumps({"type": "BUILD_DONE"})
                        await websocket.send_text(done_msg)
                        logger.info("<<< BUILD_DONE")

                    except Exception as parse_err:
                        logger.error(f"Schematic parse/stream error: {parse_err}", exc_info=True)
                        await websocket.send_text(f"Error parsing schematic: {parse_err}")

                elif schematic_name and not schematic_path:
                    logger.warning(f"Schematic '{schematic_name}' matched but path missing.")

            except Exception as e:
                logger.error(f"Pipeline error: {e}", exc_info=True)
                await websocket.send_text("Sorry, I encountered an error processing your request.")

    except WebSocketDisconnect:
        logger.info("Minecraft client disconnected.")


# ---------------------------------------------------------------------------
# End-to-end CLI mode  (-e flag)
# ---------------------------------------------------------------------------

# Node names that carry interesting pipeline state worth printing
_E2E_DISPLAY_NODES = {
    "image_search":       ("Reference images", "reference_images"),
    "palette":            ("Block palette",    "block_palette"),
    "trellis_generator":  ("Generated model",  "combined_blocks"),
}

# Simple ANSI colours for readability (no extra deps)
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_CYAN  = "\033[36m"
_GREEN = "\033[32m"
_RESET = "\033[0m"


def _print_pipeline_step(node: str, update: dict) -> None:
    """Pretty-print a single graph node's output during e2e mode."""
    label, key = _E2E_DISPLAY_NODES.get(node, (None, None))
    if label is None:
        return

    value = update.get(key)
    print(f"\n{_CYAN}{_BOLD}[{node}]{_RESET} {_BOLD}{label}:{_RESET}")

    if not value:
        print(f"  {_DIM}(none){_RESET}")
        return

    if key == "combined_blocks":
        print(f"  {_DIM}{len(value)} total blocks in 3D grid{_RESET}")
        if update.get('glb_path'):
            print(f"  {_CYAN}GLB Path:{_RESET} {_DIM}{update['glb_path']}{_RESET}")
        if update.get('obj_path'):
            print(f"  {_CYAN}OBJ Path:{_RESET} {_DIM}{update['obj_path']}{_RESET}")
        return

    if isinstance(value, list):
        for i, item in enumerate(value, 1):
            if isinstance(item, dict) and "url" in item:
                print(f"  {_DIM}{i:>2}.{_RESET} {item['url']}")
            elif isinstance(item, str) and item.startswith("data:"):
                size_kb = len(item) // 1024
                print(f"  {_DIM}{i:>2}.{_RESET} [base64 image, ~{size_kb}KB]")
            else:
                print(f"  {_DIM}{i:>2}.{_RESET} {item}")
    else:
        print(f"  {value}")


def run_e2e() -> None:
    """Interactive CLI pipeline runner — no WebSocket, full step visibility."""
    print(f"\n{_BOLD}Claude Craft — End-to-End Mode{_RESET}")
    print(f"{_DIM}Type a build request and watch the full pipeline. Ctrl-C or 'quit' to exit.{_RESET}\n")

    graph = build_graph()
    chat_history: list[dict] = []

    try:
        while True:
            try:
                user_input = input(f"{_GREEN}You>{_RESET} ").strip()
            except EOFError:
                break

            if not user_input or user_input.lower() in ("quit", "exit"):
                break

            state: AgentState = {
                "user_message": user_input,
                "chat_history": chat_history,
                "intent": "",
                "ai_response": "",
                "schematic_name": None,
                "schematic_path": None,
                "build_plan": None,
            }

            print(f"\n{_DIM}── pipeline ──────────────────────────────{_RESET}")

            final_state: dict = {}
            try:
                # stream() yields {node_name: state_update} after each node
                for step in graph.stream(state):
                    for node_name, node_update in step.items():
                        print(f"{_DIM}  → {node_name}{_RESET}", end="", flush=True)
                        _print_pipeline_step(node_name, node_update)
                        if not _E2E_DISPLAY_NODES.get(node_name):
                            print()  # newline after the dim arrow
                        final_state.update(node_update)

            except Exception as e:
                print(f"\n{_BOLD}Pipeline error:{_RESET} {e}")
                logger.error("e2e pipeline error", exc_info=True)
                continue

            # Show final AI text response
            ai_response = final_state.get("ai_response", "")
            if ai_response:
                print(f"\n{_DIM}── response ──────────────────────────────{_RESET}")
                print(f"{_BOLD}AI:{_RESET} {ai_response}")

            # Show block palette summary if one was produced
            palette = final_state.get("block_palette")
            if palette:
                print(f"\n{_DIM}── final palette ──────────────────────────{_RESET}")
                for layer, block in palette.items():
                    print(f"  {layer}: {block}")

            print(f"\n{_DIM}──────────────────────────────────────────{_RESET}")
            chat_history = final_state.get("chat_history", chat_history)

    except KeyboardInterrupt:
        pass

    print(f"\n{_DIM}Bye.{_RESET}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "-e" in sys.argv:
        run_e2e()
    else:
        import uvicorn

        logger.info("Starting Claude Craft server on ws://127.0.0.1:8080")
        uvicorn.run(app, host="127.0.0.1", port=8080)
