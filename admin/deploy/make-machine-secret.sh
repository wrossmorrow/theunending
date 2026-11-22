#!/bin/bash

# Renders the machine (job-system) JWT configuration into envoy.yaml.
#
# The committed admin/deploy/envoy.yaml contains placeholders
# (__MACHINE_JWKS__ and __MACHINE_SA_EMAIL__). This script replaces them with:
#   - the public JWKS derived from the admin service account (private key stays local)
#   - the service account email (iss/sub of the minted tokens)
#
# Renders a pristine envoy.yaml (checked out from git). Re-rendering a rendered
# file fails loudly; restore from git first if the SA rotated.
#
# Usage:
#   set -a && source .env && set +a
#   ./make-machine-secret.sh
#
# Requires GOOGLE_SERVICE_ACCOUNT_KEY_JSON in the environment (or sourced .env).

set -euo pipefail

: "${GOOGLE_SERVICE_ACCOUNT_KEY_JSON:?GOOGLE_SERVICE_ACCOUNT_KEY_JSON must be set (e.g. sourced from .env)}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ENVOY_YAML="${ENVOY_YAML:-${HERE}/envoy.yaml}"

uv run --no-project --with cryptography python3 - "$ENVOY_YAML" <<'PY'
import base64
import json
import os
import sys

from cryptography.hazmat.primitives.serialization import load_pem_private_key

raw = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_KEY_JSON"])
key = load_pem_private_key(raw["private_key"].encode(), password=None)
numbers = key.public_key().public_numbers()


def b64u(i: int) -> str:
    b = i.to_bytes((i.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


jwks = {
    "keys": [
        {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "n": b64u(numbers.n),
            "e": b64u(numbers.e),
        }
    ]
}

email = raw.get("client_email") or raw.get("email")
if not email:
    raise SystemExit("key JSON has no client_email / email")

path = sys.argv[1]
with open(path) as f:
    text = f.read()
if "__MACHINE_JWKS__" not in text:
    raise SystemExit(f"{path} is already rendered (no placeholders). Restore it from git first.")

text = text.replace("__MACHINE_JWKS__", json.dumps(jwks))
text = text.replace("__MACHINE_SA_EMAIL__", email)

with open(path, "w") as f:
    f.write(text)

print(f"rendered {path} (machine subject: {email})")
PY
