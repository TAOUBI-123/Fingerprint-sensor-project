import time
from machine import UART

class Fingerprint:
    def __init__(self, uart_id=2, tx=17, rx=16):
        # Initialize UART connection to sensor
        self.uart = UART(uart_id, baudrate=57600, tx=tx, rx=rx)
        self.password = 0x00000000
        self.address = 0xFFFFFFFF
    
    def send_packet(self, cmd, data=None):
        if data is None:
            data = []
        # Flush RX buffer to ensure we don't read old data
        while self.uart.any():
            self.uart.read()
            
        # Construct and send data packet to sensor
        packet = bytearray(12 + len(data))
        packet[0:2] = b'\xEF\x01' # Header
        packet[2:6] = self.address.to_bytes(4, 'big')
        packet[6] = 0x01 # Command packet
        packet[7:9] = (len(data) + 3).to_bytes(2, 'big') # Length (cmd + data + checksum)
        packet[9] = cmd
        if data:
            packet[10:10+len(data)] = bytes(data)
        checksum = (0x01 + (len(data) + 3) + cmd + sum(data)) & 0xFFFF
        packet[-2:] = checksum.to_bytes(2, 'big')
        self.uart.write(packet)

    def read_packet(self):
        # Read response from sensor
        start_time = time.ticks_ms()
        while self.uart.any() < 9:
            if time.ticks_diff(time.ticks_ms(), start_time) > 2000: # 2s timeout
                return None
            time.sleep(0.002)
            
        header = self.uart.read(2)
        if header != b'\xEF\x01': return None
        addr = self.uart.read(4)
        pid = self.uart.read(1)[0]
        length = int.from_bytes(self.uart.read(2), 'big')
        
        # Wait for the full payload to arrive
        while self.uart.any() < length:
            if time.ticks_diff(time.ticks_ms(), start_time) > 2000: return None
            time.sleep(0.002)
            
        content = self.uart.read(length)
        return content[0] # Return confirmation code (0x00 = Success)

    def verify_password(self):
        self.send_packet(0x13, self.password.to_bytes(4, 'big'))
        return self.read_packet() == 0x00

    def get_image(self):
        self.send_packet(0x01) # Command to take image
        return self.read_packet() == 0x00

    def image2tz(self, buffer_id=1):
        # Convert image to character file in buffer_id
        self.send_packet(0x02, [buffer_id])
        return self.read_packet() == 0x00

    def search(self):
        # Search the database for the finger in buffer 1
        self.send_packet(0x04, [0x01, 0x00, 0x00, 0x00, 0xA3]) 
        return self.read_packet() == 0x00

    def reg_model(self):
        # Combine character files from Buffer 1 and 2
        self.send_packet(0x05)
        return self.read_packet() == 0x00

    def store(self, buffer_id, page_id):
        # Store the template at specific ID location
        data = [buffer_id, (page_id >> 8) & 0xFF, page_id & 0xFF]
        self.send_packet(0x06, data)
        return self.read_packet() == 0x00

    def empty_db(self):
        # Wipe all fingerprints
        self.send_packet(0x0D)
        return self.read_packet() == 0x00

    def led_control(self, on=True):#this part of code turns on/off the led
        # Control LED: 0x50 command, data 1=on, 0=off
        self.send_packet(0x50, [0x01 if on else 0x00])
        return self.read_packet() == 0x00