from machine import Pin, SoftI2C, unique_id, PWM
import time, network, ubinascii, sys, ntptime, ujson, gc, machine

# Fix for missing 'ussl' module in newer MicroPython versions
try:
    import ussl
except ImportError:
    import ssl
    sys.modules['ussl'] = ssl
import lib.ssd1306 as ssd1306
import lib.fingerprint as fingerprint
from lib.mqtt import MQTTClient # Requires mqtt.py file
from config import secrets  

# --- CONFIGURATION (Loaded from secrets.py) ---
MQTT_TOPIC = "abdel_project_9Xs9/security/alerts"
TOPIC_DETECTION = "abdel_project_9Xs9/security/detection"
TOPIC_ACCESS = "abdel_project_9Xs9/security/access"
TOPIC_COMMANDS = "abdel_project_9Xs9/security/commands"
TOPIC_DOOR_STATUS = "abdel_project_9Xs9/security/door"

# --- HARDWARE CONFIGURATION ---
led_green = Pin(4, Pin.OUT)
led_red = Pin(5, Pin.OUT)
led_red.value(0)
led_yellow = Pin(18, Pin.OUT)
led_yellow.value(0)
pir = Pin(2, Pin.IN)
setup_button = Pin(0, Pin.IN, Pin.PULL_UP)

buzzer = PWM(Pin(23))
buzzer.duty(0) # Start silent

time.sleep(1) # Wait for power to stabilize on boot

# I2C OLED Display (SDA=21, SCL=22)
i2c = SoftI2C(scl=Pin(22), sda=Pin(21), freq=100000)

print("Scanning I2C bus...")
devices = i2c.scan()
if devices:
    print("I2C devices found:", [hex(d) for d in devices])
else:
    print("No I2C devices found! Check wiring.")

try:
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
except OSError as e:
    print("OLED init failed. Using dummy display.", e)
    class DummyOLED:
        def fill(self, c): pass
        def text(self, s, x, y, c=1): pass
        def show(self): pass
    oled = DummyOLED()

# UART Fingerprint Sensor (TX=17, RX=16)
fp = fingerprint.Fingerprint(uart_id=2, tx=17, rx=16)
# Ensure sensor LED is OFF immediately after initialization
try: fp.led_control(False)
except: pass

# --- NETWORK FUNCTIONS ---
client = None
panic_mode = False

def mqtt_callback(topic, msg_in):
    global panic_mode
    print(f">> MQTT Command: {topic} -> {msg_in}")
    
    try:
        payload = ujson.loads(msg_in)
        message = payload.get("cmd")
        ts = payload.get("ts")
        # Validate Timestamp (30s window). ESP32 Epoch (2000) + 946684800 = Unix Epoch (1970)
        if not ts or abs((time.time() + 946684800) - int(ts)) > 30:
            print(">> REJECTED: Invalid Timestamp or Replay Detected")
            return
    except:
        print(">> REJECTED: Invalid JSON Format")
        return
    
    if message == "OPEN_DOOR":
        print(">> Remote Unlock")
        msg("Remote Access", "Unlocked")
        send_alert("OPEN", TOPIC_DOOR_STATUS)
        # Success Tone
        buzzer.freq(1500); buzzer.duty(512); time.sleep(0.1)
        buzzer.freq(2500); time.sleep(0.2); buzzer.duty(0)
        
        led_green.value(1)
        time.sleep(4)
        led_green.value(0)
        send_alert("CLOSED", TOPIC_DOOR_STATUS)
        msg("SYSTEM ARMED", "Waiting...")
        
    elif message == "ALARM_ON":
        print(">> PANIC MODE ACTIVATED")
        panic_mode = True
        
    elif message == "ALARM_OFF":
        print(">> PANIC MODE DEACTIVATED")
        panic_mode = False
        led_red.value(0)
        buzzer.duty(0)
        msg("SYSTEM ARMED", "Waiting...")

def connect_wifi(timeout_ms=20000):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...", end="")
        # USES SECRETS HERE 
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        start_time = time.ticks_ms()
        while not wlan.isconnected():
            time.sleep(0.5)
            print(".", end="")
            if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                print(" Failed!")
                return False
    print(" Connected! IP:", wlan.ifconfig()[0])
    return True

