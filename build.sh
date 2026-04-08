#!/bin/bash
set -e

pip install -r requirements.txt

# Install Japanese fonts for rich menu image generation
apt-get install -y fonts-noto-cjk 2>/dev/null || true
fc-cache -f 2>/dev/null || true
