#!/usr/bin/env python3

import json
import ssl
import time
import base64
import subprocess
import tempfile
import os
import urllib.request

import board
import busio
import adafruit_dht
import paho.mqtt.client as mqtt

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# ==================================================
# AWS IoT Configuration
# ==================================================

ENDPOINT = "a2juep91lmd06o-ats.iot.ap-south-1.amazonaws.com"

CLIENT_ID = "room-pi-01"

TELEMETRY_TOPIC = "room/telemetry"
AUDIO_TOPIC = "room/alerts/audio"

CA = "/home/pi/certs/AmazonRootCA1.pem"
CERT = "/home/pi/certs/07cab4a453de2301c7d858b74cee37b7452e1c3a65b8dd2e5389c766889f33ec-certificate.pem.crt"
KEY = "/home/pi/certs/07cab4a453de2301c7d858b74cee37b7452e1c3a65b8dd2e5389c766889f33ec-private.pem.key"

INTERVAL = 60

# ==================================================
# Sensors
# ==================================================

dht = adafruit_dht.DHT22(board.D4)

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


# ==================================================
# Audio
# ==================================================

def play_mp3(data: bytes):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(data)
        path = f.name

    try:
        subprocess.run(
            [
                "mpg123",
                "-o",
                "alsa",
                "-a",
                "plughw:CARD=Device,DEV=0",
                "-q",
                path,
            ],
            check=False,
        )
    finally:
        if os.path.exists(path):
            os.unlink(path)


# ==================================================
# MQTT
# ==================================================

def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected to AWS IoT rc =", rc)

    result, mid = client.subscribe(AUDIO_TOPIC, qos=1)

    print("Subscribe:", result, mid)


def on_disconnect(client, userdata, rc, *args):
    print("Disconnected:", rc)


def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed:", granted_qos)


def on_message(client, userdata, msg):
    payload = json.loads(msg.payload)

    print(payload.get("alert_text", ""))

    if "audio_b64" in payload:
        play_mp3(base64.b64decode(payload["audio_b64"]))

    elif "audio_url" in payload:
        play_mp3(
            urllib.request.urlopen(
                payload["audio_url"]
            ).read()
        )


client = mqtt.Client(client_id=CLIENT_ID)

client.tls_set(
    ca_certs=CA,
    certfile=CERT,
    keyfile=KEY,
    tls_version=ssl.PROTOCOL_TLSv1_2,
)

client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_subscribe = on_subscribe
client.on_message = on_message

print("Connecting...")

client.connect(
    ENDPOINT,
    8883,
    keepalive=120,
)

client.loop_start()

# ==================================================
# Publish Function
# ==================================================

def publish_telemetry():

    temperature = None
    humidity = None

    for _ in range(3):
        try:
            temperature = dht.temperature
            humidity = dht.humidity

            if temperature is not None and humidity is not None:
                break

        except RuntimeError as e:
            print("DHT:", e)
            time.sleep(2)

    else:
        print("Failed to read DHT22 after 3 attempts")
        return

    moisture_pct, moisture_raw = get_moisture()

    payload = {
        "device_id": CLIENT_ID,
        "ts": int(time.time()),
        "temperature_c": round(temperature, 1),
        "humidity_pct": round(humidity, 1),
        "soil_moisture_pct": moisture_pct,
        "soil_moisture_raw": moisture_raw,
    }

    info = client.publish(
        TELEMETRY_TOPIC,
        json.dumps(payload),
        qos=0,
    )

    print("Publish rc =", info.rc)
    print(payload)


# ==================================================
# Main Loop
# ==================================================

while True:
    publish_telemetry()
    time.sleep(INTERVAL)
