import os
import time
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])
history_table = dynamodb.Table("room-telemetry-history")


def lambda_handler(event, context):
    try:
        item = {
            "device_id": event["device_id"],
            "temperature_c": Decimal(str(event["temperature_c"])),
            "humidity_pct": Decimal(str(event["humidity_pct"])),
            "soil_moisture_pct": int(event["soil_moisture_pct"]),
            "soil_moisture_raw": int(event["soil_moisture_raw"]),
            "timestamp": int(event.get("ts", time.time()))
        }

        table.put_item(Item=item)
        history_table.put_item(Item=item)

        print(f"Updated telemetry for {item['device_id']}")

        return {
            "statusCode": 200,
            "body": "Telemetry updated successfully"
        }

    except Exception as e:
        print(f"Error: {e}")
        raise