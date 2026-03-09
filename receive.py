from device_control import DeviceControl
import numpy as np
import reedsolo
import time
from modulation import modulation_methods
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from config_loader import TIMEOUT, MAX_RESEND, MODULATION_METHOD

def process_burst(iq_data, baud_rate: int, sample_rate: int, rs: reedsolo.RSCodec, plot):
    
    if plot is not None:
        fig, ax = plot

        def update():
            ax.clear()  
            ax.scatter(iq_data.real,iq_data.imag)  
            fig.canvas.draw() 

        anim = FuncAnimation(fig, update)
        plt.show()
    # 1. Packet Detection (Find the burst using Amplitude Envelope)
    iq_data = iq_data - np.mean(iq_data)

    mag = np.abs(iq_data)
    window_size = baud_rate * 2
    smoothed = np.convolve(mag, np.ones(window_size)/window_size, mode='same')
    
    max_val = np.max(smoothed)
    noise_floor = np.median(smoothed)
    
    # If the peak is not at least 3x louder than the background noise, ignore it.
    if max_val < (noise_floor * 3.0): 
        return None
    threshold = max_val * 0.5
    active_indices = np.where(smoothed > threshold)[0]
    
    # if len(active_indices) < baud_rate * 10:
    #     return None # Too short, just a noise pop

    if len(active_indices) < 100:  
        return None # Too short, just a noise pop
    
    # Snip out the burst, giving it a tiny buffer on the edges
    start_idx = max(0, active_indices[0] - baud_rate)
    end_idx = min(len(iq_data), active_indices[-1] + baud_rate)
    burst = iq_data[start_idx:end_idx]

    start_bits = ''.join(format(ord(i), '08b') for i in "[START]")
    _, demod = modulation_methods[MODULATION_METHOD]
    payload_bits = demod(burst, baud_rate, sample_rate, start_bits)  

    if payload_bits:
        byte_array = bytearray()
        for i in range(0, len(payload_bits)-7, 8):
            byte = payload_bits[i:i+8]
            byte_array.append(int(byte, 2))
            
        end_idx = byte_array.find(b"[END]")
        if end_idx != -1:
            fec_payload = byte_array[:end_idx]
            try:
                repaired_bytes = rs.decode(fec_payload)[0]
                extracted_text = repaired_bytes.decode('utf-8')
                return extracted_text
            except reedsolo.ReedSolomonError:
                return None
        else:
            return None

    return None

def receive(buff: np.ndarray, temp_buff: np.ndarray, device: DeviceControl, baud_rate: int, sample_rate: int, rs: reedsolo.RSCodec, timeout: float, plot = None):
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
        result = process_burst(valid_buff, baud_rate, sample_rate, rs, plot)
        return result, elapsed
    