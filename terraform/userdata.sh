#!/bin/bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

# 1. Update apt and install Docker, Compose V2, ECR Credential Helper, git, curl, tar
apt-get update -y
apt-get install -y \
  docker.io \
  docker-compose-v2 \
  amazon-ecr-credential-helper \
  git \
  curl \
  tar \
  ca-certificates \
  unzip

# 2. install AWS cli
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o "/tmp/awscliv2.zip" \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install --update \
    && rm -rf /tmp/aws /tmp/awscliv2.zip

# 3. Install uv (and uvx) system-wide into /usr/local/bin
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# 4. Install just system-wide into /usr/local/bin
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# 5. Enable Docker and add the 'ubuntu' user to the docker group
usermod -aG docker ubuntu
systemctl enable --now docker

# 6. Configure ECR Credential Helper for the 'ubuntu' user
mkdir -p /home/ubuntu/.docker
echo '{"credsStore": "ecr-login"}' > /home/ubuntu/.docker/config.json
chown -R ubuntu:ubuntu /home/ubuntu/.docker
