from device_control import DeviceControl
import numpy as np
import threading
import queue
import math
import json
import uuid 
import reedsolo
# --- CONFIGURATION ---
TX_SERIAL = "0000000000000000f77c60dc29417dc3"
FREQ = 1.2e9
SAMP_RATE = int(2e6)
SAMPLES_PER_SYMBOL = 100 
CHUNK_SIZE = 512  
# The decoupled queue used to receive data from the API
_tx_queue = queue.Queue()

# def add_parity(bits):
#     ones_count = bits.count('1')
#     parity_byte = '00000001' if (ones_count % 2) != 0 else '00000000'
#     return bits + parity_byte

rs = reedsolo.RSCodec(32)

def _text_to_dqpsk(text):
    # 1. Encode text to bytes, then apply Reed-Solomon FEC
    raw_bytes = text.encode('utf-8')
    fec_payload = list(rs.encode(raw_bytes)) 
    
    # 2. Add plaintext headers/footers for simple syncing
    start_bytes = list(b"[START]")
    end_bytes = list(b"[END]")
    full_frame = start_bytes + fec_payload + end_bytes
    
    # 3. Convert to 8-bit binary string
    bits = ''.join(format(b, '08b') for b in full_frame)

    phase_shifts = {
        '00': 0.0,
        '01': np.pi / 2,
        '11': np.pi,
        '10': -np.pi / 2
    }
    
    current_phase = 0.0
    iq_symbols =[]
    
    # Add a starting dummy symbol
    iq_symbols.append(np.exp(1j * current_phase) * 0.7) 
    
    # Map bits to phase changes, two at a time
    for i in range(0, len(bits), 2):
        bit_pair = bits[i:i+2]
        current_phase += phase_shifts[bit_pair]
        iq_symbols.append(np.exp(1j * current_phase) * 0.7)
        
    iq_symbols = np.array(iq_symbols, dtype=np.complex64)
    iq_data = np.repeat(iq_symbols, SAMPLES_PER_SYMBOL)
    return iq_data

def _sdr_worker():
    print("[HARDWARE] Booting HackRF Transmitter...")
    device = DeviceControl(TX_SERIAL, True, SAMP_RATE, FREQ, 60, 40)
    padding = np.zeros(int(SAMP_RATE * 0.5), dtype=np.complex64)
    print("[HARDWARE] HackRF is live. Waiting for data from API...")
    
    try:
        while True:
            # Block and wait until the API drops a payload into the queue
            payload_string = _tx_queue.get()
            
            iq_samples = _text_to_dqpsk(payload_string)

            full_burst = np.concatenate((padding, iq_samples, padding))
            mtu = device.getMTU()
            
            for i in range(0, len(full_burst), mtu):
                chunk = full_burst[i:i+mtu]
                device.write(chunk, len(chunk))
                
            print(f"[HARDWARE] DQPSK Burst sent. ({len(iq_samples)} baseband samples)")
            _tx_queue.task_done()
            
    except Exception as e:
        print(f"[HARDWARE] Error: {e}")
    finally:
        print("[HARDWARE] Shutting down SDR...")
        device.close()


# ==========================================
# PUBLIC API EXPOSED TO FASTAPI
# ==========================================

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