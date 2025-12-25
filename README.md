# Project Overview: IoT Biometric Security System

## 1. Executive Summary
This project implements a **smart access control system** utilizing a microcontroller (ESP32/ESP8266), biometric authentication, and IoT connectivity. The system functions as a "Smart Lock" that sleeps to save power, wakes up upon detecting motion, and requires a valid fingerprint to grant access, all while reporting real-time events to a remote server.

## 2. Hardware Architecture
The system integrates several distinct hardware modules:
* **Controller:** Microcontroller with WiFi capabilities.
* **Sensors:**
    * **PIR Motion Sensor:** Detects physical presence to wake the system.
    * **Optical Fingerprint Sensor (UART):** Handles biometric scanning and image storage.
* **User Interface:**
    * **OLED Display (I2C):** Visual feedback (e.g., "Scan Finger", "Access Denied").
    * **Buzzer:** Audio feedback (Success chimes vs. Intruder alarms).
    * **LEDs:** Status indicators (Green=Access, Red=Deny, Yellow=Scanning).

## 3. Core Logic Flow

### A. The "Armed" State
The system sits in a loop monitoring the PIR sensor.
* **Idle:** The system is "Armed" and waiting.
* **Trigger:** When the PIR detects motion, the Yellow LED turns on, and the OLED displays a welcome message.

### B. Authentication Process
Once motion is detected, the system initiates a 10-second scanning window:
1.  **Scan:** The user places a finger on the sensor.
2.  **Verification:** The sensor compares the print against the internal database.
    * **Success:** Green LED on, "Access Granted" displayed, Success tone played.
    * **Failure:** Red LED flashes, "Access Denied" displayed, Alarm tone played.
3.  **Timeout:** If no finger is placed within 10 seconds, the system locks down and returns to the "Armed" state.

### C. Admin & Maintenance Mode
The code includes a secure enrollment sequence:
* **Trigger:** Holding the `BOOT` button during startup.
* **Security:** Requires a password input via the Serial Terminal.
* **Action:** Wipes the fingerprint database and enters a guided mode to enroll a new "Master" fingerprint.

## 4. IoT & Remote Monitoring (MQTT)
The device connects to a local WiFi network and an MQTT Broker to log security events. 

## 5. Circuit Connections (Inferred)
* **I2C Bus:** OLED Display (SDA=Pin 21, SCL=Pin 22)
* **UART:** Fingerprint Sensor (TX=17, RX=16)
* **GPIO:** PIR (Pin 2), Green LED (4), Red LED (5), Yellow LED (18), Buzzer (23).

## 6. Security Analysis & Auditing (Bus Pirate v4)
To validate the physical security of this device, a **Bus Pirate v4** is used to perform hardware penetration testing and protocol analysis.

### A. UART Sniffing (Fingerprint Sensor Attack)
The fingerprint sensor communicates with the MCU via UART (Pins 16/17).
* **Vulnerability:** A "Man-in-the-Middle" attack.
* **Method:** The Bus Pirate probes the RX/TX lines.
* **Goal:** Capture the specific byte sequence sent by the sensor when a fingerprint is *successfully* matched.
* **Exploit:** An attacker can use the Bus Pirate to **replay** this "Success" packet to the MCU, tricking the system into unlocking without a real finger.

### B. I2C Interception (Data Snooping)
The OLED display uses the I2C bus (Pins 21/22).
* **Method:** The Bus Pirate connects to SDA/SCL lines in "I2C Sniffer" mode.
* **Goal:** Decode the text being sent to the screen.
* **Exploit:** Even if the screen is covered or broken, an attacker can read the "Setup Password" prompts or internal debug messages invisible to the user.

### C. Setup Mode Brute-Force
* **Method:** The Bus Pirate acts as a UART bridge (Bitbanging mode) to the setup terminal.
* **Goal:** Automate the entry of passwords at high speed.
* **Exploit:** Attempt to brute-force the setup password defined in `secrets.py` to gain administrative control and wipe the database.
