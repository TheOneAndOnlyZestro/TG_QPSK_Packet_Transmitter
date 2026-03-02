import SoapySDR
from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32
import numpy as np
import time

TX_SERIAL = "0000000000000000f77c60dc29417dc3"
FREQ = 1.2e9
SAMP_RATE = 2e6
SAMPLES_PER_SYMBOL = 100 # Slowed down for reliability (20k baud)


def text_to_ook(filename):
    with open(filename, 'r') as f:
        text = f.read()
    
    # Add a preamble so the RX knows EXACTLY where data starts
    framed_text = "[START]" + text + "[END]"
    print(f"Payload to send: {framed_text}")

    # Convert to 8-bit binary strings
    bits = ''.join(format(ord(i), '08b') for i in framed_text)
    
    # OOK Modulation: '1' -> Amplitude 1.0, '0' -> Amplitude 0.0
    iq_data = np.array([1.0 + 0j if b == '1' else 0.0 + 0j for b in bits], dtype=np.complex64)
    
    # Repeat samples to define symbol length
    iq_data = np.repeat(iq_data, SAMPLES_PER_SYMBOL)
    return iq_data

def main():
    sdr = SoapySDR.Device(dict(driver="hackrf", serial=TX_SERIAL))
    sdr.setSampleRate(SOAPY_SDR_TX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_TX, 0, FREQ)
    sdr.setGain(SOAPY_SDR_TX, 0, 60) # Keep relatively low

    tx_stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)
    sdr.activateStream(tx_stream)

    iq_samples = text_to_ook("input.txt")
    print(f"Modulated {len(iq_samples)} baseband samples.")

    # Send padding (zeros) to "warm up" the receiver's AGC if applied
    padding = np.zeros(int(SAMP_RATE), dtype=np.complex64)

    try:
        while True:
            print("Transmitting burst...")
            # Send zeros, then data
            full_burst = np.concatenate((padding, iq_samples, padding))
            mtu = sdr.getStreamMTU(tx_stream)
            
            for i in range(0, len(full_burst), mtu):
                chunk = full_burst[i:i+mtu]
                sdr.writeStream(tx_stream, [chunk], len(chunk))
                
            print("Burst sent. Waiting 2 seconds...")
            time.sleep(2)
            
    except KeyboardInterrupt:
        pass

    sdr.deactivateStream(tx_stream)
    sdr.closeStream(tx_stream)

if __name__ == '__main__':
    main()