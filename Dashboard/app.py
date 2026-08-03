from flask import Flask, render_template
import boto3
from datetime import datetime
from flask import Flask, render_template, jsonify
from boto3.dynamodb.conditions import Key
from decimal import Decimal

app = Flask(__name__)

table = boto3.resource("dynamodb").Table("room-latest-telemetry")
history_table = boto3.resource("dynamodb").Table("room-telemetry-history")

@app.route("/")
def home():
    response = table.get_item(
        Key={"device_id": "room-pi-01"}
    )

    item = response.get("Item", {})
    ts = item.get("timestamp")

    try:
        formatted_time = datetime.fromtimestamp(int(ts)).strftime("%d %b %Y, %I:%M:%S %p")
    except:
        formatted_time = "--"
    data = {
        "temperature": item.get("temperature_c", "--"),
        "humidity": item.get("humidity_pct", "--"),
        "soil": item.get("soil_moisture_pct", "--"),
        "timestamp": formatted_time
    }

    return render_template("index.html", data=data)

@app.route("/history")
def history():
    response = history_table.query(
        KeyConditionExpression=Key("device_id").eq("room-pi-01"),
        ScanIndexForward=True,
        Limit=50
    )

    items = response.get("Items", [])

    data = []

    for item in items:
        data.append({
            "timestamp": item["timestamp"],
            "temperature": float(item["temperature_c"]),
            "humidity": float(item["humidity_pct"]),
            "soil": int(item["soil_moisture_pct"])
        })

    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
