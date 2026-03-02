import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import sys

# --- CONFIGURATION ---
RX_SERIAL = "000000000000000075b068dc30792007"
FREQ = 1.2e9           
SAMP_RATE = int(2e6)   
SAMPLES_PER_SYMBOL = 100
CAPTURE_SECONDS = 1.5  

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
            
            if result:
                print("=" * 40)
                print(f"MESSAGE RECEIVED: {result}")
                print("=" * 40)
                
                with open("output.txt", "a") as f:
                    f.write(result + "\n")
                    
    except KeyboardInterrupt:
        print("\n[INFO] User interrupted. Stopping receiver...")
        
    finally:
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        print("[INFO] Capture closed safely.")
    
if __name__ == '__main__':
    main()