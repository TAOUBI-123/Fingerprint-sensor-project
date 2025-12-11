# boot.py -- run on boot-up
# This file is executed on every boot (including wake-boot from deepsleep)
import esp
esp.osdebug(None) # Optional: turns off some vendor debug messages
