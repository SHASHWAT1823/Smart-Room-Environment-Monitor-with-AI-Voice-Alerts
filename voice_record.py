import pyaudio
import wave

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
RECORD_SECONDS = 5
OUTPUT = "query.wav"

audio = pyaudio.PyAudio()

stream = audio.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK
)

print("🎤 Recording... Speak now")

frames = []

for _ in range(int(RATE / CHUNK * RECORD_SECONDS)):
    frames.append(stream.read(CHUNK, exception_on_overflow=False))

print("✅ Recording complete")

stream.stop_stream()
stream.close()
audio.terminate()

wf = wave.open(OUTPUT, "wb")
wf.setnchannels(CHANNELS)
wf.setsampwidth(audio.get_sample_size(FORMAT))
wf.setframerate(RATE)
wf.writeframes(b"".join(frames))
wf.close()

print("Saved as", OUTPUT)
