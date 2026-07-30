import subprocess
import os

OUTPUT = "query.wav"

print("🎤 Speak for 5 seconds...")

subprocess.run([
    "arecord",
    "-D", "plughw:1,0",
    "-f", "S16_LE",
    "-r", "16000",
    "-c", "1",
    "-d", "5",
    OUTPUT
], check=True)

print(f"✅ Recording saved as {OUTPUT}")

print("File size:", os.path.getsize(OUTPUT), "bytes")
