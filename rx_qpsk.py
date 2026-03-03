import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import sys
import base64
import json
import os
import Levenshtein
import reedsolo
# --- CONFIGURATION ---
RX_SERIAL = "000000000000000075b068dc30792007"
FREQ = 1.2e9           
SAMP_RATE = int(2e6)   
SAMPLES_PER_SYMBOL = 100
CAPTURE_SECONDS = 1.5  

rs = reedsolo.RSCodec(32)

_received_blocks = {}
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

def finalize_file(data_dict):
    """Handles dispatching of fully assembled file files"""
    filename = data_dict.get('filename', '')
    if filename and '.' in filename:
        ext = filename.split('.')[-1].lower()
        if ext in extensions:
            extensions[ext](data_dict)
        else:
            print(f"[WARNING] No handler found for extension: .{ext}")
    else:
        print("[ERROR] File assembled but filename is missing or invalid.")



def process_json(extracted):
    print(f"RAW DATA: {extracted}")
    try:
        data_dict = json.loads(extracted)
        kind = data_dict.get('type')
        
        if kind == 'file_chunk':
            # Extract tracking info
            block_id = data_dict.get('block_id')
            chunk_id = data_dict.get('chunk_id')
            total_chunks = data_dict.get('total_chunks')
            filename = data_dict.get('filename')
            payload = data_dict.get('payload')
            
            if not block_id:
                return

            # Note: Out of order handling wrapper
            if block_id not in _received_blocks:
                _received_blocks[block_id] = {
                    'filename': filename,
                    'total_chunks': total_chunks,
                    'chunks': {}
                }
                
            block_state = _received_blocks[block_id]
            
            # Record it (repeated identical chunk_ids overwrite effortlessly avoiding duplication logic)
            if chunk_id not in block_state['chunks']:
                block_state['chunks'][chunk_id] = payload
                current_count = len(block_state['chunks'])
                print(f"[ASSEMBLY] '{filename}' - Received chunk {chunk_id + 1}/{total_chunks} ({current_count}/{total_chunks} total)")
            
            # Check if assembly is complete
            if len(block_state['chunks']) == total_chunks:
                print(f"[ASSEMBLY] File '{filename}' complete! Rebuilding base64 string...")
                
                # Sort the dictionary items by chunk_id and concatenate
                sorted_chunks = sorted(block_state['chunks'].items(), key=lambda x: x[0])
                full_base64 = "".join([chunk_data for _, chunk_data in sorted_chunks])
                
                # Send to final processing
                finalize_file({
                    'type': 'file',
                    'filename': block_state['filename'],
                    'payload': full_base64
                })
                
                # Cleanup the hash dictionary
                del _received_blocks[block_id]
                
        elif kind == 'text':
            print(f"MESSAGE: {data_dict.get('payload')}")

    except json.JSONDecodeError:
        print("[ERROR] Failed to parse JSON. Radio interference likely corrupted the packet.")

def check_parity(bit_string):
    end_bits_len = len("[END]") * 8
    
    incoming_parity_str = bit_string[-end_bits_len - 8 : -end_bits_len]
    
    payload_to_check = bit_string[0 : -end_bits_len - 8]
    
    if len(incoming_parity_str) != 8:
        return False
        
    incoming_parity_val = int(incoming_parity_str, 2)
    
    actual_ones = payload_to_check.count('1')
    expected_parity = actual_ones % 2
    
    return expected_parity == incoming_parity_val

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
                process_json(result)
                    
    except KeyboardInterrupt:
        print("\n[INFO] User interrupted. Stopping receiver...")
        
    finally:
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        print("[INFO] Capture closed safely.")
    
if __name__ == '__main__':
    main()