
# Smart Room Environment Monitor with AI Voice Alerts

An AI powered IoT monitoring system built using Raspberry Pi Zero W and AWS.

## Features

- Temperature & Humidity Monitoring
- Soil Moisture Monitoring
- AWS IoT Core (MQTT over TLS)
- AWS Lambda
- Amazon DynamoDB
- Amazon Polly
- Amazon Transcribe
- AWS SNS Alerts
- Flask Dashboard
- AI powered Voice Alerts
- Voice Query Support

## Dashboard

A **Flask + Chart.js** dashboard is included for real time visualization of room telemetry and device status.

**Location**

```text
Dashboard/
```

**Features**

- Real time temperature graph
- Real time humidity graph
- Real time soil moisture graph
- Device online/offline status
- Latest telemetry timestamp
- Historical sensor visualization using Chart.js
- Responsive web interface

## Hardware

- Raspberry Pi Zero W
- DHT22
- Soil Moisture Sensor
- ADS1115 ADC
- USB Microphone
- USB Speaker

## AWS Services

- AWS IoT Core
- AWS Lambda
- DynamoDB
- Amazon Polly
- Amazon Transcribe
- Amazon S3
- Amazon SNS
- AWS IoT Device Shadow