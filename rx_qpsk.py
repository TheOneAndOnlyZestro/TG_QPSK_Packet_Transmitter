from device_control import DeviceControl
from json_parser import process_json
from transmit import transmit
from receive import receive
import numpy as np
import sys
import os
import json
import time
import reedsolo
import matplotlib
import matplotlib.pyplot as plt
from config_loader import RX_SERIAL, SAMP_RATE, FREQ, CAPTURE_SECONDS, SAMPLES_PER_SYMBOL, TX_GAIN, RX_GAIN, TIMEOUT

rs = reedsolo.RSCodec(32)

def send_ack(device, seq_count, padding):
    # CRITICAL: Wait for Transmitter to switch its HackRF to RX mode (Turnaround time)
    time.sleep(0.05) 
    
    ack_dict = {
        "type": "ack",
        "ack_seq": seq_count
    }
    ack_string = json.dumps(ack_dict)
    print(f"[ARQ] Transmitting ACK for Seq {seq_count}...")
    for _ in range(4):
        transmit(ack_string, device, padding, rs, SAMPLES_PER_SYMBOL)

def main():
    print(f"[INFO] Opening HackRF One RX: {RX_SERIAL}...")
    try:
        device = DeviceControl(RX_SERIAL, False, SAMP_RATE, FREQ - 200000, TX_GAIN, RX_GAIN)
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    total_samples = int(SAMP_RATE * CAPTURE_SECONDS)
    buffer = np.zeros(total_samples, dtype=np.complex64)
    mtu = device.getMTU()
    temp_buf = np.zeros(mtu, dtype=np.complex64)
    padding = np.zeros(int(SAMP_RATE * 0.5), dtype=np.complex64)
    
    last_seq_count = -1 
    
    print(f"\n[START] Listening continuously for QPSK on {FREQ / 1e9} GHz...")

    fig, ax = plt.subplots(nrows=2, ncols=1, figsize=(6,8))
    ax[0].clear()
    ax[0].scatter(buffer.real, buffer.imag, s=2, alpha=0.4)   # ← update here
    ax[0].set_xlabel("In-phase (I)")
    ax[0].set_ylabel("Quadrature (Q)")
    ax[0].set_title("Raw Received Signal")
    ax[0].grid(True)

    ax[1].clear()
    ax[1].scatter(buffer.real, buffer.imag, s=2, alpha=0.4)   # ← update here
    ax[1].set_xlabel("In-phase (I)")
    ax[1].set_ylabel("Quadrature (Q)")
    ax[1].set_title("Signal After modulation")
    ax[1].grid(True)
    plt.show(block=False)

    try:
        while True:
            # We use TIMEOUT here to allow safe KeyboardInterrupt catching
            result_string, _ = receive(buffer, temp_buf, device, SAMPLES_PER_SYMBOL, SAMP_RATE, rs, TIMEOUT, (fig,ax))
            
            if result_string:
                success, data_dict = process_json(result_string)
                
                if success:
                    current_seq = data_dict.get("seq_count")
                    
                    # If this packet requires an ACK (has a seq_count)
                    if current_seq is not None:
                        # Prevent saving a file chunk twice if our previous ACK dropped
                        if current_seq == last_seq_count:
                            print(f"[ARQ] Duplicate packet detected (Seq {current_seq}). Resending ACK.")
                            send_ack(device, current_seq, padding)
                        else:
                            last_seq_count = current_seq
                            send_ack(device, current_seq, padding)

    except KeyboardInterrupt:
        print("\n[INFO] User interrupted. Stopping receiver...")
        
    finally:
        device.close()
        print("[INFO] Capture closed safely.")
    
if __name__ == '__main__':
    main()