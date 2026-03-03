from device_control import DeviceControl
from transmit import transmit
import numpy as np
import threading
import queue
import math
import json
import uuid 
import reedsolo
# --- CONFIGURATION ---
#TX_SERIAL = "0000000000000000f77c60dc29417dc3"
TX_SERIAL = "000000000000000075b068dc30792007"
FREQ = 1.2e9
SAMP_RATE = int(2e6)
SAMPLES_PER_SYMBOL = 100 
CHUNK_SIZE = 512  
# The decoupled queue used to receive data from the API
_tx_queue = queue.Queue()

rs = reedsolo.RSCodec(32)
def _sdr_worker():
    print("[HARDWARE] Booting HackRF Transmitter...")
    device = DeviceControl(TX_SERIAL, True, SAMP_RATE, FREQ, 70, 70)
    padding = np.zeros(int(SAMP_RATE * 0.5), dtype=np.complex64)
    print("[HARDWARE] HackRF is live. Waiting for data from API...")
    
    try:
        while True:
            # Block and wait until the API drops a payload into the queue
            payload_string = _tx_queue.get()
            transmit(payload_string, device, padding, rs, SAMPLES_PER_SYMBOL)
            _tx_queue.task_done()
            
    except Exception as e:
        print(f"[HARDWARE] Error: {e}")
    finally:
        print("[HARDWARE] Shutting down SDR...")
        device.close()

def start_transmitter():
    """Initializes the SDR and starts the hardware worker loop in a background thread."""
    thread = threading.Thread(target=_sdr_worker, daemon=True)
    thread.start()

def enqueue_payload(payload: str):
    try:
        final_payload = json.loads(payload)
    except json.JSONDecodeError:
        print("[ERROR] Failed to parse payload JSON before enqueueing.")
        return

    if final_payload.get("type") == "file":
        filename = final_payload.get("filename", "unknown_file")
        base64_data = final_payload.get("payload", "")
        
        total_length = len(base64_data)
        total_chunks = math.ceil(total_length / CHUNK_SIZE)
        
        if total_chunks == 0:
            total_chunks = 1
            
        print(f"[API] Splitting file '{filename}' into {total_chunks} chunks...")
        
        # ---> Produce a unique Block ID for reassembly <---
        block_id = uuid.uuid4().hex
        
        for i in range(total_chunks):
            start_idx = i * CHUNK_SIZE
            end_idx = start_idx + CHUNK_SIZE
            chunk_data = base64_data[start_idx:end_idx]
            
            # Update dictionary with block_id
            chunk_packet = {
                "type": "file_chunk",
                "block_id": block_id,
                "filename": filename,
                "chunk_id": i,
                "total_chunks": total_chunks,
                "payload": chunk_data
            }
            
            chunk_json_string = json.dumps(chunk_packet)
            _tx_queue.put(chunk_json_string)
            
        print(f"[API] Successfully enqueued {total_chunks} chunks for '{filename}'.")
            
    else:
        _tx_queue.put(payload)