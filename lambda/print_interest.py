import os
import json
import base64
from decimal import Decimal
from datetime import datetime, timezone

import boto3

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://theunending.ai")
TABLE_NAME = os.environ.get("TABLE_NAME", "UnendingPrintInterest")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def build_response(status_code: int, body: dict, request_origin: str = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    # Reflect origin only if it matches the configured allowed origin
    if request_origin == ALLOWED_ORIGIN:
        headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body)
    }


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin")

    # 1. Handle CORS preflight
    http_method = event.get("requestContext", {}).get("http", {}).get("method")
    if http_method == "OPTIONS":
        return build_response(204, {}, request_origin=origin)

    # 2. Origin check
    if origin != ALLOWED_ORIGIN:
        return build_response(403, {"error": "Forbidden: Origin not allowed."}, request_origin=origin)

    # 3. Decode & parse JSON payload
    raw_body = event.get("body", "")
    if event.get("isBase64Encoded", False):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        payload = json.loads(raw_body, parse_float=Decimal)
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object.")
    except (json.JSONDecodeError, ValueError) as err:
        return build_response(400, {"error": f"Invalid JSON payload: {str(err)}"}, request_origin=origin)

    # 4. Dump payload directly to DynamoDB
    aws_request_id = context.aws_request_id
    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        "pk": f"{payload['theme']}#{payload['size']}",
        "sk": f"{timestamp}#{aws_request_id}",
        "request_id": aws_request_id,
        "received_at": timestamp,
        "payload": payload,
    }

    if payload.get("nonce") is not None:
        item["nonce"] = payload["nonce"]
        
    table.put_item(Item=item)

    return build_response(200, {
        "message": "Payload stored successfully.",
        "request_id": aws_request_id
    }, request_origin=origin)
