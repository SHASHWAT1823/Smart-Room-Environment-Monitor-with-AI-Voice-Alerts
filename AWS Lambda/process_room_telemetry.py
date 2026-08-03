import os
import json
import base64
import uuid
import urllib3
import boto3
import re
import io
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

# AWS Clients

ddb = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
polly = boto3.client("polly")
iot = boto3.client("iot-data")
sns = boto3.client("sns")
s3 = boto3.client("s3")

http = urllib3.PoolManager(maxsize=10)

# Environment Variables

TEMP_MAX = float(os.environ.get("TEMP_MAX", "32"))
HUM_MAX = float(os.environ.get("HUM_MAX", "70"))
SOIL_MIN = float(os.environ.get("SOIL_MIN", "30"))

AUDIO_TOPIC = os.environ.get("AUDIO_TOPIC", "room/alerts/audio")
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
AUDIO_BUCKET = os.environ["AUDIO_BUCKET"]

THING_NAME = "room-pi-01"

DEEPSEEK_MODEL = os.environ["DEEPSEEK_MODEL"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
CLAUDE_MODEL = os.environ["CLAUDE_MODEL"]

# Helper Functions

def load_thresholds():
    global TEMP_MAX, HUM_MAX, SOIL_MIN
    try:
        response = iot.get_thing_shadow(thingName=THING_NAME)
        shadow = json.loads(response["payload"].read())
        desired = shadow.get("state", {}).get("desired", {})
        TEMP_MAX = float(desired.get("temp_max", TEMP_MAX))
        HUM_MAX = float(desired.get("humidity_max", HUM_MAX))
        SOIL_MIN = float(desired.get("soil_min", SOIL_MIN))
    except Exception as e:
        print("Shadow read failed:", e)

def remove_emojis(text: str) -> str:
    return re.sub(r'[^\x00-\x7F]+', '', text).strip()

def ask_claude(prompt):
    payload = {"model": CLAUDE_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4, "max_tokens": 150}
    try:
        response = http.request("POST", "https://api.anthropic.com/v1/messages", 
                                headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, 
                                body=json.dumps(payload).encode("utf-8"), timeout=8.0)
        if response.status != 200: return None
        result = json.loads(response.data.decode("utf-8"))
        content = result.get("content", [])
        return content[0].get("text", "").strip() if content else None
    except Exception as e:
        print("Claude Error:", e)
        return None

def ask_deepseek(prompt):
    payload = {"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4, "max_tokens": 150}
    try:
        response = http.request("POST", "https://api.deepseek.com/chat/completions", 
                                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}, 
                                body=json.dumps(payload).encode("utf-8"), timeout=8.0)
        if response.status != 200: return None
        result = json.loads(response.data.decode("utf-8"))
        choices = result.get("choices", [])
        content = choices[0].get("message", {}).get("content")
        return content.strip() if content else None
    except Exception as e:
        print("DeepSeek Error:", e)
        return None

# Lambda Handler

def lambda_handler(event, context):
    load_thresholds()

    device_id = str(event.get("device_id", "unknown_device"))
    ts = int(event.get("ts", 0))
    temperature = float(event.get("temperature_c", 0.0))
    humidity = float(event.get("humidity_pct", 0.0))
    soil_moisture = float(event.get("soil_moisture_pct", 0.0))
    soil_raw = int(event.get("soil_moisture_raw", 0))

    # Save to DynamoDB
    ddb.put_item(Item={
        "device_id": device_id, "ts": ts,
        "temperature_c": Decimal(str(temperature)), "humidity_pct": Decimal(str(humidity)),
        "soil_moisture_pct": Decimal(str(soil_moisture)), "soil_moisture_raw": soil_raw
    })

    # BREACH LOGIC
    breaches = []
    if temperature > TEMP_MAX: breaches.append(f"Temperature is {temperature:.1f}°C")
    if humidity > HUM_MAX: breaches.append(f"Humidity is {humidity:.1f}%")
    if soil_moisture < SOIL_MIN: breaches.append(f"Soil moisture is {soil_moisture:.1f}%")

    # Handle Logic: Normal status vs Breach AI Alert
    if not breaches:
        final_alert = (
            f"Current room status: Temperature is {temperature:.1f} degrees Celsius, "
            f"humidity is {humidity:.1f} percent, and soil moisture is {soil_moisture:.1f} percent. "
            f"All room conditions are normal."
        )
    else:
        prompt = f"""
        You are an intelligent room environment assistant.
        Current readings:
        - Temperature: {temperature:.1f}°C
        - Humidity: {humidity:.1f}%
        - Soil Moisture: {soil_moisture:.1f}%

        Issues detected: {', '.join(breaches)}.

        Provide a short, friendly, natural voice response (max 2 sentences).
        Explain the issue and suggest one simple action.
        Do not use emojis or markdown.
        """

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_claude = executor.submit(ask_claude, prompt)
            f_ds = executor.submit(ask_deepseek, prompt)
            claude_response = f_claude.result()
            deepseek_response = f_ds.result()

        if claude_response and deepseek_response:
            if claude_response.strip().lower() == deepseek_response.strip().lower():
                final_alert = claude_response
            else:
                final_alert = f"{claude_response} Additionally, {deepseek_response}"
        elif claude_response:
            final_alert = claude_response
        elif deepseek_response:
            final_alert = deepseek_response
        else:
            final_alert = f"Alert: {', '.join(breaches)}. Please check the room."

    final_alert = remove_emojis(final_alert)[:400]

    # Polly Synthesis
    try:
        speech = polly.synthesize_speech(Text=final_alert, OutputFormat="mp3", VoiceId="Kajal", Engine="neural")
    except:
        speech = polly.synthesize_speech(Text=final_alert, OutputFormat="mp3", VoiceId="Kajal", Engine="standard")

    audio = speech["AudioStream"].read()

    # S3 Upload
    key = f"alerts/{device_id}/{uuid.uuid4()}.mp3"
    s3.put_object(Bucket=AUDIO_BUCKET, Key=key, Body=audio, ContentType="audio/mpeg")
    audio_url = s3.generate_presigned_url("get_object", Params={"Bucket": AUDIO_BUCKET, "Key": key}, ExpiresIn=300)

    # MQTT & SNS
    payload = {"alert_text": final_alert, "audio_url": audio_url}
    try:
        iot.publish(topic=AUDIO_TOPIC, qos=1, payload=json.dumps(payload))
        sns.publish(
            TopicArn=SNS_TOPIC_ARN, Subject="Smart Room Status" if not breaches else "Smart Room Alert",
            Message=f"Smart Room Report\n\n{final_alert}"
        )
    except Exception as e:
        print("Messaging Error:", e)

    return {"status": "alert_sent", "message": final_alert}