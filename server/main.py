import os
import logging
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("LitemodBackend")

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logger.warning("GEMINI_API_KEY not found in environment. Gemini responses will fail.")
else:
    genai.configure(api_key=api_key)

app = FastAPI()

# Use the recommended Gemini model
model = genai.GenerativeModel('gemini-2.5-flash')

SYSTEM_PROMPT = """
You are a helpful Minecraft assistant in the game.
The user might ask you to load a schematic.
If the user's message indicates they want to build or load something into the world (like a house, a tree, etc.), 
your goal is to output exactly the following command:
LOAD_SCHEMATIC <filename>
Where <filename> is the name of the schematic they want without the .litematic extension.
If they are just chatting, respond normally and concisely.
"""

@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("New WebSocket connection established from Minecraft client.")
    
    # Start a chat session for this connection
    chat_session = model.start_chat(history=[])
    try:
        chat_session.send_message(SYSTEM_PROMPT)
        logger.info("System prompt initialized for new chat session.")
    except Exception as e:
        logger.error(f"Failed to initialize chat context: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from client: '{data}'")
            
            try:
                # Send to Gemini
                logger.info("Sending message to Gemini API...")
                response = chat_session.send_message(data)
                reply = response.text.strip()
                logger.info(f"Gemini responded: '{reply}'")
                await websocket.send_text(reply)
                logger.info("Response sent to Minecraft client.")
            except Exception as e:
                logger.error(f"Gemini API Error: {e}")
                await websocket.send_text("Sorry, I encountered an error communicating with Gemini.")

    except WebSocketDisconnect:
        logger.info("Minecraft client disconnected.")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI server on ws://127.0.0.1:8080")
    uvicorn.run(app, host="127.0.0.1", port=8080)
