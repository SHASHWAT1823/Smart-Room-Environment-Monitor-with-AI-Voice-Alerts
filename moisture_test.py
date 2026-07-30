import time
import board
import busio

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# Initialize I2C
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize ADS1115
ads = ADS.ADS1115(i2c)

# Read channel A0
chan = AnalogIn(ads, 0)

print("Reading Moisture Sensor...\n")

while True:
    print(f"Voltage : {chan.voltage:.3f} V")
    print(f"ADC Raw : {chan.value}")
    print("------------------------")
    time.sleep(1)