def connect_mqtt():
    global client
    try:
        # 1. Use your fixed Thing Name from secrets as the Client ID
        client_id = secrets.MQTT_CLIENT_ID 
        
        # 2. Read the AWS Certificates you uploaded to the /certs folder
        with open(secrets.CERT_FILE, 'rb') as f:
            cert_data = f.read()
        with open(secrets.KEY_FILE, 'rb') as f:
            key_data = f.read()
            
        # 3. Configure the Security Parameters (mTLS)
        ssl_params = {
            "cert": cert_data,
            "key": key_data,
            "server_side": False
        }

        print(f">> Connecting to AWS IoT Core: {secrets.MQTT_SERVER}...")
        
        # 4. Create the Secure Client
        client = MQTTClient(
            client_id, 
            secrets.MQTT_SERVER, 
            port=secrets.MQTT_PORT, 
            keepalive=60, 
            ssl=True, 
            ssl_params=ssl_params
        )
        
        client.set_callback(mqtt_callback)
        client.connect()
        client.subscribe(TOPIC_COMMANDS)
        print(">> Success: Securely Linked to AWS Cloud")
        return True
    except Exception as e:
        print(">> AWS Connection Failed:", e)
        return False

def send_alert(msg_text, topic=MQTT_TOPIC):
    if client:
        try:
            # Package the scan info into JSON so S3 can organize it
            payload = ujson.dumps({
                "device": secrets.MQTT_CLIENT_ID,
                "status": msg_text,
                "timestamp": time.time()
            })
            client.publish(topic, payload)
            print(f">> Cloud Log Sent: {msg_text}")
        except:
            print(">> Cloud Error. Reconnecting...")
            connect_mqtt()

# --- HELPER FUNCTIONS ---
def msg(line1, line2=""):
    oled.fill(0)
    y = 0
    for i, content in enumerate([str(line1), str(line2)]):
        if i == 1 and y < 16: y = 16
        while len(content) > 0:
            if y + 8 > 64: break
            chunk = content[:16]
            content = content[16:]
            oled.text(chunk, 0, y)
            y += 10
            if y > 0 and y < 16: y = 16
    oled.show()

def health_check():
    print("\n--- SYSTEM HEALTH CHECK ---")
    print(f"CPU Freq: {machine.freq() / 1000000} MHz")
    print(f"Mem Free: {gc.mem_free()} bytes")
    print(f"Mem Alloc: {gc.mem_alloc()} bytes")
    print("---------------------------\n")

def enroll_master_finger():
    print(">> STARTING ENROLLMENT...")
    msg("SETUP MODE", "Place New Finger")
    
    start_t = time.ticks_ms()
    while not fp.get_image():
        if time.ticks_diff(time.ticks_ms(), start_t) > 10000:
            msg("Timeout", "Try Again"); return
        time.sleep(0.01)
        
    if not fp.image2tz(1):
        msg("Error", "Bad Image"); return
        
    msg("Remove Finger", "...")
    print(">> First image taken. Remove finger.")
    
    start_rem = time.ticks_ms()
    while fp.get_image():
        if time.ticks_diff(time.ticks_ms(), start_rem) > 5000:
            msg("Timeout", "Remove Finger"); return
        time.sleep(0.01)
    time.sleep(2)
    
    msg("Place Same", "Finger Again")
    start_t = time.ticks_ms()
    while not fp.get_image():
        if time.ticks_diff(time.ticks_ms(), start_t) > 10000:
            msg("Timeout", "Try Again"); return
        time.sleep(0.01)
        
    if not fp.image2tz(2):
        msg("Error", "Bad Image"); return
        
    if fp.reg_model():
        if fp.store(1, 1):
            msg("SUCCESS!", "ID #1 Saved")
            print(">> SUCCESS: Fingerprint saved.")
            # Blink LED
            for _ in range(3): 
                led_green.value(1); time.sleep(0.1); led_green.value(0); time.sleep(0.1)
        else:
            msg("Error", "Save Failed")
    else:
        msg("Error", "No Match")

# --- STARTUP SEQUENCE ---
health_check()
msg("System Booting", "Connecting Net...")
if connect_wifi():
    try:
        ntptime.settime()
        print(">> Time synchronized via NTP")
    except:
        print(">> NTP Sync Failed")
    connect_mqtt()
    send_alert("System Booted")
else:
    msg("WiFi Failed", "Offline Mode")
    time.sleep(2)

msg("Setup Menu", "Hold BOOT Btn")
in_setup_mode = False
start_time = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start_time) < 2000:
    if setup_button.value() == 0:
        in_setup_mode = True
        break
    time.sleep_ms(20)

if in_setup_mode:
    msg("PASSWORD REQUIRED", "Check Terminal ->")
    print("\n--- ENTER SETUP PASSWORD ---")
    time.sleep(1) 
    password_input = input("Password: ")
    
    # USES SECRETS HERE (No Hashing)
    if password_input == secrets.SETUP_PASSWORD:
        print(">> Password Accepted.")
        msg("ACCESS GRANTED", "Wiping DB...")
        fp.empty_db()
        time.sleep(1)
        enroll_master_finger()
    else:
        print(">> Wrong Password.")
        msg("ACCESS DENIED", "Wrong Password")
        time.sleep(4)

