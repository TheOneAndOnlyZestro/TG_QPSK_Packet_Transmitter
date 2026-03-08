from device_control import DeviceControl
import numpy as np
import reedsolo
import time
from config_loader import TIMEOUT, MAX_RESEND
def process_burst(iq_data, baud_rate: int, sample_rate: int, rs: reedsolo.RSCodec):
    # 1. Packet Detection (Find the burst using Amplitude Envelope)
    iq_data = iq_data - np.mean(iq_data)

    mag = np.abs(iq_data)
    window_size = baud_rate * 2
    smoothed = np.convolve(mag, np.ones(window_size)/window_size, mode='same')
    
    max_val = np.max(smoothed)
    #print(f"MAX VAL: {max_val}")
    # if max_val < 0.1:  # Absolute noise floor threshold
    #     return None

    noise_floor = np.median(smoothed)
    
    # If the peak is not at least 3x louder than the background noise, ignore it.
    if max_val < (noise_floor * 3.0): 
        return None
    
    # Dynamic threshold: The QPSK signal will be a solid "block" of amplitude
    threshold = max_val * 0.5
    active_indices = np.where(smoothed > threshold)[0]
    
    if len(active_indices) < baud_rate * 10:
        return None # Too short, just a noise pop

    # Snip out the burst, giving it a tiny buffer on the edges
    start_idx = max(0, active_indices[0] - baud_rate)
    end_idx = min(len(iq_data), active_indices[-1] + baud_rate)
    burst = iq_data[start_idx:end_idx]

    # 2. Carrier Recovery (Correct HackRF internal clock frequency drift)
    # Raising a QPSK signal to the 4th power removes the phase modulation, 
    # leaving only a massive spike at 4x the frequency offset!
    N = len(burst)
    burst_4 = burst**4 
    fft_res = np.fft.fft(burst_4)
    fft_freqs = np.fft.fftfreq(N, d=1/sample_rate)
    
    peak_idx = np.argmax(np.abs(fft_res))
    f_offset = fft_freqs[peak_idx] / 4.0
    
    # Derotate the burst to bring it perfectly back to 0 Hz baseband
    t = np.arange(N) / sample_rate
    derotated_burst = burst * np.exp(-1j * 2 * np.pi * f_offset * t)

    # 3. Symbol Timing & Phase Decoding
    start_bits = ''.join(format(ord(i), '08b') for i in "[START]")
    
    # Brute force 100 offset phases
    for offset in range(baud_rate):
        syms = derotated_burst[offset :: baud_rate]
        if len(syms) < 2: 
            continue
            
        # Measure the phase DIFFERENCE between the current symbol and the previous one
        diff_phases = np.angle(syms[1:] * np.conj(syms[:-1]))
        
        # Map phase angles back into bit pairsd
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
             # Skip the [START] string bits automatically
             payload_bits = bit_str[idx + len(start_bits):]
             
             # Reconstruct raw byte array
             byte_array = bytearray()
             for i in range(0, len(payload_bits)-7, 8):
                 byte = payload_bits[i:i+8]
                 byte_array.append(int(byte, 2))
                 
             # Find the [END] tag in the raw bytes
             end_idx = byte_array.find(b"[END]")
             if end_idx != -1:
                 # Extract everything between START and END
                 fec_payload = byte_array[:end_idx]
                 
                 # --- Apply Forward Error Correction ---
                 try:
                     # RS decode returns a tuple: (decoded_data, decoded_ecc, erasures)
                     # We only care about the repaired data at index [0]
                     repaired_bytes = rs.decode(fec_payload)[0]
                     #print(f"THE UNREPAIRED BYTES: {fec_payload}")
                     extracted_text = repaired_bytes.decode('utf-8')
                     print("[SUCCESS] FEC passed. Packet repaired and approved.")
                     return extracted_text
                     
                 except reedsolo.ReedSolomonError:
                     # This triggers if the errors exceed the 16-byte maximum threshold
                     print("[FEC ERROR] Corrupted block dropped: RF interference exceeded correction limits.")
                     return None
             else:
                 return None

    return None

def receive(buff: np.ndarray, temp_buff: np.ndarray, device: DeviceControl, baud_rate: int, sample_rate: int, rs: reedsolo.RSCodec, timeout: float = TIMEOUT):
    samples_read = 0
    start_time = time.time()
    
    # 1. Read until buffer is full OR timeout expires
    while samples_read < len(buff):
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            break
            
        sr = device.read(temp_buff, len(temp_buff))
        
        if sr.ret > 0:
            end_idx = min(samples_read + sr.ret, len(buff))
            read_len = end_idx - samples_read
            buff[samples_read:end_idx] = temp_buff[:read_len]
            samples_read += read_len
        elif sr.ret == 0:
            # 2. Prevent CPU lockup if SoapySDR has no samples ready
            time.sleep(0.001) 
        else:
            # Handle SDR read errors gracefully (negative return codes)
            pass

    elapsed = time.time() - start_time

    # 3. ONLY process the portion of the buffer that was actually filled
    if samples_read > baud_rate * 10:
        valid_buff = buff[:samples_read]
        result = process_burst(valid_buff, baud_rate, sample_rate, rs)
        return result, elapsed
    