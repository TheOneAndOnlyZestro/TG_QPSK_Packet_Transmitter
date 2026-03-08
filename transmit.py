from device_control import DeviceControl
import numpy as np
import reedsolo
from modulation import modulation_methods
from config_loader import MODULATION_METHOD
def text_to_complex(text, baud_rate: int, rs: reedsolo.RSCodec):
    # 1. Encode text to bytes, then apply Reed-Solomon FEC
    raw_bytes = text.encode('utf-8')
    fec_payload = list(rs.encode(raw_bytes)) 
    
    # 2. Add plaintext headers/footers for simple syncing
    start_bytes = list(b"[START]")
    end_bytes = list(b"[END]")
    full_frame = start_bytes + fec_payload + end_bytes
    bits = ''.join(format(b, '08b') for b in full_frame)

    mod, _ = modulation_methods[MODULATION_METHOD]

    return mod(bits, baud_rate)

def transmit(payload_string: str, device: DeviceControl, padding, rs: reedsolo.RSCodec, baud_rate: int):
    iq_samples = text_to_complex(payload_string, baud_rate ,rs)

    full_burst = np.concatenate((padding, iq_samples, padding))
    mtu = device.getMTU()
            
    for i in range(0, len(full_burst), mtu):
        chunk = full_burst[i:i+mtu]
        device.write(chunk, len(chunk))

    print(f"[HARDWARE] {MODULATION_METHOD} Burst sent. ({len(iq_samples)} baseband samples via Refactored Module)")