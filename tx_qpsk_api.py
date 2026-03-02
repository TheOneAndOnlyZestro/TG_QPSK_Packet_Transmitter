import SoapySDR
from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32
import numpy as np
import threading
import queue

# --- CONFIGURATION ---
TX_SERIAL = "0000000000000000f77c60dc29417dc3"
FREQ = 1.2e9
SAMP_RATE = int(2e6)
SAMPLES_PER_SYMBOL = 100 

# The decoupled queue used to receive data from the API
_tx_queue = queue.Queue()

def _text_to_dqpsk(text):
    # Frame the payload for the physical receiver
    framed_text = "[START]" + text + "[END]"
    print(f"[HARDWARE] Modulating payload of length: {len(framed_text)} characters")

    # Convert to 8-bit binary string
    bits = ''.join(format(ord(i), '08b') for i in framed_text)
    
    # DQPSK Phase Mapping
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
    sdr = SoapySDR.Device(dict(driver="hackrf", serial=TX_SERIAL))
    sdr.setSampleRate(SOAPY_SDR_TX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_TX, 0, FREQ)
    sdr.setGain(SOAPY_SDR_TX, 0, 60) 

    tx_stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)
    sdr.activateStream(tx_stream)
    
    padding = np.zeros(int(SAMP_RATE * 0.5), dtype=np.complex64)
    print("[HARDWARE] HackRF is live. Waiting for data from API...")
    
    try:
        while True:
            # Block and wait until the API drops a payload into the queue
            payload_string = _tx_queue.get()
            
            iq_samples = _text_to_dqpsk(payload_string)
            full_burst = np.concatenate((padding, iq_samples, padding))
            mtu = sdr.getStreamMTU(tx_stream)
            
            for i in range(0, len(full_burst), mtu):
                chunk = full_burst[i:i+mtu]
                sdr.writeStream(tx_stream,[chunk], len(chunk))
                
            print(f"[HARDWARE] DQPSK Burst sent. ({len(iq_samples)} baseband samples)")
            _tx_queue.task_done()
            
    except Exception as e:
        print(f"[HARDWARE] Error: {e}")
    finally:
        print("[HARDWARE] Shutting down SDR...")
        sdr.deactivateStream(tx_stream)
        sdr.closeStream(tx_stream)


# ==========================================
# PUBLIC API EXPOSED TO FASTAPI
# ==========================================

def start_transmitter():
    """Initializes the SDR and starts the hardware worker loop in a background thread."""
    thread = threading.Thread(target=_sdr_worker, daemon=True)
    thread.start()

def enqueue_payload(payload: str):
    """Allows the web backend to safely drop data into the transmission queue."""
    _tx_queue.put(payload)