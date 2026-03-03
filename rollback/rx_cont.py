import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import sys

# --- CONFIGURATION ---
RX_SERIAL = "000000000000000075b068dc30792007"
FREQ = 1.2e9           # 1.2 GHz
SAMP_RATE = int(2e6)   # 2.0 MHz
SAMPLES_PER_SYMBOL = 100
CAPTURE_SECONDS = 1.5  # Reduced for faster, real-time terminal updates

def process_burst(iq_data):
    # Envelope detection
    mag = np.abs(iq_data)
    
    # Smooth out microscopic noise spikes (moving average low-pass filter)
    window_size = 5
    smoothed = np.convolve(mag, np.ones(window_size)/window_size, mode='same')
    
    max_val, min_val = np.max(smoothed), np.min(smoothed)
    
    # If the airwaves are quiet, fail silently without flooding the terminal
    if max_val < 0.05:
        return None

    # Dynamic slice threshold
    threshold = (max_val + min_val) / 2
    bool_array = smoothed > threshold

    # The exact binary sequence of "[START]"
    start_bits = ''.join(format(ord(i), '08b') for i in "[START]")
    
    # Check all 100 possible sync offsets
    for offset in range(SAMPLES_PER_SYMBOL):
        # Downsample stream at current offset
        downsampled = bool_array[offset :: SAMPLES_PER_SYMBOL]
        
        # Convert true/false array to '1' and '0' string
        bit_str = "".join(['1' if b else '0' for b in downsampled])
        
        # Scan for the preamble sequence
        idx = bit_str.find(start_bits)
        
        if idx != -1:
             # Extract raw binary payload from start marker onward
             payload_bits = bit_str[idx:]
             
             # Convert bits back to characters
             chars =[]
             for i in range(0, len(payload_bits)-7, 8):
                 byte = payload_bits[i:i+8]
                 chars.append(chr(int(byte, 2)))
                 
             full_text = "".join(chars)
             
             # Clean out the tags
             if "[END]" in full_text:
                 extracted = full_text.split("[START]")[1].split("[END]")[0]
                 return extracted
             else:
                 # Packet was cut off by the end of the buffer. 
                 # We will silently skip it; the next loop iteration will catch the next broadcast.
                 return None

    return None

def main():
    print(f"[INFO] Opening HackRF One RX: {RX_SERIAL}...")
    try:
        sdr = SoapySDR.Device(dict(driver="hackrf", serial=RX_SERIAL))
    except Exception as e:
        print(f"Failed to connect to HackRF: {e}")
        sys.exit(1)

    sdr.setSampleRate(SOAPY_SDR_RX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_RX, 0, FREQ)
    sdr.setGain(SOAPY_SDR_RX, 0, 30)

    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)

    total_samples = int(SAMP_RATE * CAPTURE_SECONDS)
    buffer = np.zeros(total_samples, dtype=np.complex64)
    mtu = sdr.getStreamMTU(rx_stream)
    temp_buf = np.zeros(mtu, dtype=np.complex64)
    
    print(f"\n[START] Listening continuously on {FREQ / 1e9} GHz...")
    print("Waiting for data... (Press Ctrl+C to stop)\n")

    try:
        while True:
            samples_read = 0
            
            # Fast buffer copy loop for this chunk
            while samples_read < total_samples:
                sr = sdr.readStream(rx_stream, [temp_buf], mtu)
                if sr.ret > 0:
                    end_idx = min(samples_read + sr.ret, total_samples)
                    read_len = end_idx - samples_read
                    buffer[samples_read:end_idx] = temp_buf[:read_len]
                    samples_read += read_len

            # Once the chunk is full, demodulate it
            result = process_burst(buffer)
            
            if result:
                print("=" * 40)
                print(f"MESSAGE RECEIVED: {result}")
                print("=" * 40)
                
                # Optionally keep logging to file
                with open("output.txt", "a") as f:
                    f.write(result + "\n")
                    
    except KeyboardInterrupt:
        print("\n[INFO] User interrupted. Stopping receiver...")
        
    finally:
        # This guarantees the HackRF is safely turned off when you quit
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        print("[INFO] Capture closed safely.")
    
if __name__ == '__main__':
    main()