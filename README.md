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
