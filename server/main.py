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
import sys
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from urllib.parse import urlparse
from openai import OpenAI

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
                "rag_score": None,
                "reference_images": None,
                "block_palette": None,
                "palette_map": None,
                "components": None,
                "component_results": [],
                "combined_blocks": None,
                "build_json": None,
                "build_layers": None,
                "total_layers": None,
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
    "image_search":      ("Reference images",  "reference_images"),
    "palette":           ("Block palette",     "block_palette"),
    "component_planner": ("Components",        "components"),
    "component_builder": ("Built component",   "component_results"),
    "combiner":          ("Build JSON",        "build_json"),
    "converter":         ("Schematic",         "schematic_path"),
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

    if isinstance(value, list):
        for i, item in enumerate(value, 1):
            if isinstance(item, dict) and "url" in item and "data" in item:
                print(f"  {_DIM}{i:>2}.{_RESET} {item['url']}")
            # Component specs from planner
            elif isinstance(item, dict) and "component_name" in item:
                dims = item.get("dimensions", {})
                print(f"  {_DIM}{i:>2}.{_RESET} {item['component_name']} "
                      f"({dims.get('X','?')}x{dims.get('Y','?')}x{dims.get('Z','?')}) "
                      f"— {len(item.get('blocks',[]))} block types")
            # Built component results
            elif isinstance(item, dict) and "name" in item:
                s = item.get("size", {})
                print(f"  {_DIM}{i:>2}.{_RESET} {item['name']} "
                      f"({s.get('x','?')}x{s.get('y','?')}x{s.get('z','?')})")
            else:
                print(f"  {_DIM}{i:>2}.{_RESET} {item}")
    elif isinstance(value, dict):
        comps = value.get("components", [])
        palette = value.get("palette", {})
        print(f"  {len(comps)} components, {len(palette)} palette entries")
    elif isinstance(value, str):
        print(f"  {_GREEN}{value}{_RESET}")
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
                "rag_score": None,
                "reference_images": None,
                "block_palette": None,
                "palette_map": None,
                "components": None,
                "component_results": [],
                "combined_blocks": None,
                "build_json": None,
                "build_layers": None,
                "total_layers": None,
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
                print(f"\n{_DIM}── final palette ({len(palette)} blocks) ──────────{_RESET}")
                for i, block in enumerate(palette, 1):
                    print(f"  {i:>2}. {block}")

            # Show generated schematic path
            sch_path = final_state.get("schematic_path")
            if sch_path:
                print(f"\n{_GREEN}{_BOLD}✓ Schematic saved: {sch_path}{_RESET}")
                total = final_state.get("total_layers", 0)
                if total:
                    print(f"  {total} layers")

            print(f"\n{_DIM}──────────────────────────────────────────{_RESET}")
            chat_history = final_state.get("chat_history", chat_history)

    except KeyboardInterrupt:
        pass

    print(f"\n{_DIM}Bye.{_RESET}\n")


# ---------------------------------------------------------------------------
# Interactive prompt mode  (-p flag)
# ---------------------------------------------------------------------------

# Holds the most-recently connected WebSocket so the prompt thread can push to it
_active_websocket: WebSocket | None = None


async def _prompt_loop() -> None:
    """
    Runs in the background while the server is live.
    Reads build prompts from stdin and sends them as [BUILD] messages
    so they go through the exact same pipeline as Minecraft client messages.
    """
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

        # Inject the message as if it came from the Minecraft client
        # The websocket_endpoint loop is already handling receive_text(),
        # so we fake an inbound message by directly running the pipeline
        # and pushing results back through the open socket.
        print(f"{_DIM}  → sending to pipeline…{_RESET}")
        asyncio.create_task(_run_build_for_prompt(ws, user_input))


