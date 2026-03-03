import SoapySDR
from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32, SOAPY_SDR_RX
import time
class DeviceControl:
    def __init__(self, device_serial: str ,transmitting: bool, sample_rate: int, freq: float, gain_tx: int, gain_rx: int):
        
        self.device_serial = device_serial
        self.transmitting = transmitting
        self.sample_rate = sample_rate
        self.freq = freq
        self.gain_tx = gain_tx
        self.gain_rx = gain_rx

        self.sdr = SoapySDR.Device(dict(driver="hackrf", serial=self.device_serial))
        self.sdr.setSampleRate(SOAPY_SDR_TX, 0, self.sample_rate)
        self.sdr.setFrequency(SOAPY_SDR_TX, 0, self.freq)
        self.sdr.setGain(SOAPY_SDR_TX, 0, self.gain_tx) 

        self.sdr.setSampleRate(SOAPY_SDR_RX, 0, self.sample_rate)
        self.sdr.setFrequency(SOAPY_SDR_RX, 0, self.freq)
        self.sdr.setGain(SOAPY_SDR_RX, 0, self.gain_rx) 
        #set to transmitting or receiving
        self.transmitting_stream = self.sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)
        self.receiving_stream = self.sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        
        if self.transmitting:
            self.sdr.activateStream(self.transmitting_stream)
        else:
            self.sdr.activateStream(self.receiving_stream)
    
    def getMTU(self):
        if self.transmitting:
            return self.sdr.getStreamMTU(self.transmitting_stream)
        else:
            return self.sdr.getStreamMTU(self.receiving_stream)
    
    def write(self, buff, length):
        if not self.transmitting:
            self.sdr.deactivateStream(self.receiving_stream)
            time.sleep(0.3)
            self.sdr.activateStream(self.transmitting_stream)
            self.transmitting = True

        self.sdr.writeStream(self.transmitting_stream,[buff], length)


    def read(self, buff, length):
        if self.transmitting:
            self.sdr.deactivateStream(self.transmitting_stream)
            time.sleep(0.3)
            self.sdr.activateStream(self.receiving_stream)
            self.transmitting = False

        return self.sdr.readStream(self.receiving_stream,[buff], length)

    def close(self):
        if self.transmitting:
            self.sdr.deactivateStream(self.transmitting_stream)
        else:
            self.sdr.deactivateStream(self.receiving_stream)

        self.sdr.closeStream(self.transmitting_stream)
        self.sdr.closeStream(self.receiving_stream)


