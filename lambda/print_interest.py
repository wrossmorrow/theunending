"""
Anonymous poster-interest collector.

Public endpoint, no auth: a Lambda Function URL anyone can POST to. The
safety posture is therefore (a) bound what a caller can make us store, and
(b) fail closed on anything unrecognised -- not (c) try to identify callers.

Note on the Origin check: it is a cheap filter, NOT a security control.
CORS is enforced by browsers, so `curl -H "Origin: https://theunending.ai"`
walks straight through it. The controls that actually bound abuse here are
the field allowlist, the size caps, and the Lambda's reserved concurrency.
"""

import json
import logging
import os
import re
from base64 import b64decode
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://theunending.ai")
TABLE_NAME = os.environ.get("TABLE_NAME", "UnendingPrintInterest")

# Comma-separated allowlists. Leave either unset to skip that membership check
# and fall back to the format check below -- so a new set does not 400 before
# the env var catches up, but a scanner still cannot invent partition keys.
ALLOWED_THEMES = {t.strip() for t in os.environ.get("ALLOWED_THEMES", "").split(",") if t.strip()}
ALLOWED_SIZES = {s.strip() for s in os.environ.get("ALLOWED_SIZES", "").split(",") if s.strip()}

# Shapes we are willing to use as part of a partition key.
THEME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}$")
SIZE_RE = re.compile(r"^[0-9]{1,3}x[0-9]{1,3}$")

MAX_BODY_BYTES = 4096        # the real payload is ~300 bytes
MAX_NOTE_CHARS = 240         # matches the client's maxlength
MAX_COST = Decimal("100000")

_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


def respond(status: int, body: dict, origin: str = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
    }
    if origin == ALLOWED_ORIGIN:
        headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    return {"statusCode": status, "headers": headers, "body": json.dumps(body)}


def clean_text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    # strip control characters; they have no business in a free-text note
    value = "".join(ch for ch in value if ch == "\n" or ch >= " ")
    return value.strip()[:limit]


def clean_cost(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not cost.is_finite() or cost < 0 or cost > MAX_COST:
        return None
    return cost


def validate(payload: dict):
    """Return (item_fields, error). Fails closed."""
    theme = payload.get("theme")
    size = payload.get("size")

    if not isinstance(theme, str) or not isinstance(size, str):
        return None, "theme and size are required strings"
    if not THEME_RE.match(theme):
        return None, "theme is not a recognised identifier"
    if not SIZE_RE.match(size):
        return None, "size is not a recognised identifier"
    if ALLOWED_THEMES and theme not in ALLOWED_THEMES:
        return None, "unknown theme"
    if ALLOWED_SIZES and size not in ALLOWED_SIZES:
        return None, "unknown size"

    # Explicit allowlist: we store these fields and nothing else, so a caller
    # cannot decide what ends up in the table.
    fields = {
        "theme": theme,
        "size": size,
        "note": clean_text(payload.get("note"), MAX_NOTE_CHARS),
        "page": clean_text(payload.get("page"), 200),
        "nonce": clean_text(payload.get("nonce"), 64),
        "currency": clean_text(payload.get("currency"), 8),
        "client_ts": clean_text(payload.get("ts"), 40),
        "v": payload.get("v") if isinstance(payload.get("v"), int) else None,
    }
    cost = clean_cost(payload.get("cost"))
    if cost is not None:
        fields["cost"] = cost
    return {k: v for k, v in fields.items() if v not in (None, "")}, None


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin")

    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "POST")
    if method == "OPTIONS":
        return respond(204, {}, origin)
    if method != "POST":
        return respond(405, {"error": "Method not allowed."}, origin)

    if origin != ALLOWED_ORIGIN:
        return respond(403, {"error": "Forbidden."}, origin)

    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = b64decode(raw).decode("utf-8")
        except Exception:
            return respond(400, {"error": "Undecodable body."}, origin)

    # cap before parsing: a 6MB Function URL payload should not reach json.loads
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        return respond(413, {"error": "Payload too large."}, origin)

    try:
        payload = json.loads(raw, parse_float=Decimal)
    except (json.JSONDecodeError, ValueError):
        return respond(400, {"error": "Invalid JSON."}, origin)
    if not isinstance(payload, dict):
        return respond(400, {"error": "Payload must be a JSON object."}, origin)

    # Honeypot: a filled hidden field means a bot. Look successful, store nothing,
    # so it gets no signal to adapt. Harmless when the client omits the field.
    if clean_text(payload.get("website"), 200):
        log.info("rejected: honeypot")
        return respond(200, {"message": "Received."}, origin)

    fields, error = validate(payload)
    if error:
        log.info("rejected: %s", error)
        return respond(400, {"error": error}, origin)

    received_at = datetime.now(timezone.utc).isoformat()
    item = {
        "pk": f"{fields['theme']}#{fields['size']}",
        "sk": f"{received_at}#{context.aws_request_id}",
        "request_id": context.aws_request_id,
        "received_at": received_at,
        "payload": fields,
    }
    if "nonce" in fields:
        item["nonce"] = fields["nonce"]

    try:
        table().put_item(Item=item)
    except Exception:
        log.exception("put_item failed")
        return respond(500, {"error": "Could not store that. Please try again."}, origin)

    log.info("stored %s", item["pk"])
    return respond(200, {"message": "Received.", "request_id": context.aws_request_id}, origin)
