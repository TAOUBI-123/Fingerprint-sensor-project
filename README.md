

# 🔐 ESP32 Biometric Sensor

A robust IoT security solution built with MicroPython on ESP32. This system combines biometric authentication with motion detection, brute-force protection, and secure real-time remote management via MQTT.

## 📖 Overview

This project turns an ESP32 into an intelligent access control system. It remains in a low-power idle state until motion is detected. Once triggered, it activates a fingerprint scanner for authentication. The system handles logic for door locking mechanisms, local alarms, and communicates securely with a central MQTT broker to report access logs and receive remote commands.

**Key Features:**
* **Biometric Access:** Optical fingerprint verification (AS608/R307).
* **Smart Wake-up:** PIR motion sensor activation to conserve component life.
* **Remote Management:** Open door, arm/disarm, and trigger panic mode via MQTT.
* **OLED Feedback:** Real-time status display (Access Granted, Denied, System Locked).
* **Secure Timekeeping:** NTP synchronization for accurate event logging and replay-attack prevention.

---

## 🛡️ Security Architecture

This system uses a **Defense-in-Depth** strategy, layering physical hardware security with software logic and encrypted network communication.

### 1. Physical & Biometric Layer
* **Two-Factor Wake-up:** The fingerprint scanner is logically inactive until the **PIR Motion Sensor** detects movement. This obscures the sensor from attackers and reduces power consumption.
* **Biometric Privacy:** Fingerprint data is hashed and stored locally on the sensor's internal flash memory. Actual fingerprint images are never transmitted over the network or stored on the ESP32.

### 2. Application Logic Layer
* **Brute-Force Protection:** The system monitors for repeated failures.
    * **Trigger:** 3 consecutive failed authentication attempts.
    * **Response:** Immediate system lockout for 5 seconds, visual/audible alarm activation, and an MQTT alert (`limit overpassed`) sent to the admin.
* **Panic Mode:** A global flag that overrides all other operations. When active, it disables the door release and locks the system into an alarm state until explicitly reset via MQTT.

### 3. Network & Transport Layer
* **Encrypted Communication:** MQTT traffic is secured using **SSL/TLS**. This prevents packet sniffing of critical commands (e.g., "OPEN_DOOR") on the local network.
* **Certificate Validation:** The system verifies the identity of the MQTT broker using a CA certificate (`hivemq.pem`) to prevent Man-in-the-Middle (MitM) attacks.

### 4. Anti-Replay Mechanism
To prevent an attacker from recording a valid "OPEN_DOOR" signal and replaying it later, the system enforces **Timestamp Validation**:
* **Logic:** Every remote command must include a Unix timestamp (`ts`).
* **Window:** The device rejects any command where the timestamp differs from the device's NTP-synced time by more than **30 seconds**.

### 5. Setup Security
* **Console Lock:** The enrollment menu is inaccessible via the physical interface alone. It requires:
    1.  Holding the physical **BOOT** button during startup.
    2.  Entering a **Password** via the Serial/UART console (hashed in `secrets.py`).


## 🛠 Hardware Required

| Component | Description |
| :--- | :--- | 
| **ESP32** | Development Board (e.g., ESP32 DevKit V1) |
| **Fingerprint Sensor** | AS608 or R307 (UART) | 
| **OLED Display** | SSD1306 0.96" I2C (128x64) | 
| **PIR Sensor** | HC-SR501 Motion Detector | 
| **Buzzer** | Active or Passive Piezo Buzzer | 
| **LEDs** | Red, Green, Yellow |
| **Resistors** | 220Ω or 330Ω (for LEDs) |
| **Push Button** | Uses the onboard BOOT button (GPIO 0) for setupe |

## 🔌 Wiring Diagram

| Component | ESP32 Pin | Sensor Pin / Note | Function |
| :--- | :--- | :--- | :--- |
| **OLED SDA** | GPIO 21 | SDA | I2C Data |
| **OLED SCL** | GPIO 22 | SCL | I2C Clock |
| **Fingerprint TX** | GPIO 16 | RX (Green Wire) | UART RX (Receive) |
| **Fingerprint RX** | GPIO 17 | TX (White Wire) | UART TX (Transmit) |
| **PIR Sensor** | GPIO 2 | OUT | Motion Input |
| **Green LED** | GPIO 4 | Anode (+) | Success Indicator |
| **Red LED** | GPIO 5 | Anode (+) | Alarm/Fail Indicator |
| **Yellow LED** | GPIO 18 | Anode (+) | Busy/Scanning Indicator |
| **Buzzer** | GPIO 23 | Positive (+) | PWM Audio Alarm |
| **Setup Button** | GPIO 0 | (Built-in BOOT) | Long press for Setup |

