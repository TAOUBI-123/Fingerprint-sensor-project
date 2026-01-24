from machine import Pin, SoftI2C, unique_id, PWM
import time, network, ubinascii, sys, ntptime, ujson, gc, machine

# Fix for missing 'ussl' module
try:
    import ussl
except ImportError:
    import ssl
    sys.modules['ussl'] = ssl

import lib.ssd1306 as ssd1306
import lib.fingerprint as fingerprint
from lib.mqtt import MQTTClient 
from config import secrets  

# --- CONFIGURATION ---
MQTT_TOPIC = "abdel_project_9Xs9/security/alerts"
TOPIC_DETECTION = "abdel_project_9Xs9/security/detection"
TOPIC_ACCESS = "abdel_project_9Xs9/security/access"
TOPIC_COMMANDS = "abdel_project_9Xs9/security/commands"
TOPIC_DOOR_STATUS = "abdel_project_9Xs9/security/door"

# --- HARDWARE CONFIGURATION ---
led_green = Pin(4, Pin.OUT)
led_red = Pin(5, Pin.OUT)
led_yellow = Pin(18, Pin.OUT)
pir = Pin(2, Pin.IN)
setup_button = Pin(0, Pin.IN, Pin.PULL_UP)
buzzer = PWM(Pin(23))
buzzer.duty(0)

# I2C OLED Display
i2c = SoftI2C(scl=Pin(22), sda=Pin(21), freq=100000)
try:
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
except:
    class DummyOLED:
        def fill(self, c): pass
        def text(self, s, x, y, c=1): pass
        def show(self): pass
    oled = DummyOLED()

# Fingerprint Sensor
fp = fingerprint.Fingerprint(uart_id=2, tx=17, rx=16)

# --- GLOBAL STATE ---
client = None
panic_mode = False

# --- MQTT CALLBACK (Node-RED Compatible) ---
def mqtt_callback(topic, msg_in):
    global panic_mode
    raw_msg = msg_in.decode()
    print(f">> MQTT In: {topic.decode()} -> {raw_msg}")
    
    # 1. Handle Node-RED Simple Strings
    if raw_msg == "OPEN_DOOR":
        remote_unlock()
    elif raw_msg == "ALARM_ON":
        panic_mode = True
    elif raw_msg == "ALARM_OFF":
        panic_mode = False
        led_red.value(0)
        buzzer.duty(0)
        msg("SYSTEM ARMED", "Waiting...")
    
    # 2. Handle Secure JSON Commands (Existing Logic)
    else:
        try:
            payload = ujson.loads(msg_in)
            cmd = payload.get("cmd")
            if cmd == "OPEN_DOOR":
                remote_unlock()
        except:
            pass

def remote_unlock():
    print(">> Remote Unlock Triggered")
    msg("Remote Access", "Unlocked")
    send_alert("OPEN", TOPIC_DOOR_STATUS)
    buzzer.freq(1500); buzzer.duty(512); time.sleep(0.1)
    buzzer.freq(2500); time.sleep(0.2); buzzer.duty(0)
    led_green.value(1)
    time.sleep(4)
    led_green.value(0)
    send_alert("CLOSED", TOPIC_DOOR_STATUS)
    msg("SYSTEM ARMED", "Waiting...")

# --- NETWORK FUNCTIONS ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        for _ in range(20):
            if wlan.isconnected(): break
            time.sleep(1)
    return wlan.isconnected()

def connect_mqtt():
    global client
    try:
        with open(secrets.CERT_FILE, 'rb') as f: cert_data = f.read()
        with open(secrets.KEY_FILE, 'rb') as f: key_data = f.read()
        ssl_params = {"cert": cert_data, "key": key_data, "server_side": False}

        client = MQTTClient(secrets.MQTT_CLIENT_ID, secrets.MQTT_SERVER, port=8883, keepalive=60, ssl=True, ssl_params=ssl_params)
        client.cb = mqtt_callback # Use .cb for umqttsimple
        client.connect()
        client.subscribe(TOPIC_COMMANDS)
        print(">> Linked to AWS & Node-RED")
        return True
    except Exception as e:
        print(">> AWS Fail:", e)
        return False

def send_alert(msg_text, topic=MQTT_TOPIC):
    if client:
        try:
            payload = ujson.dumps({
                "device": secrets.MQTT_CLIENT_ID,
                "status": msg_text,
                "timestamp": time.time() + 946684800
            })
            client.publish(topic, payload)
        except:
            connect_mqtt()

def msg(line1, line2=""):
    oled.fill(0)
    oled.text(str(line1)[:16], 0, 0)
    oled.text(str(line2)[:16], 0, 16)
    oled.show()

# --- STARTUP ---
msg("Booting...", "Connecting...")
if connect_wifi():
    try: ntptime.settime()
    except: pass
    connect_mqtt()
    send_alert("System Online")
else:
    msg("WiFi Error", "Offline Mode")

msg("SYSTEM ARMED", "Waiting...")

# --- MAIN LOOP ---
failed_attempts = 0

while True:
    # Always check for Node-RED commands first
    if client:
        try: client.check_msg()
        except: pass
        
    if panic_mode:
        led_red.value(not led_red.value())
        buzzer.freq(500); buzzer.duty(50); time.sleep(0.1)
        buzzer.duty(0); time.sleep(0.1)
        continue

    # PIR Detection
    if pir.value() == 1:
        led_yellow.value(1)
        msg("Welcome", "Scan Finger...")
        send_alert("Motion Detected", TOPIC_DETECTION)
        
        start_scan = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_scan) < 10000:
            if client: client.check_msg() # Listen while scanning
            
            if fp.get_image():
                if fp.image2tz(1) and fp.search():
                    # SUCCESS
                    msg("ACCESS GRANTED", "Welcome")
                    send_alert("Access Granted", TOPIC_ACCESS)
                    remote_unlock()
                    failed_attempts = 0
                    break
                else:
                    # FAILURE
                    failed_attempts += 1
                    msg("DENIED", f"Try {failed_attempts}/3")
                    send_alert("Access Denied", TOPIC_ACCESS)
                    led_red.value(1); time.sleep(1); led_red.value(0)
                    
                    if failed_attempts >= 3:
                        msg("LOCKED", "Wait 30s")
                        send_alert("Limit Overpassed", TOPIC_ACCESS)
                        time.sleep(30)
                        failed_attempts = 0
                        break
            time.sleep(0.1)
        
        led_yellow.value(0)
        msg("SYSTEM ARMED", "Waiting...")
        
    time.sleep(0.2)