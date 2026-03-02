import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import sys
import base64
import json
import os
# --- CONFIGURATION ---
RX_SERIAL = "000000000000000075b068dc30792007"
FREQ = 1.2e9           
SAMP_RATE = int(2e6)   
SAMPLES_PER_SYMBOL = 100
CAPTURE_SECONDS = 1.5  



# --- 1. Define the Handler Functions ---

def handle_jpg(data):
    filename = data.get('filename', 'received_image') + 'mina.jpg'
    payload = data.get('payload', '')
    
    try:
        # Decode the Base64 string back into binary bytes
        img_bytes = base64.b64decode(payload)
        with open(filename, 'wb') as f:
            f.write(img_bytes)
        print(f"[SUCCESS] JPG image saved as: {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to save JPG: {e}")

def handle_png(data):
    filename = data.get('filename', 'received_image.png')
    payload = data.get('payload', '')
    
    try:
        img_bytes = base64.b64decode(payload)
        with open(filename, 'wb') as f:
            f.write(img_bytes)
        print(f"[SUCCESS] PNG image saved as: {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to save PNG: {e}")

# --- 2. Create the Extensions Dictionary ---

# This maps the file extension string to the function name
extensions = {
    'jpg': handle_jpg,
    'jpeg': handle_jpg, # Map both to the same function
    'png': handle_png
}

def process_json(extracted):
    print(extracted)
    try:
        data_dict = json.loads(extracted)
        kind = data_dict.get('type')
        if kind == 'file':
            filename = data_dict.get('filename', '')
            print(f"filename:{filename}")
            if filename and '.' in filename:
                # Get the extension and convert to lowercase (e.g., "JPG" -> "jpg")
                ext = filename.split('.')[-1].lower()
                
                # Check if we have a function to handle this specific extension
                if ext in extensions:
                    # Execute the function passing the whole data_dict
                    extensions[ext](data_dict)
                else:
                    print(f"[WARNING] No handler found for extension: .{ext}")
            else:
                print("[ERROR] File received but filename is missing or invalid.")
                
        elif kind == 'text':
            print(f"MESSAGE: {data_dict.get('payload')}")

    except json.JSONDecodeError:
        print("[ERROR] Failed to parse JSON. Radio interference likely corrupted the packet.")
def process_burst(iq_data):
    # 1. Packet Detection (Find the burst using Amplitude Envelope)
    mag = np.abs(iq_data)
    window_size = SAMPLES_PER_SYMBOL * 2
    smoothed = np.convolve(mag, np.ones(window_size)/window_size, mode='same')
    
    max_val = np.max(smoothed)
    if max_val < 0.1:  # Absolute noise floor threshold
        return None

    # Dynamic threshold: The QPSK signal will be a solid "block" of amplitude
    threshold = max_val * 0.5
    active_indices = np.where(smoothed > threshold)[0]
    
    if len(active_indices) < SAMPLES_PER_SYMBOL * 10:
        return None # Too short, just a noise pop

    # Snip out the burst, giving it a tiny buffer on the edges
    start_idx = max(0, active_indices[0] - SAMPLES_PER_SYMBOL)
    end_idx = min(len(iq_data), active_indices[-1] + SAMPLES_PER_SYMBOL)
    burst = iq_data[start_idx:end_idx]

    # 2. Carrier Recovery (Correct HackRF internal clock frequency drift)
    # Raising a QPSK signal to the 4th power removes the phase modulation, 
    # leaving only a massive spike at 4x the frequency offset!
    N = len(burst)
    burst_4 = burst**4 
    fft_res = np.fft.fft(burst_4)
    fft_freqs = np.fft.fftfreq(N, d=1/SAMP_RATE)
    
    peak_idx = np.argmax(np.abs(fft_res))
    f_offset = fft_freqs[peak_idx] / 4.0
    
    # Derotate the burst to bring it perfectly back to 0 Hz baseband
    t = np.arange(N) / SAMP_RATE
    derotated_burst = burst * np.exp(-1j * 2 * np.pi * f_offset * t)

    # 3. Symbol Timing & Phase Decoding
    start_bits = ''.join(format(ord(i), '08b') for i in "[START]")
    
    # Brute force 100 offset phases
    for offset in range(SAMPLES_PER_SYMBOL):
        syms = derotated_burst[offset :: SAMPLES_PER_SYMBOL]
        if len(syms) < 2: 
            continue
            
        # Measure the phase DIFFERENCE between the current symbol and the previous one
        diff_phases = np.angle(syms[1:] * np.conj(syms[:-1]))
        
        # Map phase angles back into bit pairs
        bit_list =[]
        for dp in diff_phases:
            if -np.pi/4 <= dp < np.pi/4:          # ~0 deg
                bit_list.append('00')
            elif np.pi/4 <= dp < 3*np.pi/4:       # ~90 deg
                bit_list.append('01')
            elif -3*np.pi/4 <= dp < -np.pi/4:     # ~-90 deg
                bit_list.append('10')
            else:                                 # ~180 deg
                bit_list.append('11')
                
        bit_str = "".join(bit_list)
        
        # Search for preamble
        idx = bit_str.find(start_bits)
        if idx != -1:
             payload_bits = bit_str[idx:]
             
             # Reconstruct Bytes
             chars =[]
             for i in range(0, len(payload_bits)-7, 8):
                 byte = payload_bits[i:i+8]
                 chars.append(chr(int(byte, 2)))
                 
             full_text = "".join(chars)
             
             if "[END]" in full_text:
                 extracted = full_text.split("[START]")[1].split("[END]")[0]
                 return extracted
             else:
                 return None

    return None

def main():
    print(f"[INFO] Opening HackRF One RX: {RX_SERIAL}...")
    try:
        sdr = SoapySDR.Device(dict(driver="hackrf", serial=RX_SERIAL))
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    sdr.setSampleRate(SOAPY_SDR_RX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_RX, 0, FREQ)
    sdr.setGain(SOAPY_SDR_RX, 0, 40) # Gain bumped slightly for Phase

    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)

    total_samples = int(SAMP_RATE * CAPTURE_SECONDS)
    buffer = np.zeros(total_samples, dtype=np.complex64)
    mtu = sdr.getStreamMTU(rx_stream)
    temp_buf = np.zeros(mtu, dtype=np.complex64)
    
    print(f"\n[START] Listening continuously for QPSK on {FREQ / 1e9} GHz...")
    print("Waiting for data... (Press Ctrl+C to stop)\n")

    try:
        while True:
            samples_read = 0
            while samples_read < total_samples:
                sr = sdr.readStream(rx_stream,[temp_buf], mtu)
                if sr.ret > 0:
                    end_idx = min(samples_read + sr.ret, total_samples)
                    read_len = end_idx - samples_read
                    buffer[samples_read:end_idx] = temp_buf[:read_len]
                    samples_read += read_len

            result = process_burst(buffer)
            print(result + "\n")
            if result:
                process_json(result)
                    
    except KeyboardInterrupt:
        print("\n[INFO] User interrupted. Stopping receiver...")
        
    finally:
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        print("[INFO] Capture closed safely.")
    
if __name__ == '__main__':
    main()