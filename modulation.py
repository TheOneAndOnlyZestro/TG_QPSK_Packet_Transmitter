import numpy as np
def modulate_qpsk(bits: str, baud_rate: int):
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
    return np.repeat(iq_symbols, int(baud_rate))

def demodulate_qpsk(complex: np.ndarray, baud_rate: int, sample_rate: int, start_bits: str):
     # 2. Carrier Recovery (Correct HackRF internal clock frequency drift)
    # Raising a QPSK signal to the 4th power removes the phase modulation, 
    # leaving only a massive spike at 4x the frequency offset!
    N = len(complex)
    burst_4 = complex**4 
    fft_res = np.fft.fft(burst_4)
    fft_freqs = np.fft.fftfreq(N, d=1/sample_rate)
    
    peak_idx = np.argmax(np.abs(fft_res))
    f_offset = fft_freqs[peak_idx] / 4.0
    
    # Derotate the complex to bring it perfectly back to 0 Hz baseband
    t = np.arange(N) / sample_rate
    derotated_burst = complex * np.exp(-1j * 2 * np.pi * f_offset * t)
    
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
            return bit_str[idx + len(start_bits):]
        return None
    
def demodulate_bpsk(complex: np.ndarray, baud_rate: int, sample_rate: int, start_bits: str):
    # Carrier Recovery (M=2 for BPSK)
    N = len(complex)
    burst_2 = complex**2 
    fft_res = np.fft.fft(burst_2)
    fft_freqs = np.fft.fftfreq(N, d=1/sample_rate)
    
    f_offset = fft_freqs[np.argmax(np.abs(fft_res))] / 2.0
    t = np.arange(N) / sample_rate
    derotated = complex * np.exp(-1j * 2 * np.pi * f_offset * t)

    for offset in range(baud_rate):
        syms = derotated[offset :: baud_rate]
        if len(syms) < 2: continue
            
        diff_phases = np.angle(syms[1:] * np.conj(syms[:-1]))
        
        bit_list =[]
        for dp in diff_phases:
            # DBPSK maps -90 to +90 as '0', and outside as '1'
            if -np.pi/2 <= dp < np.pi/2: bit_list.append('0')
            else:                        bit_list.append('1')
                
        bit_str = "".join(bit_list)
        idx = bit_str.find(start_bits)
        if idx != -1:
             return bit_str[idx + len(start_bits):]
             
    return None
def modulate_bpsk(bits: str, baud_rate: int):
    phase_shifts = {
        '0':0.0,
        '1' : np.pi
    }
    
    current_phase = 0.0
    iq_symbols =[]
    
    # Add a starting dummy symbol
    iq_symbols.append(np.exp(1j * current_phase) * 0.7) 
    
    # Map bits to phase changes, two at a time
    for b in bits:
        current_phase += phase_shifts[b]
        iq_symbols.append(np.exp(1j * current_phase) * 0.7)
        
    iq_symbols = np.array(iq_symbols, dtype=np.complex64)
    iq_data = np.repeat(iq_symbols, baud_rate)
    return iq_data

modulation_methods ={
    'QPSK': (modulate_qpsk, demodulate_qpsk),
    'BPSK' : (modulate_bpsk, demodulate_bpsk)
}

