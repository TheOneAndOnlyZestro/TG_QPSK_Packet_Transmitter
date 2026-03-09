import numpy as np
from config_loader import MODULATION_METHOD
# =======================================================
# ABSTRACTION HELPERS 
# =======================================================
def qpsk_phase_to_bits(diff_syms: np.ndarray, start_bits: str):
    """Pure phase-to-bit mapping. Shared by both single-carrier QPSK and OFDM."""
    bit_list =[]
    for dp in np.angle(diff_syms):
        if -np.pi/4 <= dp < np.pi/4:          bit_list.append('00')
        elif np.pi/4 <= dp < 3*np.pi/4:       bit_list.append('01')
        elif -3*np.pi/4 <= dp < -np.pi/4:     bit_list.append('10')
        else:                                 bit_list.append('11')
            
    bit_str = "".join(bit_list)
    idx = bit_str.find(start_bits)
    if idx != -1:
        return bit_str[idx + len(start_bits):]
    return None

# def qpsk_constellation_decoder(syms: np.ndarray, start_bits: str):
#     """Legacy decoder for single-carrier QPSK."""
#     if len(syms) < 2: 
#         return None
#     # Calculate difference between adjacent time symbols
#     diff_syms = syms[1:] * np.conj(syms[:-1])
#     return qpsk_phase_to_bits(diff_syms, start_bits)

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
# =======================================================
# NEW OFDM IMPLEMENTATION (Fixed Guard Bands & 2D Math)
# =======================================================
def modulate_ofdm(bits: str, baud_rate: int):
    n_subcarriers = 64
    cp_len = 16
    
    # 1. Guard Bands: Leave edges empty to survive HackRF analog filters!
    # DC is at 32. We use 16..31 and 33..48 for data (32 active carriers total).
    pilot_positions = list(range(0, 16)) +[32] + list(range(49, 64))
    data_rows = np.setdiff1d(np.arange(n_subcarriers), pilot_positions)
    n_data_subc = len(data_rows) # Exactly 32

    # 2. Map bits to absolute phases
    phase_shifts = {'00': 1+0j, '01': 0+1j, '11': -1+0j, '10': 0-1j}
    if len(bits) % 2 != 0: 
        bits += '0'
        
    data_symbols = np.array([phase_shifts.get(bits[i:i+2], 1+0j) for i in range(0, len(bits), 2)], dtype=complex)

    # Pad with 1+0j so it perfectly fills the last OFDM block
    remainder = len(data_symbols) % n_data_subc
    if remainder != 0:
        data_symbols = np.concatenate([data_symbols, np.ones(n_data_subc - remainder, dtype=complex)])

    # +1 extra symbol at the start for the Differential Reference
    n_ofdm_symbols = (len(data_symbols) // n_data_subc) + 1
    grid = np.zeros((n_subcarriers, n_ofdm_symbols), dtype=complex)

    # 3. Populate Grid (Column by Column to preserve byte sequence)
    # The first column (sym 0) is left as 1+0j reference on active carriers
    grid[data_rows, 0] = 1+0j
    
    data_iter = iter(data_symbols)
    for sym in range(1, n_ofdm_symbols):
        for k in data_rows:
            grid[k, sym] = next(data_iter)

    # 4. CRITICAL: 2D Differential Encoding across Time (Axis=1)
    for sym in range(1, n_ofdm_symbols):
        grid[:, sym] = grid[:, sym] * grid[:, sym-1]

    # 5. IFFT and Cyclic Prefix
    ofdm_time = np.fft.ifft(np.fft.ifftshift(grid, axes=0), axis=0) * np.sqrt(n_subcarriers)
    ofdm_w_cp = np.concatenate([ofdm_time[-cp_len:, :], ofdm_time], axis=0)
    ofdm_cp = ofdm_w_cp.flatten(order='F') 
    
    return ofdm_cp.astype(np.complex64)


def demodulate_ofdm(burst: np.ndarray, baud_rate: int, sample_rate: int, start_bits: str):
    n_subcarriers = 64
    cp_len = 16
    sym_len = n_subcarriers + cp_len
    
    pilot_positions = list(range(0, 16)) + [32] + list(range(49, 64))
    data_rows = np.setdiff1d(np.arange(n_subcarriers), pilot_positions)

    # Sweep window to find exact sync alignment
    step_size = max(1, cp_len // 4)
    for offset in range(0, sym_len, step_size):
        rx_stream = burst[offset:]
        n_symbols = len(rx_stream) // sym_len
        
        if n_symbols < 2:
            continue
            
        # 1. Reshape and 2D FFT
        rx_stream_trimmed = rx_stream[:n_symbols * sym_len]
        rx_mat = rx_stream_trimmed.reshape(n_symbols, sym_len).T   
        rx_no_cp = rx_mat[cp_len:, :]  
        grid_rx = np.fft.fftshift(np.fft.fft(rx_no_cp, axis=0) / np.sqrt(n_subcarriers), axes=0)

        # 2. CRITICAL: 2D Differential Decoding across Time!
        # This compares Sym 1 against Sym 0, isolating the phase shift per frequency
        diff_grid = grid_rx[:, 1:] * np.conj(grid_rx[:, :-1])

        # 3. Extract active carriers and flatten Column-Major ('F')
        # This perfectly restores the sequence of bytes exactly how the transmitter packed them
        data_sym_2d = diff_grid[data_rows, :]
        diff_syms_1d = data_sym_2d.flatten(order='F')

        # 4. Phase mapping
        result = qpsk_phase_to_bits(diff_syms_1d, start_bits)
        if result:
            return result
            
    return None

# =======================================================
# YOUR ORIGINAL QPSK & BPSK FUNCTIONS (Untouched Logic)
# =======================================================
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

        ideal = np.array([1+1j, 1-1j, -1+1j, -1-1j]) / np.sqrt(2)  # unit energ
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
    iq_symbols =[np.exp(1j * current_phase) * 0.7] 
    for b in bits:
        current_phase += phase_shifts[b]
        iq_symbols.append(np.exp(1j * current_phase) * 0.7)
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
    
    # 2. Auto-rotate to align signal to real axis (handle 90° offsets)
    # Compute variance on real vs imag to detect axis
    var_real = np.var(derotated_burst.real)
    var_imag = np.var(derotated_burst.imag)
    if var_imag > var_real:
        derotated_burst *= 1j  # Rotate 90° to move to real axis
    
    # Optional: Fine phase correction (average angle of high-amplitude samples)
    high_amp_idx = np.abs(derotated_burst) > 0.3 * np.max(np.abs(derotated_burst))  # Threshold
    residual_phase = np.mean(np.angle(derotated_burst[high_amp_idx]))
    derotated_burst *= np.exp(-1j * residual_phase)
    
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

# =======================================================
# CONFIG DICTIONARY
# =======================================================
modulation_methods = {
    'QPSK': (modulate_qpsk, demodulate_qpsk),
    'BPSK': (modulate_bpsk, demodulate_bpsk),
    'OFDM': (modulate_ofdm, demodulate_ofdm)
}