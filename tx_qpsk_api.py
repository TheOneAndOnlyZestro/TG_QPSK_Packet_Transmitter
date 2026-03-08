from device_control import DeviceControl
from transmit import transmit
from receive import receive
from json_parser import process_json
import numpy as np
import threading
import queue
import math
import json
import uuid 
import reedsolo
import time
import traceback
from telemetry import Telemtry

from config_loader import TX_SERIAL, SAMP_RATE, FREQ, SAMPLES_PER_SYMBOL, CHUNK_SIZE, TX_GAIN, RX_GAIN, TIMEOUT, CAPTURE_SECONDS, MAX_RESEND, TRANS_COUNT
_tx_queue = queue.Queue()

rs = reedsolo.RSCodec(32)

# Global sequence counter to prevent duplicate file chunks
_global_seq_count = 0 

def _sdr_worker():
    global _global_seq_count
    print("[HARDWARE] Booting HackRF Transmitter...")
    device = DeviceControl(TX_SERIAL, True, SAMP_RATE, FREQ - (200000), TX_GAIN, RX_GAIN)
    tel = Telemtry()
    padding = np.zeros(int(SAMP_RATE * 0.25), dtype=np.complex64)
    print("[HARDWARE] HackRF is live. Waiting for data from API...")
    
    total_samples = int(SAMP_RATE * CAPTURE_SECONDS)
    buffer = np.zeros(total_samples, dtype=np.complex64)
    mtu = device.getMTU()
    temp_buf = np.zeros(mtu, dtype=np.complex64)
    
    try:
        while True:
            payload_string = _tx_queue.get()
            payload_dict = json.loads(payload_string)
            
            # Inject Sequence Count (our CCSDS routing equivalent)
            payload_dict["seq_count"] = _global_seq_count
            final_payload_string = json.dumps(payload_dict)
            
            ack_received = False
            
            packet_start_time = time.time()
            # Stop-and-Wait ARQ Loop
            for attempt in range(int(MAX_RESEND)):
                tel.log_attempt()
                print(f"[ARQ] Transmitting Seq {_global_seq_count} (Attempt {attempt + 1}/{MAX_RESEND})")
                
                for _ in range(TRANS_COUNT):
                    transmit(final_payload_string, device, padding, rs, SAMPLES_PER_SYMBOL)
                
                # Listen for the ACK over the FULL TIMEOUT window
                listen_start = time.time()
                while (time.time() - listen_start) < TIMEOUT:
                    time_left = TIMEOUT - (time.time() - listen_start)
                    print(f"[TIME] {time_left}")
                    ack_raw, _ = receive(buffer, temp_buf, device, SAMPLES_PER_SYMBOL, SAMP_RATE, rs, timeout=time_left)
                    
                    if ack_raw:
                        print(f"[ACK_RAW] {ack_raw}")
                        success, ack_dict = process_json(ack_raw)
                        # Verify it's an ACK and matches our sent sequence number!
                        if success and ack_dict.get("type") == "ack" and ack_dict.get("ack_seq") == _global_seq_count:
                            print(f"[ARQ] SUCCESS - Received valid ACK for Seq {_global_seq_count}")
                            ack_received = True
                            break
                        elif success and ack_dict.get("type") == "nack":
                            print("[ARQ] NACK received. Breaking listen loop to resend immediately.")
                            break # Breaks the listen loop, goes to next 'attempt' iteration
                
                if ack_received:
                    break # Break out of the resend loop
            
            if ack_received:
                rtt = time.time() - packet_start_time
                tel.log_success(len(final_payload_string.encode('utf-8')), rtt) 
                _global_seq_count = (_global_seq_count + 1) % 16384

                if _global_seq_count % 2 == 0:
                    tel.write_report()
                
            else:
                print(f"[ERROR] Max retries reached for Seq {_global_seq_count}. Packet Dropped.")
                
            _tx_queue.task_done()
            
    except Exception as e:
        traceback.print_exc()
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