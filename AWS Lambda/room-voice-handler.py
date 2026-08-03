import base64
import json
import os
import re
import time
import urllib3
import boto3
from boto3.dynamodb.conditions import Key

# AWS Clients
s3 = boto3.client("s3")
transcribe = boto3.client("transcribe")
dynamodb = boto3.resource("dynamodb")
polly = boto3.client("polly")
iot = boto3.client("iot-data")

# Environment Variables
BUCKET_NAME = os.environ["BUCKET_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]
UPLOAD_PREFIX = os.environ["UPLOAD_PREFIX"]
AUDIO_TOPIC = os.environ.get("AUDIO_TOPIC", "room/alerts/audio")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# DynamoDB Tables
table = dynamodb.Table(TABLE_NAME)
telemetry_table = dynamodb.Table("room-latest-telemetry")

http = urllib3.PoolManager()

# CORE FUNCTIONS

def save_chunk(query_id, chunk_no, total_chunks, audio_chunk):
    table.put_item(Item={"query_id": query_id, "chunk": chunk_no, "total_chunks": total_chunks, "audio": audio_chunk})

def get_chunks(query_id):
    response = table.query(KeyConditionExpression=Key("query_id").eq(query_id))
    items = sorted(response.get("Items", []), key=lambda x: int(x["chunk"]))
    return items

def delete_chunks(query_id):
    items = get_chunks(query_id)
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"query_id": item["query_id"], "chunk": item["chunk"]})

def reconstruct_audio(query_id, items):
    if not items: raise Exception("No audio chunks found.")
    encoded_audio = "".join(item["audio"] for item in items)
    audio_bytes = base64.b64decode(encoded_audio)
    wav_path = f"/tmp/{query_id}.wav"
    with open(wav_path, "wb") as f: f.write(audio_bytes)
    return wav_path

def upload_to_s3(query_id, wav_path):
    key = f"{UPLOAD_PREFIX}/{query_id}.wav"
    s3.upload_file(wav_path, BUCKET_NAME, key)
    return key

def start_transcription_job(query_id):
    job_name = f"voice-{query_id}"
    transcribe.start_transcription_job(TranscriptionJobName=job_name, Media={"MediaFileUri": f"s3://{BUCKET_NAME}/{UPLOAD_PREFIX}/{query_id}.wav"}, MediaFormat="wav", LanguageCode="en-US")
    print(f"Started Transcribe Job: {job_name}")
    return job_name

def cleanup(query_id, wav_path):
    try: delete_chunks(query_id)
    except Exception as e: print(f"Warning: Failed to delete DynamoDB records for {query_id}: {e}")
    try:
        if os.path.exists(wav_path): os.remove(wav_path)
    except Exception as e: print(f"Warning: Failed to remove temp WAV file {wav_path}: {e}")

# SENSOR & INTENT LOGIC

def get_latest_telemetry():
    try:
        response = telemetry_table.get_item(Key={"device_id": "room-pi-01"})
        return response.get("Item")
    except Exception as e:
        print(f"Error fetching telemetry: {e}")
        return None

def handle_sensor_query(transcript):
    text = transcript.lower()
    data = get_latest_telemetry()
    if not data: return None

    # Temperature Query (Includes 'hot')
    if "temperature" in text or "hot" in text:
        return f"The current temperature is {data.get('temperature_c', 'N/A')} degrees Celsius."

    # Humidity Query
    if "humidity" in text:
        return f"The current humidity is {data.get('humidity_pct', 'N/A')} percent."

    # Watering/Plant Logic
    if "water" in text or "plant" in text or "soil" in text or "moisture" in text:
        moisture = int(data.get("soil_moisture_pct", 0))
        if "water" in text or "plant" in text:
            return "Yes. The soil moisture is low. You should water the plant." if moisture < 30 else "The soil moisture is sufficient. Watering is not required right now."
        return f"The soil moisture is {moisture} percent."

    # Room Status (Expanded)
    if (
        "room status" in text
        or "how is my room" in text
        or "how's my room" in text
        or "how is the room" in text
        or "how's the room" in text
    ):
        return f"The room temperature is {data.get('temperature_c', 'N/A')} degrees Celsius, humidity is {data.get('humidity_pct', 'N/A')} percent, and soil moisture is {data.get('soil_moisture_pct', 'N/A')} percent."
    
    return None

# EXISTING HELPERS & AI LOGIC

def remove_emojis(text):
    emoji_pattern = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+", flags=re.UNICODE)
    return emoji_pattern.sub(r"", text).strip()

