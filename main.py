from fastapi import FastAPI, UploadFile, Form
from contextlib import asynccontextmanager
import base64
import json

# ---------------------------------------------------------
# DECOUPLED HARDWARE IMPORT
# To swap hardware in the future, just change this import!
from tx_qpsk_api import start_transmitter, enqueue_payload
# ---------------------------------------------------------

# Startup event to initialize the hardware thread safely when FastAPI boots
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[API] Starting hardware transmitter thread...")
    start_transmitter()
    yield
    print("[API] Shutting down...")

app = FastAPI(lifespan=lifespan)

@app.post("/send_text")
async def send_text(message: str = Form(...)):
    # 1. Package the text into structured JSON
    packet = {
        "type": "text",
        "payload": message
    }
    
    # 2. Convert dictionary to string 
    json_data = json.dumps(packet)
    
    # 3. Hand off the raw string to the physical hardware module
    enqueue_payload(json_data)
    
    return {"status": "success", "message": "Text queued for transmission"}

@app.post("/send_file")
async def send_file(file: UploadFile):
    # 1. Read the raw file bytes
    file_bytes = await file.read()
    
    # 2. Encode to Base64 so it can be transmitted as a safe text string over the radio
    encoded_file = base64.b64encode(file_bytes).decode('utf-8')
    
    # 3. Package it into JSON
    packet = {
        "type": "file",
        "filename": file.filename,
        "payload": encoded_file
    }
    
    json_data = json.dumps(packet)
    
    # 4. Hand off to the hardware module
    enqueue_payload(json_data)
    
    return {"status": "success", "message": f"File '{file.filename}' queued for transmission"}