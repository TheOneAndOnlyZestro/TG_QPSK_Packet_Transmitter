import configparser
import os
import sys

config = configparser.ConfigParser()
conf_file = 'radio.conf'

if not os.path.exists(conf_file):
    print(f"[ERROR] '{conf_file}' not found.")
    sys.exit(1)

config.read(conf_file)

# Hardware
RX_SERIAL = config['Hardware']['rx_serial']
TX_SERIAL = config['Hardware']['tx_serial']

# RF
FREQ = float(config['RF_Settings']['frequency'])
SAMP_RATE = int(config['RF_Settings']['sample_rate'])
SAMPLES_PER_SYMBOL = int(config['RF_Settings']['samples_per_symbol'])
CAPTURE_SECONDS = float(config['RF_Settings']['capture_seconds'])
TX_GAIN = int(config['RF_Settings']['tx_gain'])
RX_GAIN = float(config['RF_Settings']['rx_gain'])
CHUNK_SIZE = int(config['RF_Settings']['chunk_size'])
TIMEOUT = float(config['RF_Settings']['timeout'])
MAX_RESEND = float(config['RF_Settings']['max_resend'])