def wait_for_transcription(job_name, max_wait_seconds=60):
    start_time = time.time()

    while time.time() - start_time < max_wait_seconds:

        response = transcribe.get_transcription_job(
            TranscriptionJobName=job_name
        )

        status = response["TranscriptionJob"]["TranscriptionJobStatus"]
        print(f"Transcribe status: {status}")
        
        if status == "COMPLETED":
            print(f"Transcribe completed in {time.time()-start_time:.2f} sec")
            return response["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]

        elif status == "FAILED":
            raise Exception(
                f"Transcribe job failed: {response['TranscriptionJob'].get('FailureReason','Unknown')}"
            )

        time.sleep(0.2)

    raise TimeoutError(f"Transcribe job {job_name} timed out.")

def get_transcript_text(transcript_uri):
    response = http.request("GET", transcript_uri)
    if response.status != 200: raise Exception("Failed to download transcript JSON")
    return json.loads(response.data.decode("utf-8"))["results"]["transcripts"][0]["transcript"]

def generate_ai_response(transcript):
    prompt = f"You are a smart room assistant. Answer briefly and naturally.\n\nQuestion:\n{transcript}"
    try: return ask_claude(prompt)
    except Exception as e:
        print(f"Claude error ({e}). Falling back to DeepSeek...")
        try: return ask_deepseek(prompt)
        except Exception as ds_e:
            print(f"DeepSeek error: {ds_e}")
            return "I heard your query, but I had trouble reaching my primary intelligence servers."

def ask_claude(prompt):
    headers = {"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    payload = {"model": CLAUDE_MODEL, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]}
    res = http.request("POST", "https://api.anthropic.com/v1/messages", headers=headers, body=json.dumps(payload))
    
    if res.status == 200:
        return json.loads(res.data.decode("utf-8"))["content"][0]["text"].strip()
    
    raise Exception(f"Claude API HTTP {res.status}: {res.data.decode('utf-8')}")

def ask_deepseek(prompt):
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": DEEPSEEK_MODEL, "messages": [{"role": "system", "content": "You are a smart room assistant."}, {"role": "user", "content": prompt}], "max_tokens": 300}
    res = http.request("POST", "https://api.deepseek.com/chat/completions", headers=headers, body=json.dumps(payload))
    
    if res.status == 200:
        return json.loads(res.data.decode("utf-8"))["choices"][0]["message"]["content"].strip()
        
    raise Exception(f"DeepSeek API HTTP {res.status}: {res.data.decode('utf-8')}")

def text_to_speech(text):
    clean_text = remove_emojis(text)
    try: response = polly.synthesize_speech(Text=clean_text, OutputFormat="mp3", VoiceId="Kajal", Engine="neural")
    except polly.exceptions.EngineNotSupportedException:
        print("Polly neural engine unsupported. Falling back to standard...")
        response = polly.synthesize_speech(Text=clean_text, OutputFormat="mp3", VoiceId="Kajal", Engine="standard")
    return base64.b64encode(response["AudioStream"].read()).decode("utf-8")

def publish_audio_response(response_text, audio_b64):
    iot.publish(topic=AUDIO_TOPIC, qos=1, payload=json.dumps({"response_text": response_text, "audio_b64": audio_b64}))
    print(f"Published to {AUDIO_TOPIC}")

# MAIN LAMBDA HANDLER

def lambda_handler(event, context):
    query_id, chunk, total_chunks, audio = event["query_id"], int(event["chunk"]), int(event["total_chunks"]), event["audio"]
    save_chunk(query_id, chunk, total_chunks, audio)
    items = get_chunks(query_id)
    if len(items) < total_chunks: return {"statusCode": 200, "body": "Pending chunks..."}

    wav_path = None
    try:
        wav_path = reconstruct_audio(query_id, items)

        t = time.time()
        upload_to_s3(query_id, wav_path)
        print(f"S3 Upload: {time.time()-t:.2f}s")

        t = time.time()
        job_name = start_transcription_job(query_id)
        print(f"Start Transcribe API: {time.time()-t:.2f}s")

        t = time.time()
        transcript_uri = wait_for_transcription(job_name)
        print(f"Transcribe: {time.time()-t:.2f}s")

        t = time.time()
        transcript = get_transcript_text(transcript_uri)
        print(f"Transcript Download: {time.time()-t:.2f}s")

        t = time.time()
        ai_response = handle_sensor_query(transcript)
        if ai_response is None:
            ai_response = generate_ai_response(transcript)
        print(f"AI/Sensor Logic: {time.time()-t:.2f}s")

        t = time.time()
        audio_b64 = text_to_speech(ai_response)
        print(f"Polly TTS: {time.time()-t:.2f}s")

        t = time.time()
        publish_audio_response(ai_response, audio_b64)
        print(f"MQTT Publish: {time.time()-t:.2f}s")

        cleanup(query_id, wav_path)

        return {
            "statusCode": 200,
            "body": "Success"
        }
    except Exception as e:
        if wav_path: cleanup(query_id, wav_path)
        return {"statusCode": 500, "body": str(e)}