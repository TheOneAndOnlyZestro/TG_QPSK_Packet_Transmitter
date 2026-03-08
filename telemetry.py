import time
from datetime import datetime

class Telemtry:
    def __init__(self, log_filename="telemetry.log"):
        self.session_start = time.time()
        self.total_attempts = 0
        self.successful_deliveries = 0
        self.total_payload_bytes = 0
        self.rtt_list =[]
        self.log_filename = log_filename
        
        # Add a session start marker to the log file
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(f"\n\n{'='*50}\n")
            f.write(f"🚀 NEW SESSION STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*50}\n")

    def log_attempt(self):
        self.total_attempts += 1

    def log_success(self, payload_bytes: int, rtt: float):
        self.successful_deliveries += 1
        self.total_payload_bytes += payload_bytes
        self.rtt_list.append(rtt)

    def write_report(self):
        if self.total_attempts == 0:
            return

        elapsed = time.time() - self.session_start
        drops = self.total_attempts - self.successful_deliveries
        pdr = (drops / self.total_attempts) * 100
        goodput_bps = (self.total_payload_bytes * 8) / elapsed if elapsed > 0 else 0
        avg_rtt = sum(self.rtt_list) / len(self.rtt_list) if self.rtt_list else 0

        # Create the detailed multi-line string for the log file
        report = (
            f"[{datetime.now().strftime('%H:%M:%S')}] TELEMETRY REPORT |\n"
            f"  -> Elapsed Time : {elapsed:.2f} s\n"
            f"  -> Total Bytes  : {self.total_payload_bytes} B\n"
            f"  -> Goodput      : {goodput_bps:.2f} bps ({goodput_bps/1000:.2f} kbps)\n"
            f"  -> TX Attempts  : {self.total_attempts}\n"
            f"  -> Packet Drops : {drops} ({pdr:.1f}% Drop Rate)\n"
            f"  -> Average RTT  : {avg_rtt:.2f} sec/packet\n"
            f"{'-'*50}\n"
        )

        # Append to the text file
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(report)
            
        # Print a tiny, clean summary to the busy console
        print(f"[TELEMETRY] Log saved -> Goodput: {goodput_bps/1000:.2f} kbps | PDR: {pdr:.1f}% | RTT: {avg_rtt:.2f}s")


