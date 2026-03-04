from device_control import DeviceControl
from json_parser import process_json
import numpy as np
import sys
from receive import receive

import os
import Levenshtein
import reedsolo

from config_loader import RX_SERIAL, SAMP_RATE, FREQ, CAPTURE_SECONDS, SAMPLES_PER_SYMBOL, TX_GAIN, RX_GAIN

rs = reedsolo.RSCodec(32)

_received_blocks = {}

def main():
    print(f"[INFO] Opening HackRF One RX: {RX_SERIAL}...")
    try:
        device = DeviceControl(RX_SERIAL, False, SAMP_RATE, FREQ, TX_GAIN,RX_GAIN)
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    total_samples = int(SAMP_RATE * CAPTURE_SECONDS)
    buffer = np.zeros(total_samples, dtype=np.complex64)
    mtu = device.getMTU()
    temp_buf = np.zeros(mtu, dtype=np.complex64)
    
    print(f"\n[START] Listening continuously for QPSK on {FREQ / 1e9} GHz...")
    print("Waiting for data... (Press Ctrl+C to stop)\n")

    try:
        while True:
            result = receive(buffer, temp_buf, device,SAMPLES_PER_SYMBOL,SAMP_RATE,rs)
            if result:
                process_json(result)
                    
    except KeyboardInterrupt:
        print("\n[INFO] User interrupted. Stopping receiver...")
        
    finally:
        device.close()
        print("[INFO] Capture closed safely.")
    
if __name__ == '__main__':
    main()