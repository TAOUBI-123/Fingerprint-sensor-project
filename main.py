from machine import Pin, SoftI2C, unique_id, PWM
import time, network, ubinascii
import lib.ssd1306 as ssd1306
import lib.fingerprint as fingerprint
from lib.mqtt import MQTTClient # Requires mqtt.py file
from config import secrets  

# --- CONFIGURATION (Loaded from secrets.py) ---
MQTT_TOPIC = "security/alert"

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

# I2C OLED Display (SDA=21, SCL=22)
i2c = SoftI2C(scl=Pin(22), sda=Pin(21), freq=100000)
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# UART Fingerprint Sensor (TX=17, RX=16)
fp = fingerprint.Fingerprint(uart_id=2, tx=17, rx=16)

# --- NETWORK FUNCTIONS ---
client = None

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...", end="")
        # USES SECRETS HERE
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        timeout = 0
        while not wlan.isconnected():
            time.sleep(0.5)
            print(".", end="")
            timeout += 1
            if timeout > 20: # 10s timeout
                print(" Failed!")
                return False
    print(" Connected! IP:", wlan.ifconfig()[0])
    return True

def connect_mqtt():
    global client
    try:
        client_id = ubinascii.hexlify(unique_id())
        # USES SECRETS HERE
        print(f">> Connecting to MQTT Broker at {secrets.MQTT_SERVER}...")
        client = MQTTClient(client_id, secrets.MQTT_SERVER)
        client.connect()
        print(">> MQTT Connected to Broker")
        return True
    except Exception as e:
        print(">> MQTT Failed:", e)
        return False

def send_alert(msg_text):
    if client:
        try:
            client.publish(MQTT_TOPIC, msg_text)
            print(f">> MQTT Sent: {msg_text}")
        except:
            print(">> MQTT Error. Reconnecting...")
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
msg("System Booting", "Connecting Net...")
if connect_wifi():
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
        msg("ACCESS DENIED", "Wrong Password")
        time.sleep(2)

msg("SYSTEM ARMED", "Waiting...")
send_alert("System Armed") # <--- MQTT ALERT

# Try to turn off LED (If supported)
try: fp.led_control(False)
except: pass 

# --- MAIN SECURITY LOOP ---
while True:
    if pir.value() == 1:
        print(">> Motion Detected!")
        msg("MOTION DETECTED", "Scan ID #1...")
        send_alert("Motion Detected") # <--- MQTT ALERT
        led_yellow.value(1)

        # Try Wake LED
        try: fp.led_control(True)
        except: pass
        
        start_scan = time.ticks_ms()
        access = False
        
        while time.ticks_diff(time.ticks_ms(), start_scan) < 10000:
            if fp.get_image():
                if fp.image2tz(1) and fp.search():
                    # Match found
                    msg("ACCESS GRANTED", "Welcome Master")
                    send_alert("Access Granted") # <--- MQTT ALERT
                    
                    # Acceptance Tone
                    buzzer.freq(1500)
                    buzzer.duty(512) 
                    time.sleep(0.1)
                    buzzer.freq(2500)
                    time.sleep(0.2)
                    buzzer.duty(0)   # Silence
                    
                    led_green.value(1)
                    time.sleep(4)
                    led_green.value(0)
                    led_yellow.value(0)
                    access = True
                    break
                else:
                    # Intruder
                    msg("ACCESS DENIED", "Unknown Finger")
                    send_alert("Access Denied: Intruder") # <--- MQTT ALERT
                    buzzer.freq(2000) 
                    buzzer.duty(10)  
                    led_red.value(1)
                    time.sleep(1)
                    buzzer.duty(0)
                    led_red.value(0)
                    msg("MOTION DETECTED", "Scan ID #1...")
            time.sleep(0.01)
            
        if not access:
            led_yellow.value(0)
            msg("TIMEOUT", "System Locked")
            send_alert("Timeout: No Scan") # <--- MQTT ALERT
            time.sleep(2)
            
        # Try Sleep LED
        try: fp.led_control(False)
        except: pass
        
        msg("SYSTEM ARMED", "Waiting...")
        
    time.sleep(0.1)