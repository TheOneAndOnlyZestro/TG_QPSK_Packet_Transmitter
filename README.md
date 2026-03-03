# QPSK Packet Transmitter & Receiver System (HackRF One)

A full-stack software-defined radio (SDR) solution for transmitting text and binary files over the air using **QPSK (Quadrature Phase Shift Keying)** modulation. This project implements a **FastAPI** backend to handle transmission requests and a standalone Python receiver script that performs real-time demodulation, error correction, and file reassembly.

## 📡 Project Overview

This system turns two HackRF One devices into a digital data link. It overcomes the challenges of RF noise and interference by implementing **Reed-Solomon Forward Error Correction (FEC)** and robust packet framing.

* **Transmitter:** Exposes a REST API to accept data. It chunks large files (like images), applies FEC, modulates the data into baseband IQ samples, and streams them to the HackRF.
* **Receiver:** Continuously monitors the spectrum for QPSK bursts. It performs carrier recovery, symbol timing synchronization, demodulates the signal, corrects bit errors, and reassembles the file chunks back into their original format (e.g., `.jpg`, `.png`).

## ✨ Features

* **REST API Control:** Queue messages and files for transmission via simple HTTP POST requests.
* **Robust QPSK/DQPSK Modulation:** Uses Differential QPSK to handle phase ambiguity inherent in wireless transmission.
* **Reed-Solomon FEC:** Integrates `reedsolo` to detect and repair corrupted bytes automatically, ensuring data integrity even in noisy environments.
* **Automatic File Chunking:** Large files are automatically split into manageable packets and reassembled by the receiver using unique Block IDs.
* **Real-Time Demodulation:** Custom DSP logic performs signal detection (energy threshold), carrier frequency offset correction, and symbol timing recovery in Python.
* **Image Handling:** dedicated handlers in `data_handling.py` automatically save received `base64` payloads as valid JPEG or PNG images.

## 🛠️ Prerequisites

### Hardware

* 2x **HackRF One** Software Defined Radios.
* 2x Antennas (tuned to **1.2 GHz** or the frequency configured in the code).
* USB cables for PC connection.

### Software

* **Python 3.10+**
* **HackRF Host Tools** (Drivers and `hackrf_info` utility).
* **SoapySDR** (and the SoapySDR Python bindings).

## 📦 Installation

1. **Clone the Repository**
```bash
git clone https://github.com/yourusername/qpsk-transmitter.git
cd qpsk-transmitter

```


2. **Set Up a Virtual Environment**
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

```


3. **Install Python Dependencies**
Create a `requirements.txt` with the following content, or install directly:
```bash
pip install fastapi uvicorn numpy reedsolo python-multipart python-Levenshtein SoapySDR

```


*(Note: You must have the underlying SoapySDR system libraries installed on your OS for the Python wrapper to work.)*

## ⚙️ Configuration

Before running the system, you **must** configure the Serial Numbers of your specific HackRF devices.

1. Plug in your HackRFs and run:
```bash
hackrf_info

```


Copy the `Serial number` for both devices.
2. **Configure Transmitter:**
Open `tx_qpsk_api.py` and update the `TX_SERIAL` variable:
```python
TX_SERIAL = "YOUR_TX_DEVICE_SERIAL_HERE"

```


3. **Configure Receiver:**
Open `rx_qpsk.py` and update the `RX_SERIAL` variable:
```python
RX_SERIAL = "YOUR_RX_DEVICE_SERIAL_HERE"

```



## 🚀 Usage Instructions

### Step 1: Start the Receiver

Open a terminal and run the receiver script. It will begin listening for signals on 1.2 GHz.

```bash
python rx_qpsk.py

```

*Output: `[START] Listening continuously for QPSK on 1.2 GHz...*`

### Step 2: Start the Transmitter API

Open a **new** terminal window and launch the FastAPI server.

```bash
uvicorn main:app --reload

```

*Output: `[API] Starting hardware transmitter thread...*`

### Step 3: Send Data

You can now send data using `curl` or by visiting the interactive API docs at `http://127.0.0.1:8000/docs`.

#### Send a Text Message

```bash
curl -X POST "http://127.0.0.1:8000/send_text" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "message=Hello HackRF World"

```

#### Send an Image File

```bash
curl -X POST "http://127.0.0.1:8000/send_file" \
     -F "file=@/path/to/your/image.jpg"

```

The receiver terminal should show logs indicating packet detection (`[SUCCESS] FEC passed`), and eventually:
`[ASSEMBLY] File 'image.jpg' complete! ... [SUCCESS] JPG image saved.`

## 📂 File Structure

```text
.
├── main.py                # FastAPI entry point & API routes
├── tx_qpsk_api.py         # Hardware interface & Threaded Transmission Queue
├── transmit.py            # QPSK Modulation logic & Packet framing
├── device_control.py      # Object-Oriented wrapper for SoapySDR
├── rx_qpsk.py             # CORE RECEIVER: Demodulation, FEC, & Reassembly
├── data_handling.py       # Helper functions to save received images
├── output.txt             # Log of received text payloads
└── rollback/              # [DEPRECATED] Legacy/Archive code
    ├── rx_ant_file.py     # Old FSK demodulation test
    ├── tx_cont.py         # Continuous transmission test
    └── ...                # Other experimental scripts

```

> **Note:** The `rollback/` directory contains experimental scripts and previous modulation attempts (like OOK/FSK). The core QPSK logic resides in the root directory.

## 🔧 Troubleshooting

* **`[ERROR] Failed to connect to HackRF` / Device not found:**
* Ensure your HackRF is plugged in.
* Verify the `TX_SERIAL` and `RX_SERIAL` in the code match `hackrf_info`.
* Ensure no other software (like SDR# or GQRX) is claiming the device.


* **High Packet Loss / CRC Errors:**
* **Gain Settings:** RF environments vary. Adjust `gain_tx` in `tx_qpsk_api.py` (default 40) or `device.setGain` in `rx_qpsk.py` (default 60/40).
* **Distance:** Move antennas closer for testing.
* **Interference:** 1.2 GHz can be crowded. Try changing `FREQ` in both `tx_qpsk_api.py` and `rx_qpsk.py` to a cleaner frequency (e.g., 900 MHz or 2.4 GHz, depending on antenna rating).


* **"SoapySDR module not found":**
* Ensure you have installed the Python bindings. On Ubuntu/Debian: `sudo apt install python3-soapysdr`. On other systems, you may need to build SoapySDR from source or use a specific `pip` package depending on your OS.
