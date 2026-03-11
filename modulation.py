import numpy as np
from config_loader import MODULATION_METHOD

def qpsk_phase_to_bits(diff_syms: np.ndarray, start_bits: str, plot):
    """Pure phase-to-bit mapping. Shared by both single-carrier QPSK and OFDM."""
    bit_list =[]
    
    for dp in np.angle(diff_syms):
        if -np.pi/4 <= dp < np.pi/4:          bit_list.append('00')
        elif np.pi/4 <= dp < 3*np.pi/4:       bit_list.append('01')
        elif -3*np.pi/4 <= dp < -np.pi/4:     bit_list.append('10')
        else:                                 bit_list.append('11')
            
    bit_str = "".join(bit_list)

    print(f"[OFDM TEST BITS]: {bit_str}")
    idx = bit_str.find(start_bits)
    if idx != -1:
        return bit_str[idx + len(start_bits):]
    return None

def qpsk_constellation_decoder(syms: np.ndarray, start_bits: str):
    if len(syms) < 2: 
        return None
        
    diff_phases = np.angle(syms[1:] * np.conj(syms[:-1]))
    bit_list =[]
    for dp in diff_phases:
        if -np.pi/4 <= dp < np.pi/4:          bit_list.append('00')
        elif np.pi/4 <= dp < 3*np.pi/4:       bit_list.append('01')
        elif -3*np.pi/4 <= dp < -np.pi/4:     bit_list.append('10')
        else:                                 bit_list.append('11')
            
    bit_str = "".join(bit_list)
    idx = bit_str.find(start_bits)
    if idx != -1:
        return bit_str[idx + len(start_bits):]
    return None

def modulate_ofdm(bits: str, baud_rate: int):
    pass


def demodulate_ofdm(burst: np.ndarray, baud_rate: int, sample_rate: int, start_bits: str, plot: bool):
    pass

def modulate_qpsk(bits: str, baud_rate: int):
    phase_shifts = {'00': 0.0, '01': np.pi / 2, '11': np.pi, '10': -np.pi / 2}
    current_phase = 0.0
    iq_symbols =[np.exp(1j * current_phase) * 0.7] 
    
    for i in range(0, len(bits), 2):
        bit_pair = bits[i:i+2]
        current_phase += phase_shifts[bit_pair]
        iq_symbols.append(np.exp(1j * current_phase) * 0.7)
        
    iq_symbols = np.array(iq_symbols, dtype=np.complex64)
    return np.repeat(iq_symbols, int(baud_rate))

def demodulate_qpsk(complex_data: np.ndarray, baud_rate: int, sample_rate: int, start_bits: str, plot):
    # 1. Time-Domain Carrier Recovery
    N = len(complex_data)
    burst_4 = complex_data**4 
    fft_res = np.fft.fft(burst_4)
    fft_freqs = np.fft.fftfreq(N, d=1/sample_rate)
    
    peak_idx = np.argmax(np.abs(fft_res))
    f_offset = fft_freqs[peak_idx] / 4.0
    
    t = np.arange(N) / sample_rate
    derotated_burst = complex_data * np.exp(-1j * 2 * np.pi * f_offset * t)
    
    if plot is not None:
        fig, ax = plot

        if len(derotated_burst) > 80000:
            indices = np.random.choice(len(derotated_burst), size=60000, replace=False)
            iq_plot = derotated_burst[indices]
        else:
            iq_plot = derotated_burst

        ax[1].clear()
        #ax[0].scatter(iq_plot.real, iq_plot.imag, s=2, alpha=0.4)   # ← update here
        ax[1].scatter(iq_plot.real, iq_plot.imag, s=2, alpha=0.5, color='blue', edgecolors='none')
        ax[1].set_xlabel("In-phase (I)")
        ax[1].set_ylabel("Quadrature (Q)")
        ax[1].set_title("Signal After Modulation")
        ax[1].grid(True)

        ideal = np.array([1+1j, 1-1j, -1+1j, -1-1j]) / 0.7  # unit energ
        ax[1].scatter(ideal.real, ideal.imag, s=100, marker='x', color='red', label='Ideal')

    # 2. Offset brute-forcing
    for offset in range(baud_rate):
        syms = derotated_burst[offset :: baud_rate]
        # Call the abstracted decoder
        result = qpsk_constellation_decoder(syms, start_bits)
        if result: return result
            
    return None

def modulate_bpsk(bits: str, baud_rate: int):
    phase_shifts = {'0':0.0, '1': np.pi}
    current_phase = 0.0
    iq_symbols =[np.exp(1j * current_phase)] 
    for b in bits:
        current_phase += phase_shifts[b]
        iq_symbols.append(np.exp(1j * current_phase))
    return np.repeat(np.array(iq_symbols, dtype=np.complex64), baud_rate)

def demodulate_bpsk(complex_data: np.ndarray, baud_rate: int, sample_rate: int, start_bits: str, plot):
    # 1. Coarse CFO Estimation for BPSK (2nd power)
    N = len(complex_data)
    burst_2 = complex_data ** 2
    fft_res = np.fft.fft(burst_2)
    fft_freqs = np.fft.fftfreq(N, d=1/sample_rate)
    
    peak_idx = np.argmax(np.abs(fft_res))
    f_offset = fft_freqs[peak_idx] / 2.0  # Divide by 2 for BPSK
    
    t = np.arange(N) / sample_rate
    derotated_burst = complex_data * np.exp(-1j * 2 * np.pi * f_offset * t)
    
    # Plot the corrected constellation
    if plot is not None:
        fig, ax = plot
        if len(derotated_burst) > 80000:
            indices = np.random.choice(len(derotated_burst), size=60000, replace=False)
            iq_plot = derotated_burst[indices]
        else:
            iq_plot = derotated_burst
        ax[1].clear()
        ax[1].scatter(iq_plot.real, iq_plot.imag, s=2, alpha=0.5, color='blue', edgecolors='none')
        ax[1].set_xlabel("In-phase (I)")
        ax[1].set_ylabel("Quadrature (Q)")
        ax[1].set_title("Signal After Demodulation")
        ax[1].grid(True)
        ideal = np.array([1+0j, -1+0j])  # BPSK ideals on real axis
        ax[1].scatter(ideal.real, ideal.imag, s=100, marker='x', color='red', label='Ideal')

    # 3. Brute-force timing offset and decode
    for offset in range(baud_rate):  # baud_rate = samples_per_symbol
        syms = derotated_burst[offset::baud_rate]
        if len(syms) < len(start_bits):  # Too few symbols
            continue
        
        # Differential decoding for DBPSK (1 bit per symbol)
        # Compute phase differences via conjugate multiply
        diffs = syms[1:] * np.conj(syms[:-1])
        bits = np.where(np.real(diffs) > 0, '0', '1')  # >0: no flip ('0'), <0: flip ('1')
        
        # Handle 180° ambiguity: try normal and inverted
        for invert in [False, True]:
            if invert:
                current_bits = np.where(bits == '0', '1', '0')  # Flip all bits
            else:
                current_bits = bits
            
            bit_string = ''.join(current_bits)
            
            # Search for start_bits in the stream
            start_idx = bit_string.find(start_bits)
            if start_idx != -1:
                # Found preamble; extract payload bits after it
                payload_start = start_idx + len(start_bits)
                return bit_string[payload_start:]  # Return raw payload bits for further processing
    
    return None

modulation_methods = {
    'QPSK': (modulate_qpsk, demodulate_qpsk),
    'BPSK': (modulate_bpsk, demodulate_bpsk),
    'OFDM': (modulate_ofdm, demodulate_ofdm)
}