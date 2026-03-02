import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np

RX_SERIAL = "000000000000000075b068dc30792007"
FREQ = 1.2e9
SAMP_RATE = int(2e6)
SAMPLES_PER_SYMBOL = 100
CAPTURE_SECONDS = 3  

def process_burst(iq_data):
    # Envelope detection
    mag = np.abs(iq_data)
    
    # 1. Smooth out microscopic noise spikes (moving average low-pass filter)
    window_size = 5
    smoothed = np.convolve(mag, np.ones(window_size)/window_size, mode='same')
    
    max_val, min_val = np.max(smoothed), np.min(smoothed)
    print(f"Debug: Filtered Signal Max: {max_val:.3f}, Min: {min_val:.3f}")
    
    if max_val < 0.05:
        print("Error: No signal spikes detected.")
        return None

    # Dynamic slice threshold
    threshold = (max_val + min_val) / 2
    bool_array = smoothed > threshold

    # The exact binary sequence of "[START]"
    start_bits = ''.join(format(ord(i), '08b') for i in "[START]")
    
    print("Brute-forcing symbol synchronization...")
    
    # 2. Check all 100 possible sync offsets
    for offset in range(SAMPLES_PER_SYMBOL):
        # Downsample stream at current offset
        downsampled = bool_array[offset :: SAMPLES_PER_SYMBOL]
        
        # Convert true/false array to '1' and '0' string
        bit_str = "".join(['1' if b else '0' for b in downsampled])
        
        # Scan for the preamble sequence
        idx = bit_str.find(start_bits)
        
        if idx != -1:
             print(f"Phase Synchronization locked at offset {offset}!")
             
             # Extract raw binary payload from start marker onward
             payload_bits = bit_str[idx:]
             
             # Convert bits back to characters
             chars = []
             for i in range(0, len(payload_bits)-7, 8):
                 byte = payload_bits[i:i+8]
                 chars.append(chr(int(byte, 2)))
                 
             full_text = "".join(chars)
             
             # Clean out the tags
             if "[END]" in full_text:
                 extracted = full_text.split("[START]")[1].split("[END]")[0]
                 return extracted
             else:
                 print("Found [START], but packet truncated before [END].")
                 return None

    print("Alignment failed. Preamble not found in any phase offset.")
    return None

def main():
    print(f"[INFO] Opening HackRF One RX: {RX_SERIAL}...")
    sdr = SoapySDR.Device(dict(driver="hackrf", serial=RX_SERIAL))
    sdr.setSampleRate(SOAPY_SDR_RX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_RX, 0, FREQ)
    sdr.setGain(SOAPY_SDR_RX, 0, 30)

    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)

    print(f"Gathering {CAPTURE_SECONDS} seconds of continuous RF data...")
    total_samples = int(SAMP_RATE * CAPTURE_SECONDS)
    buffer = np.zeros(total_samples, dtype=np.complex64)
    
    samples_read = 0
    mtu = sdr.getStreamMTU(rx_stream)
    temp_buf = np.zeros(mtu, dtype=np.complex64)
    
    # Fast buffer copy loop
    while samples_read < total_samples:
        sr = sdr.readStream(rx_stream, [temp_buf], mtu)
        if sr.ret > 0:
            end_idx = min(samples_read + sr.ret, total_samples)
            read_len = end_idx - samples_read
            buffer[samples_read:end_idx] = temp_buf[:read_len]
            samples_read += read_len

    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    print("Capture complete. Demodulating...")

    result = process_burst(buffer)
    
    if result:
        print("\nSUCCESS! Extracted text:")
        print("=" * 40)
        print(result)
        print("=" * 40)
        with open("output.txt", "w") as f:
            f.write(result)
        print("Data saved to output.txt")
    
if __name__ == '__main__':
    main()