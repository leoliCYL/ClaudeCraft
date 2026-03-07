import os
import logging
import re
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from urllib.parse import urlparse
from openai import OpenAI

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

# Perplexity Setup (Using OpenAI-compatible SDK)
PPLX_API_KEY = os.getenv("PERPLEXITY_API_KEY")
pplx_client = OpenAI(api_key=PPLX_API_KEY, base_url="https://api.perplexity.ai") if PPLX_API_KEY else None

# --- Constants & Helpers ---
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
URL_REGEX = re.compile(r'(https?://[^\s]+)', re.IGNORECASE)

def extract_image_urls(text: str) -> list[str]:
    urls = URL_REGEX.findall(text)
    return [url for url in urls if any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)]

def search_reference_images_with_perplexity(prompt: str) -> list[str]:
    if not pplx_client:
        return []
    
    # Perplexity is a text-model API. We ask it specifically for direct image links.
    query = f"Provide a list of direct image URLs (ending in .jpg or .png) for: {prompt}"
    
    try:
        response = pplx_client.chat.completions.create(
            model="sonar-pro", # Or your preferred Perplexity model
            messages=[{"role": "user", "content": query}]
        )
        content = response.choices[0].message.content
        return extract_image_urls(content)
    except Exception as e:
        logger.error(f"Perplexity Search Error: {e}")
        return []

app = FastAPI()

# Use the recommended Gemini model
model = genai.GenerativeModel('gemini-1.5-flash')

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
    logger.info("Starting FastAPI server on ws://127.0.0.1:8081")
    uvicorn.run(app, host="127.0.0.1", port=8081)
