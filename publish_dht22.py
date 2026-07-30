#!/usr/bin/env python3

import json
import ssl
import time

import board
import busio
import adafruit_dht
import paho.mqtt.client as mqtt

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# ==========================
# AWS IoT Configuration
# ==========================

ENDPOINT = "a2juep91lmd06o-ats.iot.ap-south-1.amazonaws.com"
CLIENT_ID = "room-pi-01-pub"

TOPIC = "room/telemetry"

CA = "/home/pi/certs/AmazonRootCA1.pem"
CERT = "/home/pi/certs/07cab4a453de2301c7d858b74cee37b7452e1c3a65b8dd2e5389c766889f33ec-certificate.pem.crt"
KEY = "/home/pi/certs/07cab4a453de2301c7d858b74cee37b7452e1c3a65b8dd2e5389c766889f33ec-private.pem.key"

# ==========================
# DHT22
# ==========================

dht = adafruit_dht.DHT22(board.D4)

# ==========================
# ADS1115
# ==========================

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
moisture = AnalogIn(ads, 0)

AIR_RAW = 26150
WATER_RAW = 9100


def get_moisture():
    raw = moisture.value
    percent = (AIR_RAW - raw) * 100 / (AIR_RAW - WATER_RAW)
    percent = max(0, min(100, percent))
    return int(percent), raw


client = mqtt.Client(client_id=CLIENT_ID)

client.tls_set(
    ca_certs=CA,
    certfile=CERT,
    keyfile=KEY,
    tls_version=ssl.PROTOCOL_TLSv1_2,
)


def on_connect(client, userdata, flags, rc, properties=None):
    print("CONNECTED rc =", rc)


def on_disconnect(client, userdata, rc, *args):
    print("DISCONNECTED rc =", rc)


client.on_connect = on_connect
client.on_disconnect = on_disconnect

print("Connecting...")

client.connect(ENDPOINT, 8883, 60)
client.loop_start()

time.sleep(2)

print("Entering loop...")

while True:
    try:
        print("DEBUG 1")
        temperature = dht.temperature
        print("DEBUG 2")
        humidity = dht.humidity
        print("DEBUG 3")

        print("Reading DHT...")

        print("Temp:", temperature)
        print("Humidity:", humidity)

        print("Reading ADS1115...")

        moisture_pct, moisture_raw = get_moisture()

        print("Moisture:", moisture_pct, moisture_raw)

        if temperature is None or humidity is None:
            print("Invalid DHT reading")
            time.sleep(5)
            continue

        payload = {
            "device_id": CLIENT_ID,
            "ts": int(time.time()),
            "temperature_c": round(temperature, 1),
            "humidity_pct": round(humidity, 1),
            "soil_moisture_pct": moisture_pct,
            "soil_moisture_raw": moisture_raw
        }

        print("Publishing...")

        info = client.publish(
            TOPIC,
            json.dumps(payload),
            qos=0
        )

        print("Publish rc =", info.rc)
        print(payload)

    except RuntimeError as e:
        print("RuntimeError:", e)

    except Exception as e:
        print("Exception:", e)

    print("-------------------------")
    time.sleep(10)
