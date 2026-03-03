import SoapySDR
from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32
import numpy as np
import time
import struct
import zlib

TX_SERIAL = "0000000000000000f77c60dc29417dc3"
FREQ = 1.2e9        # Avoid 2.4 GHz noise
SAMP_RATE = int(2e6)
SAMPLES_PER_SYMBOL = 10  # 2 Msps / 10 SPS = 200 kbps

# Sync word: Alternating bits for AGC, then a unique frame marker
SYNC_WORD = [0xAA, 0xAA, 0xD3, 0x91]

def build_packet(filename):
    with open(filename, 'rb') as f:
        payload = f.read()
    
    # 1. Compute CRC-32 of the payload
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    
    # 2. Build header: Payload length (2 bytes, unsigned short)
    header = struct.pack('>H', len(payload))
    crc_bytes = struct.pack('>I', crc)
    
    # 3. Assemble full byte array
    packet_bytes = bytearray(SYNC_WORD) + header + payload + crc_bytes
    print(f"[TX] Packet constructed: {len(packet_bytes)} bytes total.")
    return np.array(packet_bytes, dtype=np.uint8)

def modulate_fsk(packet_bytes):
    # Convert bytes to a massive array of 1s and 0s
    bits = np.unpackbits(packet_bytes)
    
    # Map 0 to -1, 1 to +1
    symbols = 2.0 * bits - 1.0
    
    # Oversample to match SAMPLES_PER_SYMBOL
    baseband = np.repeat(symbols, SAMPLES_PER_SYMBOL)
    
    # Calculate phase step per sample (h=1.0 modulation index)
    phase_diff = baseband * (np.pi / SAMPLES_PER_SYMBOL)
    
    # Integrate to get continuous phase
    phase = np.cumsum(phase_diff)
    
    # Convert phase to complex I/Q (scaled to 0.8 to prevent DAC clipping)
    iq_data = (0.8 * np.exp(1j * phase)).astype(np.complex64)
    return iq_data

def main():
    sdr = SoapySDR.Device(dict(driver="hackrf", serial=TX_SERIAL))
    sdr.setSampleRate(SOAPY_SDR_TX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_TX, 0, FREQ)
    
    # HIGH GAIN for Over-The-Air antennas
    sdr.setGain(SOAPY_SDR_TX, 0, 40) 

    tx_stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)
    sdr.activateStream(tx_stream)

    packet_bytes = build_packet("input.txt")
    iq_samples = modulate_fsk(packet_bytes)
    
    # TX Padding to let the Receiver's hardware amp settle before data hits
    padding = np.zeros(int(SAMP_RATE * 0.1), dtype=np.complex64) 
    burst = np.concatenate((padding, iq_samples, padding))

    print(f"[TX] Modulated {len(iq_samples)} symbols. Airtime: {len(iq_samples)/SAMP_RATE:.3f} sec.")

    try:
        mtu = sdr.getStreamMTU(tx_stream)
        while True:
            print("[TX] Transmitting FSK burst at 1.3 GHz...")
            for i in range(0, len(burst), mtu):
                chunk = burst[i:i+mtu]
                sdr.writeStream(tx_stream, [chunk], len(chunk))
            time.sleep(1.5)
            
    except KeyboardInterrupt:
        pass

    sdr.deactivateStream(tx_stream)
    sdr.closeStream(tx_stream)

if __name__ == '__main__':
    main()