> **⚠️ Important:**
> * **Power:** Most fingerprint sensors (AS608/R307) require **3.3V** or **5V** VCC. Check your specific datasheet.
> * **Logic Levels:** The ESP32 uses **3.3V logic**. If your sensor is 5V, the RX/TX lines are usually tolerant, but level shifting is recommended for long-term reliability.
> * **Common Ground:** Ensure all components share a common Ground (GND) with the ESP32.

## 📂 Project Structure

```
├── main.py               # Main application logic
├── config/
│   ├── secrets.py        # Credentials (Git ignored)
│   └── hivemq.pem        # SSL Certificate authority
└── lib/
    ├── ssd1306.py        # OLED Driver
    ├── fingerprint.py    # Fingerprint Sensor Driver
    └── mqtt.py           # MQTT Client Library
```

## ⚙️ Configuration
```config/secrets.py``` **Template:**
```python
# Network Credentials
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASS = "YOUR_WIFI_PASSWORD"

# MQTT Configuration
MQTT_SERVER = "broker.hivemq.com" 
MQTT_PORT = 8883
MQTT_USER = "your_mqtt_user"
MQTT_PASS = "your_mqtt_password"
MQTT_SSL = True   
MQTT_CERT = "hivemq.pem" # Filename in config/ folder

# Admin Security
SETUP_PASSWORD = "super_secret_admin_pass"
```
## 🚀 Usage

### 1. Enrollment (Setup Mode)
To add a new authorized user ("Master Finger") to the database:
1.  **Restart** the ESP32.
2.  Watch the OLED display. When it shows **"Hold BOOT Btn"**, press and hold the physical `BOOT` button (GPIO 0) for **2 seconds**.
3.  The screen will change to **"PASSWORD REQUIRED"**.
4.  Open your Serial Terminal (e.g., Thonny, PuTTY, or VS Code) connected to the ESP32.
5.  Type the `SETUP_PASSWORD` defined in your `secrets.py` file and press Enter.
6.  Follow the on-screen instructions to place and remove your finger to complete enrollment.

### 2. Normal Operation
Once booted, the system enters **"SYSTEM ARMED"** mode.
* **Motion Detection:** The PIR sensor monitors the area. When motion is detected, the **Yellow LED** turns ON and the fingerprint scanner wakes up.
* **Authentication:**
    * **Match:** The **Green LED** lights up, the buzzer plays a success tone, and the OLED displays "Welcome". The door state changes to `OPEN` for 4 seconds.
    * **No Match:** The **Red LED** flashes, and the OLED displays "Access Denied".
* **Brute Force Protection:** If **3 consecutive failed attempts** occur, the system triggers a **5-second lockout** with a visual/audible alarm.

### 3. Remote MQTT Commands
You can control the device remotely by publishing JSON messages to the topic:
`abdel_project_9Xs9/security/commands`

**Unlock Door:**
```json
{
  "cmd": "OPEN_DOOR", 
  "ts": "1706631000"
}
```
(Note: ts is Unix Timestamp. Must be within 30s of device time).
**Panic Alarm:**
```json
{"cmd": "ALARM_ON"}
```
**Silence Alarm:**
```json
{"cmd": "ALARM_OFF"}
```

## 📡 MQTT Topics

The device communicates with the broker using the base path: `abdel_project_9Xs9/security/`

| Topic Suffix | Type | Description | Payload Example |
| :--- | :--- | :--- | :--- |
| `.../alerts` | 📤 Pub | General system status updates | `"System Booted"`, `"System Armed"` |
| `.../detection` | 📤 Pub | PIR motion sensor events | `"Motion Detected"`, `"No Motion Detected"` |
| `.../access` | 📤 Pub | Authentication logs | `"Access Granted"`, `"Access Denied"`, `"limit overpassed"` |
| `.../door` | 📤 Pub | Physical door lock state | `"OPEN"`, `"CLOSED"` |
| `.../commands` | 📥 Sub | Remote control inputs | `{"cmd": "OPEN_DOOR", "ts": "1706631000"}` |

## 📦 Dependencies

To run this project, you need to upload the following libraries to the `/lib` directory on your ESP32.

-  **`ssd1306.py`** The standard MicroPython driver for OLED displays.  
  *(Available in the official MicroPython repository)*

-  **`fingerprint.py`** A MicroPython port of the Adafruit Fingerprint sensor library.  
  *(Ensure this supports UART communication for AS608/R307 sensors)*

-  **`mqtt.py`** The lightweight MQTT client.  
  > **Note:** This is typically the standard `umqtt.simple` library. You must rename the file from `simple.py` to `mqtt.py` for the imports in `main.py` to work.

