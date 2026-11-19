#!/bin/bash

set -a && source .env && set +a

mkdir -p /etc/envoy/secrets
chmod 755 /etc/envoy/secrets

tee /etc/envoy/secrets/token-secret.yaml > /dev/null <<EOF
resources:
  - "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
    name: token
    generic_secret:
      secret:
        inline_string: "${GCP_OAUTH_CLIENT_SECRET}"
EOF

tee /etc/envoy/secrets/hmac-secret.yaml > /dev/null <<EOF
resources:
  - "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
    name: hmac
    generic_secret:
      secret:
        inline_string: "$(openssl rand -hex 32)"
EOF

chmod 644 /etc/envoy/secrets/*.yaml
