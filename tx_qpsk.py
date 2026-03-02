import SoapySDR
from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32
import numpy as np
import time

TX_SERIAL = "0000000000000000f77c60dc29417dc3"
FREQ = 1.2e9
SAMP_RATE = 2e6
SAMPLES_PER_SYMBOL = 100 

def text_to_dqpsk(text):
    framed_text = "[START]" + text + "[END]"
    print(f"Payload to send: {framed_text}")

    # Convert to 8-bit binary string
    bits = ''.join(format(ord(i), '08b') for i in framed_text)
    
    # DQPSK Phase Mapping: (2 bits per phase shift)
    # 00: 0 deg | 01: 90 deg | 11: 180 deg | 10: -90 deg
    phase_shifts = {
        '00': 0.0,
        '01': np.pi / 2,
        '11': np.pi,
        '10': -np.pi / 2
    }
    
    current_phase = 0.0
    iq_symbols =[]
    
    # Add a starting dummy symbol so the receiver has a reference to compare the first bit to
    iq_symbols.append(np.exp(1j * current_phase) * 0.7) 
    
    # Map bits to phase changes, two at a time
    for i in range(0, len(bits), 2):
        bit_pair = bits[i:i+2]
        current_phase += phase_shifts[bit_pair]
        # Multiply by 0.7 to avoid clipping the SDR DAC
        iq_symbols.append(np.exp(1j * current_phase) * 0.7)
        
    iq_symbols = np.array(iq_symbols, dtype=np.complex64)
    
    # Repeat phase symbols to match baud rate
    iq_data = np.repeat(iq_symbols, SAMPLES_PER_SYMBOL)
    return iq_data

def main():
    sdr = SoapySDR.Device(dict(driver="hackrf", serial=TX_SERIAL))
    sdr.setSampleRate(SOAPY_SDR_TX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_TX, 0, FREQ)
    sdr.setGain(SOAPY_SDR_TX, 0, 60) 

    tx_stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)
    sdr.activateStream(tx_stream)
    
    # 0.5 seconds of zeros to separate bursts
    padding = np.zeros(int(SAMP_RATE * 0.5), dtype=np.complex64)
    
    print("Please type in something to broadcast.....")
    try:
        while True:
            msg = input("> ")
            iq_samples = text_to_dqpsk(msg)
            full_burst = np.concatenate((padding, iq_samples, padding))
            mtu = sdr.getStreamMTU(tx_stream)
            
            for i in range(0, len(full_burst), mtu):
                chunk = full_burst[i:i+mtu]
                sdr.writeStream(tx_stream, [chunk], len(chunk))
                
            print(f"DQPSK Burst sent ({len(iq_samples)} baseband samples).")
            
    except KeyboardInterrupt:
        print("\nStopping transmitter...")

    sdr.deactivateStream(tx_stream)
    sdr.closeStream(tx_stream)

if __name__ == '__main__':
    main()