from device_control import DeviceControl
import numpy as np
import reedsolo
def _text_to_dqpsk(text, baud_rate: int, rs: reedsolo.RSCodec):
    # 1. Encode text to bytes, then apply Reed-Solomon FEC
    raw_bytes = text.encode('utf-8')
    fec_payload = list(rs.encode(raw_bytes)) 
    
    # 2. Add plaintext headers/footers for simple syncing
    start_bytes = list(b"[START]")
    end_bytes = list(b"[END]")
    full_frame = start_bytes + fec_payload + end_bytes
    
    # 3. Convert to 8-bit binary string
    bits = ''.join(format(b, '08b') for b in full_frame)

    phase_shifts = {
        '00': 0.0,
        '01': np.pi / 2,
        '11': np.pi,
        '10': -np.pi / 2
    }
    
    current_phase = 0.0
    iq_symbols =[]
    
    # Add a starting dummy symbol
    iq_symbols.append(np.exp(1j * current_phase) * 0.7) 
    
    # Map bits to phase changes, two at a time
    for i in range(0, len(bits), 2):
        bit_pair = bits[i:i+2]
        current_phase += phase_shifts[bit_pair]
        iq_symbols.append(np.exp(1j * current_phase) * 0.7)
        
    iq_symbols = np.array(iq_symbols, dtype=np.complex64)
    iq_data = np.repeat(iq_symbols, baud_rate)
    return iq_data

def transmit(payload_string: str, device: DeviceControl, padding, rs: reedsolo.RSCodec, baud_rate: int):
    iq_samples = _text_to_dqpsk(payload_string, baud_rate ,rs)

    full_burst = np.concatenate((padding, iq_samples, padding))
    mtu = device.getMTU()
            
    for i in range(0, len(full_burst), mtu):
        chunk = full_burst[i:i+mtu]
        device.write(chunk, len(chunk))

    print(f"[HARDWARE] DQPSK Burst sent. ({len(iq_samples)} baseband samples via Refactored Module)")