msg("SYSTEM ARMED", "Waiting...")
send_alert("System Armed") # <--- MQTT ALERT



# Wait for PIR to stabilize (go low) to prevent immediate trigger
print(">> Waiting for PIR to stabilize...")
while pir.value() == 1:
    time.sleep(0.5)


# --- MAIN SECURITY LOOP ---
while True:
    if client:
        try: client.check_msg()
        except: pass
        
    if panic_mode:
        led_red.value(not led_red.value())
        buzzer.freq(500); buzzer.duty(50)
        msg("PANIC MODE", "LOCKED")
        time.sleep(0.1)
        buzzer.duty(0)
        time.sleep(0.1)
        continue

    if pir.value() == 1:
        print(">> Motion Detected!")
        msg("Welcome", "Scan to enter...")
        send_alert("Motion Detected", TOPIC_DETECTION)
        led_yellow.value(1)

        # Try Wake LED
        try: fp.led_control(True)
        except: pass
        
        start_scan = time.ticks_ms()
        access = False
        failed_attempts = 0 # <--- [NEW] Reset counter on new motion event
        
        # Scanning Window (10 seconds)
        while time.ticks_diff(time.ticks_ms(), start_scan) < 10000:
            if client:
                try: client.check_msg()
                except: pass
            if panic_mode: break

            if fp.get_image():
                if fp.image2tz(1) and fp.search():
                    # --- MATCH FOUND ---
                    failed_attempts = 0 # <--- [NEW] Reset counter on success
                    msg("ACCESS GRANTED", "Welcome Master")
                    send_alert("Access Granted", TOPIC_ACCESS)
                    send_alert("OPEN", TOPIC_DOOR_STATUS)
                    
                    # Acceptance Tone
                    buzzer.freq(1500); buzzer.duty(512); time.sleep(0.1)
                    buzzer.freq(2500); time.sleep(0.2); buzzer.duty(0)
                    
                    led_green.value(1)
                    time.sleep(4)
                    led_green.value(0)
                    send_alert("CLOSED", TOPIC_DOOR_STATUS)
                    led_yellow.value(0)
                    access = True
                    break
                else:
                    # --- NO MATCH (INTRUDER) ---
                    failed_attempts += 1 # <--- [NEW] Increment failure count
                    print(f">> Failed Attempt: {failed_attempts}/3")

                    # [NEW] BRUTE FORCE PROTECTION CHECK
                    if failed_attempts > 3:
                        print(">> BRUTE FORCE LIMIT REACHED")
                        msg("SYSTEM LOCKED", "Limit Overpassed")
                        send_alert("limit overpassed", TOPIC_ACCESS) # <--- MQTT ALERT

                        # 5 Second Lockout with Red LED Flicker
                        # Loop runs 25 times * 0.2s = 5.0 seconds
                        for _ in range(25): 
                            led_red.value(not led_red.value()) # Toggle LED
                            buzzer.freq(500) # Low tone warning
                            buzzer.duty(50)
                            time.sleep(0.1)
                            buzzer.duty(0)
                            time.sleep(0.1)
                        
                        led_red.value(0)
                        failed_attempts = 0 # Reset counter after penalty
                        access = False # Ensure access remains denied
                        break # Break the scanning loop immediately
                    
                    # [Standard Denial Handling] (Only if limit not reached)
                    msg("ACCESS DENIED", "Unknown Finger")
                    send_alert("Access Denied", TOPIC_ACCESS)
                    buzzer.freq(2000); buzzer.duty(10)
                    led_red.value(1)
                    time.sleep(1)
                    buzzer.duty(0)
                    led_red.value(0)
                    msg("Welcome", "Scan to enter...")
            
            time.sleep(0.01)
            
        if panic_mode:
            led_yellow.value(0)
            continue

        if not access:
            time.sleep(10)
            led_yellow.value(0)
            # Only show "System Locked" if we didn't just break out from Brute Force
            if failed_attempts < 3: 
                msg("System Locked", "Wait ...")
            
            send_alert("No Motion Detected", TOPIC_DETECTION)
            if not access: send_alert("No Scan", TOPIC_ACCESS)
            time.sleep(0.5)
            
        # Try Sleep LED
        try: fp.led_control(False)
        except: pass
        
        msg("SYSTEM ARMED", "Waiting...")
        
    time.sleep(0.1)