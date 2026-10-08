"""
Anonymous prompt-idea collector.

Sibling of print_interest.py, but a different problem. That one accepts a
closed vocabulary -- theme and size both come from allowlists -- so the server
can reject anything it does not recognise. Here the payload is free text the
submitter controls, so an allowlist is not available and the controls have to
be different ones:

  - hard caps on every field, applied after cleaning, not before
  - cheap content heuristics (no links, no long runs of one character)
  - an atomic per-nonce daily quota, so one browser cannot fill the table
  - reserved concurrency on the function itself, as the real ceiling

Two things this deliberately does NOT do. It does not try to identify callers:
the Origin check is a filter against casual drive-by traffic, not a security
control, since curl sets whatever Origin it likes. And it never runs, renders
or forwards a submission -- stored rows are inert text for a human to read.

That last point matters more than it looks. These rows are, by construction,
text written by strangers that is intended to be fed to a model. Treat them as
untrusted input anywhere downstream: anything that pipes the table into a
generation pipeline is reading attacker-authored prompts.
"""

import json
import logging
import os
import re
from base64 import b64decode
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://theunending.ai")
TABLE_NAME = os.environ.get("TABLE_NAME", "UnendingPromptIdeas")

MAX_BODY_BYTES = 4096        # the real payload is ~600 bytes
MAX_NAME_CHARS = 60
MAX_PROMPT_CHARS = 256
MIN_PROMPT_CHARS = 12
MAX_CONTACT_CHARS = 120
MAX_SET_CHARS = 48
MAX_PAGE_CHARS = 200

# Soft ceiling per browser per UTC day. The nonce is client-supplied, so this
# stops double-submits and unsophisticated bots, not a determined one. The
# function's reserved concurrency is what actually bounds the blast radius.
DAILY_QUOTA = int(os.environ.get("DAILY_QUOTA", "10"))
QUOTA_TTL_DAYS = 3

URL_RE = re.compile(r"\b(?:https?://|www\.)", re.IGNORECASE)
RUN_RE = re.compile(r"(.)\1{19,}", re.DOTALL)   # 20+ of the same character

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
    """Strip control characters, collapse surrounding space, then truncate.

    Truncating last is deliberate: cleaning can only shorten a string, so a
    caller cannot smuggle extra length past the cap by padding with control
    characters that get removed afterwards.
    """
    if not isinstance(value, str):
        return ""
    value = "".join(ch for ch in value if ch == "\n" or ch >= " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()[:limit]


def validate(payload: dict):
    """Return (item_fields, error). Fails closed."""
    name = clean_text(payload.get("name"), MAX_NAME_CHARS)
    body = clean_text(payload.get("body"), MAX_PROMPT_CHARS)

    if not name:
        return None, "A title is required."
    if len(body) < MIN_PROMPT_CHARS:
        return None, f"The prompt needs at least {MIN_PROMPT_CHARS} characters."
    if URL_RE.search(name) or URL_RE.search(body):
        return None, "Links are not accepted in the title or prompt."
    if RUN_RE.search(name) or RUN_RE.search(body):
        return None, "That does not look like a prompt."

    # Explicit allowlist: these fields are stored and nothing else, so a caller
    # cannot decide what ends up in the table.
    fields = {
        "name": name,
        "body": body,
        "contact": clean_text(payload.get("contact"), MAX_CONTACT_CHARS),
        "set": clean_text(payload.get("set"), MAX_SET_CHARS),
        "page": clean_text(payload.get("page"), MAX_PAGE_CHARS),
        "nonce": clean_text(payload.get("nonce"), 64),
        "client_ts": clean_text(payload.get("ts"), 40),
        "v": payload.get("v") if isinstance(payload.get("v"), int) else None,
    }
    return {k: v for k, v in fields.items() if v not in (None, "")}, None


def within_quota(nonce: str, day: str) -> bool:
    """Atomically increment this browser's counter for the day.

    One conditional update does both the check and the increment, so two
    concurrent requests cannot both read "9" and both write "10".
    """
    if not nonce or DAILY_QUOTA <= 0:
        return True
    expires = int((datetime.now(timezone.utc) + timedelta(days=QUOTA_TTL_DAYS)).timestamp())
    try:
        table().update_item(
            Key={"pk": f"quota#{day}", "sk": nonce},
            UpdateExpression="SET #c = if_not_exists(#c, :zero) + :one, #e = :exp",
            ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
            ExpressionAttributeNames={"#c": "count", "#e": "expires_at"},
            ExpressionAttributeValues={
                ":zero": 0, ":one": 1, ":exp": expires, ":limit": DAILY_QUOTA,
            },
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin")

    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "POST")
    if method == "OPTIONS":
        return respond(204, {}, origin)
    if method != "POST":
        return respond(405, {"error": "Method not allowed."}, origin)

    if origin != ALLOWED_ORIGIN:
        log.info("rejected: origin %r", origin)
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
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return respond(400, {"error": "Invalid JSON."}, origin)
    if not isinstance(payload, dict):
        return respond(400, {"error": "Payload must be a JSON object."}, origin)

    # Honeypot: a filled hidden field means a bot. Look successful, store
    # nothing, so it gets no signal to adapt.
    if clean_text(payload.get("website"), 200):
        log.info("rejected: honeypot")
        return respond(200, {"message": "Received."}, origin)

    fields, error = validate(payload)
    if error:
        log.info("rejected: %s", error)
        return respond(400, {"error": error}, origin)

    received_at = datetime.now(timezone.utc).isoformat()
    day = received_at[:10]

    if not within_quota(fields.get("nonce", ""), day):
        log.info("rejected: quota")
        return respond(429, {"error": "Daily limit reached. Try again tomorrow."}, origin)

    # Partitioned by day rather than by a single constant key: writes spread
    # across partitions as volume grows, and "everything from Tuesday" is a
    # query instead of a scan.
    item = {
        "pk": f"idea#{day}",
        "sk": f"{received_at}#{context.aws_request_id}",
        "request_id": context.aws_request_id,
        "received_at": received_at,
        "payload": fields,
    }

    try:
        table().put_item(Item=item)
    except Exception:
        log.exception("put_item failed")
        return respond(500, {"error": "Could not store that. Please try again."}, origin)

    # Deliberately not logging name, body or contact: contact is personal data
    # and CloudWatch retention is a separate decision from the table's.
    log.info("stored %s has_contact=%s", item["sk"], "contact" in fields)
    return respond(200, {"message": "Received.", "request_id": context.aws_request_id}, origin)
