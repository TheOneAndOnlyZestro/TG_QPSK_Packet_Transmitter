import SoapySDR
from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32
import numpy as np
import time
import signal
import sys

# --- CONFIGURATION ---
FREQ = 1.2e9          # 100 MHz (Easy for most scopes)
SAMP_RATE = 10e6      # 10 MSps
TX_GAIN = 60          # Start low (0-47 range)
TONE_FREQ = 1e6       # 1 MHz offset sine wave

def run_test():
    # 1. Initialize Device
    args = dict(driver="hackrf")
    sdr = SoapySDR.Device(args)
    
    # 2. Setup Channel
    sdr.setSampleRate(SOAPY_SDR_TX, 0, SAMP_RATE)
    sdr.setFrequency(SOAPY_SDR_TX, 0, FREQ)
    sdr.setGain(SOAPY_SDR_TX, 0, TX_GAIN)
    
    # 3. Create Tone (Complex Sine wave)
    # We create a 1MHz sine wave within our 10MHz sample rate
    num_samples = 1024 * 16
    t = np.arange(num_samples) / SAMP_RATE
    # Generating e^(j * 2 * pi * f * t)
    tx_buffer = np.exp(1j * 2 * np.pi * TONE_FREQ * t).astype(np.complex64)
    # Scale to 0.8 to prevent digital clipping
    tx_buffer *= 0.8

    # 4. Start Streaming
    tx_stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)
    sdr.activateStream(tx_stream)
    
    print(f"Transmitting Tone at {FREQ/1e6 + TONE_FREQ/1e6} MHz...")
    print("Check your oscilloscope. Press Ctrl+C to stop.")

    try:
        while True:
            # Continuously send the same buffer
            sr = sdr.writeStream(tx_stream, [tx_buffer], len(tx_buffer))
            if sr.ret < 0:
                print(f"Error writing to stream: {sr.ret}")
                break
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        sdr.deactivateStream(tx_stream)
        sdr.closeStream(tx_stream)

if __name__ == "__main__":
    run_test()