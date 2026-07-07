# Smart-Room-Environment-Monitor-with-AI-Voice-Alerts
To develop a scalable, cloud connected smart room monitoring solution that combines IoT, edge computing, AI, and voice interaction to provide real time environmental awareness and intelligent user assistance. The architecture is designed to be easily extensible for smart home, healthcare and industrial monitoring applications.

DHT22 Sensor
      ->
Raspberry Pi Zero W
      ->
AWS IoT Core (MQTT)
      ->
AWS Lambda
      ->
Amazon Bedrock (Claude + DeepSeek)
      ->
Amazon Polly
      ->
AWS IoT Core (Audio Topic)
      ->
Raspberry Pi
      ->
Speaker
