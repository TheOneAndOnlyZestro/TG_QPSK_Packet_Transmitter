import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import scipy.signal
import struct
import zlib

RX_SERIAL = "000000000000000075b068dc30792007"
FREQ = 1.2e9
SAMP_RATE = int(2e6)
SAMPLES_PER_SYMBOL = 10 
CAPTURE_SECONDS = 5 

SYNC_WORD = [0xAA, 0xAA, 0xD3, 0x91]

def generate_ideal_sync_pulse():
    # We must generate what the sync word looks like AFTER FSK demodulation
    sync_bytes = np.array(SYNC_WORD, dtype=np.uint8)
    bits = np.unpackbits(sync_bytes)
    symbols = 2.0 * bits - 1.0
    baseband = np.repeat(symbols, SAMPLES_PER_SYMBOL)
    return baseband * (np.pi / SAMPLES_PER_SYMBOL)

def process_fsk_burst(iq_data):
    print("[RX] Demodulating FSK (Differential detection)...")
    # 1. Extract Instantaneous Frequency (Delay-Multiply-Angle)
    # This single line of numpy replaces massive 'for' loops entirely!
    freq_dev = np.angle(iq_data[1:] * np.conjugate(iq_data[:-1]))
    
    # 2. Correlate to find the exact starting sample
    ideal_pulse = generate_ideal_sync_pulse()
    print("[RX] Scanning 6,000,000 samples for Sync Sequence (FFT base)...")
    
    # Scipy utilizes FFT specifically to make this fast in Python
    corr = scipy.signal.correlate(freq_dev, ideal_pulse, mode='valid', method='fft')
    start_idx = np.argmax(corr) # Peak correlation = start of payload
    peak_val = corr[start_idx]
    
    # Basic sanity check to ensure it's not just static
    if peak_val < len(ideal_pulse) * 0.2:
        print("[RX] Peak correlation too low. Packet not found in background noise. Move antennas closer.")
        return None

    print(f"[RX] SYNC LOCKED at sample offset: {start_idx}")
    
    # Move the index to exactly the END of the sync word
    data_start_idx = start_idx + len(ideal_pulse)
    
    # Slicer function: Read N bits dynamically from a specific sample index
    def read_bits(start, num_bits):
        offset = start
        extracted = []
        for _ in range(num_bits):
            if offset >= len(freq_dev): break
            # Sample right in the direct center of the symbol
            sample_val = freq_dev[offset + SAMPLES_PER_SYMBOL // 2]
            extracted.append(1 if sample_val > 0 else 0)
            offset += SAMPLES_PER_SYMBOL
        return extracted, offset

    # 3. Read Header (Payload length, 16 bits)
    header_bits, next_idx = read_bits(data_start_idx, 16)
    if len(header_bits) < 16: return None
    header_bytes = np.packbits(header_bits)
    payload_len = struct.unpack('>H', header_bytes.tobytes())[0]
    
    if payload_len == 0 or payload_len > 10000:
        print(f"[RX] Error: Corrupted Payload Length parsed ({payload_len} bytes)")
        return None
        
    print(f"[RX] Header parsed. Expecting {payload_len} bytes of data.")
    
    # 4. Read Payload
    payload_bits, next_idx = read_bits(next_idx, payload_len * 8)
    payload_bytes = np.packbits(payload_bits).tobytes()
    
    # 5. Read CRC-32 Checksum
    crc_bits, _ = read_bits(next_idx, 32)
    crc_bytes = np.packbits(crc_bits).tobytes()
    received_crc = struct.unpack('>I', crc_bytes)[0]
    
    # 6. Verify Mathematical Integrity
    calculated_crc = zlib.crc32(payload_bytes) & 0xFFFFFFFF
    if calculated_crc == received_crc:
        print("\n[RX] CRC-32 VALID! File transfer successful over-the-air!")
        return payload_bytes.decode('utf-8', errors='ignore')
    else:
        print(f"\n[RX] CRC-32 FAILED! Expected {hex(calculated_crc)}, got {hex(received_crc)}.")
        print("[RX] The file was corrupted by RF interference mid-air.")
        return None

def main():
    print(f"[INFO] Opening HackRF One RX: {RX_SERIAL} (1.3 GHz OTA)...")
    sdr = SoapySDR.Device(dict(driver="hackrf", serial=RX_SERIAL))
    sdr.setSampleRate(SOAPY_SDR_RX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_RX, 0, FREQ)
    
    # Over The Air demands High Gain
    sdr.setGain(SOAPY_SDR_RX, 0, 40) # Overall gain

    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)

    total_samples = int(SAMP_RATE * CAPTURE_SECONDS)
    buffer = np.zeros(total_samples, dtype=np.complex64)
    samples_read = 0
    mtu = sdr.getStreamMTU(rx_stream)
    temp_buf = np.zeros(mtu, dtype=np.complex64)
    
    print("[RX] Listening for 3 seconds...")
    while samples_read < total_samples:
        sr = sdr.readStream(rx_stream, [temp_buf], mtu)
        if sr.ret > 0:
            end_idx = min(samples_read + sr.ret, total_samples)
            read_len = end_idx - samples_read
            buffer[samples_read:end_idx] = temp_buf[:read_len]
            samples_read += read_len

    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)

    result = process_fsk_burst(buffer)
    
    if result:
        print("=" * 40)
        print(result)
        print("=" * 40)
        with open("output.txt", "w") as f:
            f.write(result)
            
if __name__ == '__main__':
    main()