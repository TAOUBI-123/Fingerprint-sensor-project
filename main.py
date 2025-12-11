from machine import Pin, SoftI2C
import time
import ssd1306
import fingerprint

# --- HARDWARE CONFIGURATION ---
# LED: GPIO 4
led_green = Pin(4, Pin.OUT)
# LED Red: GPIO 5
led_red = Pin(5, Pin.OUT)
led_red.value(0)
# PIR Sensor: GPIO 2
pir = Pin(2, Pin.IN)
# Boot Button: GPIO 0 (Used for entering Setup Mode)
setup_button = Pin(0, Pin.IN, Pin.PULL_UP)

# I2C OLED Display (SDA=21, SCL=22)
i2c = SoftI2C(scl=Pin(22), sda=Pin(21), freq=100000)
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# UART Fingerprint Sensor (TX=17, RX=16)
fp = fingerprint.Fingerprint(uart_id=2, tx=17, rx=16)

# --- HELPER FUNCTIONS ---
def msg(line1, line2=""):
    # Clears screen and displays text with wrapping
    oled.fill(0)
    y = 0
    for i, content in enumerate([str(line1), str(line2)]):
        # Force line 2 to start in the blue section (y=16)
        if i == 1 and y < 16:
            y = 16
        while len(content) > 0:
            if y + 8 > 64: break
            chunk = content[:16]
            content = content[16:]
            oled.text(chunk, 0, y)
            y += 10
            # Avoid printing across the yellow/blue boundary
            if y > 0 and y < 16:
                y = 16
    oled.show()

def enroll_master_finger():
    print(">> STARTING ENROLLMENT...")
    msg("SETUP MODE", "Place New Finger")
    
    # 1. Capture First Image
    start_t = time.ticks_ms()
    while not fp.get_image():
        if time.ticks_diff(time.ticks_ms(), start_t) > 10000: # 10s Timeout
            msg("Timeout", "Try Again")
            return
        time.sleep(0.01)
        
    if not fp.image2tz(1):
        msg("Error", "Bad Image")
        print(">> Error: Failed to convert image 1")
        return
        
    msg("Remove Finger", "...")
    print(">> First image taken. Remove finger.")
    
    # Wait for finger to be
    start_rem = time.ticks_ms()
    while fp.get_image():
        if time.ticks_diff(time.ticks_ms(), start_rem) > 5000: # 5s Timeout
            msg("Timeout", "Remove Finger")
            return
        time.sleep(0.01)
    time.sleep(2)
    
    # 2. Capture Second Image (Verification)
    msg("Place Same", "Finger Again")
    start_t = time.ticks_ms()
    while not fp.get_image():
        if time.ticks_diff(time.ticks_ms(), start_t) > 10000: # 10s Timeout
            msg("Timeout", "Try Again")
            return
        time.sleep(0.01)
        
    if not fp.image2tz(2):
        msg("Error", "Bad Image")
        print(">> Error: Failed to convert image 2")
        return
        
    print(">> Second image taken.")
    
    # 3. Create Model & Save as ID #1
    if fp.reg_model():
        if fp.store(1, 1):
            msg("SUCCESS!", "ID #1 Saved")
            print(">> SUCCESS: Fingerprint saved as ID #1.")
            # Blink LED to confirm
            for _ in range(3): 
                led_green.value(1); time.sleep(0.02); led_green.value(0); time.sleep(0.02)
        else:
            msg("Error", "Save Failed")
    else:
        msg("Error", "No Match")
        print(">> ERROR: Fingerprints did not match.")

# --- STARTUP SEQUENCE ---
msg("System Booting", "Hold BOOT for Setup")
msg("System Booting", "Click BOOT for Setup")

# Poll for setup button press for 2 seconds
in_setup_mode = False
start_time = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start_time) < 2000:
    if setup_button.value() == 0:
        in_setup_mode = True
        break
    time.sleep_ms(20) # Small delay to prevent busy-waiting

# Check if user wants to enter Setup Mode
if in_setup_mode:
    msg("PASSWORD REQUIRED", "Check Terminal ->")
    print("\n--------------------------------")
    print("--- ENTER SETUP PASSWORD ---")
    print("--------------------------------")
    # Add a delay to allow the serial monitor to connect
    time.sleep(1) 
    # Wait for user input in VS Code Terminal
    password = input("Password: ")
    
    if password == "aaaaaa":
        print(">> Password Accepted.")
        msg("ACCESS GRANTED", "Wiping DB...")
        fp.empty_db() # Clear old data
        time.sleep(1)
        enroll_master_finger() # Start enrollment
    else:
        msg("ACCESS DENIED", "Wrong Password")
        print(">> WRONG PASSWORD.")
        time.sleep(2)
else:
    print(">> Normal Startup.")

msg("SYSTEM ARMED", "Waiting for Motion")
fp.led_control(False) # Ensure LED is off (Sleep Mode)

# --- MAIN SECURITY LOOP ---
while True:
    if pir.value() == 1:
        print(">> Motion Detected!")
        msg("MOTION DETECTED", "Scan ID #1...")
        fp.led_control(True) # Wake up sensor LED
        
        start_scan = time.ticks_ms()
        access = False
        
        # Wait 10 seconds for user to scan finger
        while time.ticks_diff(time.ticks_ms(), start_scan) < 10000:
            if fp.get_image():
                if fp.image2tz(1) and fp.search():
                    # Match found!
                    msg("ACCESS GRANTED", "Welcome Master")
                    print(">> Unlock Successful.")
                    led_green.value(1) # Unlock (Green LED ON)
                    time.sleep(4)
                    led_green.value(0) # Lock
                    access = True
                    break
                else:
                    # Finger placed, but wrong one
                    msg("ACCESS DENIED", "Unknown Finger")
                    print(">> Intruder detected.")
                    led_red.value(1)
                    time.sleep(1)
                    led_red.value(0)
                    msg("MOTION DETECTED", "Scan ID #1...")
            time.sleep(0.01)
            
        if not access:
            msg("TIMEOUT", "System Locked")
            time.sleep(2)
            
        fp.led_control(False) # Turn LED off (Return to Sleep) _ still the light does not turn off
        msg("SYSTEM ARMED", "Waiting for Motion")
        
    time.sleep(0.1)