async def _run_build_for_prompt(websocket: WebSocket, build_request: str) -> None:
    """Run the LangGraph pipeline for a terminal prompt and stream results to Minecraft."""
    state: AgentState = {
        "user_message": build_request,
        "chat_history": [],
        "intent": "build",
        "ai_response": "",
        "schematic_name": None,
        "schematic_path": None,
        "rag_score": None,
        "reference_images": None,
        "block_palette": None,
        "palette_map": None,
        "components": None,
        "component_results": [],
        "combined_blocks": None,
        "build_json": None,
        "build_layers": None,
        "total_layers": None,
        "build_plan": None,
    }

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: agent.invoke(state)
        )

        ai_response = result.get("ai_response", "")
        if ai_response:
            print(f"{_BOLD}AI:{_RESET} {ai_response}")
            await websocket.send_text(ai_response)

        # Stream build layers to Minecraft
        build_layers = result.get("build_layers")
        total_layers = result.get("total_layers", 0)
        schematic_name = result.get("schematic_name") or build_request

        # Fallback: RAG hit returned a schematic_path but no build_layers
        if not build_layers and result.get("schematic_path"):
            try:
                parsed = parse_litematic(result["schematic_path"])
                build_layers = parsed["layers"]
                total_layers = parsed["total_layers"]
                schematic_name = parsed["name"]
            except Exception as pe:
                logger.error(f"Fallback parse failed: {pe}")

        if build_layers and total_layers:
            await websocket.send_text(json.dumps({
                "type": "BUILD_START",
                "name": schematic_name,
                "totalLayers": total_layers,
            }))
            print(f"{_GREEN}✓ BUILD_START: {schematic_name} ({total_layers} layers){_RESET}")

            for i, layer_data in build_layers.items():
                await websocket.send_text(json.dumps({
                    "type": "BUILD_LAYER",
                    "layerIndex": int(i),
                    "yLevel": layer_data["y_level"],
                    "blocks": layer_data["blocks"],
                }))
                await asyncio.sleep(LAYER_DELAY)

            await websocket.send_text(json.dumps({"type": "BUILD_DONE"}))
            print(f"{_GREEN}✓ BUILD_DONE — streamed to Minecraft{_RESET}\n")
        else:
            print(f"{_DIM}  (pipeline returned no layers){_RESET}\n")

    except Exception as e:
        print(f"{_BOLD}Pipeline error:{_RESET} {e}")
        logger.error("Prompt pipeline error", exc_info=True)


# Patch websocket_endpoint to track the active socket
_original_ws_endpoint = websocket_endpoint.__wrapped__ if hasattr(websocket_endpoint, "__wrapped__") else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "-e" in sys.argv:
        run_e2e()
    elif "-p" in sys.argv:
        # Prompt mode: start the server AND a terminal prompt loop
        import uvicorn

        # Monkey-patch the websocket handler to track the active connection
        original_handler = app.routes[-1].endpoint  # the websocket_endpoint func

        async def _tracking_ws_endpoint(websocket: WebSocket):
            global _active_websocket
            _active_websocket = websocket
            logger.info("Minecraft client connected (prompt mode).")
            try:
                await original_handler(websocket)
            finally:
                _active_websocket = None
                logger.info("Minecraft client disconnected (prompt mode).")

        # Replace the route
        app.routes[-1].endpoint = _tracking_ws_endpoint

        async def _serve_with_prompt():
            config = uvicorn.Config(app, host="127.0.0.1", port=8080, log_level="warning")
            server = uvicorn.Server(config)
            print(f"{_BOLD}Starting server on ws://127.0.0.1:8080{_RESET}")
            print(f"{_DIM}Open Minecraft first, then type your build prompt below.{_RESET}\n")
            await asyncio.gather(server.serve(), _prompt_loop())

        asyncio.run(_serve_with_prompt())
    else:
        import uvicorn

        logger.info("Starting Claude Craft server on ws://127.0.0.1:8080")
        uvicorn.run(app, host="127.0.0.1", port=8080)
