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
    iq_data = np.repeat(iq_symbols, baud_rate)
    return iq_data

def demodulate_qpsk(complex: np.ndarray, baud_rate: int, sample_rate: int):
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

    # 3. Symbol Timing & Phase Decoding
    start_bits = ''.join(format(ord(i), '08b') for i in "[START]")
    
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
            pass

def demodulate_bpsk():
    pass
def modulate_bpsk(bits: str, baud_rate: int):
    pass
modulation_methods ={
    'QPSK': (modulate_qpsk, demodulate_qpsk),
    'BPSK' : (modulate_bpsk, demodulate_bpsk)
}

