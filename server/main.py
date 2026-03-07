"""
Claude Craft — FastAPI WebSocket server powered by LangGraph.

Handles text/binary WebSocket communication with the Minecraft client.
All AI logic is delegated to the LangGraph agent pipeline.
"""

import os
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

import asyncio
import json

from graph import build_graph, AgentState
from schematic_parser import parse_litematic

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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Claude Craft server on ws://127.0.0.1:8080")
    uvicorn.run(app, host="127.0.0.1", port=8080)
