#!/bin/bash

# One-shot installer for the self-contained LightshowAI chatbot

# Uses existing Conda env: LightshowAI (Python 3.11)

set -euo pipefail

CHATBOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIGHTSHOWAI_DIR="$(cd "${CHATBOT_DIR}/../.." && pwd)"

echo "==> LightshowAI root: ${LIGHTSHOWAI_DIR}"
echo "==> Chatbot dir:      ${CHATBOT_DIR}"
echo "==> Using Conda env:  LightshowAI"

mkdir -p "${HOME}/tmp"

# --- 1. system packages ----------------------------------------------------

echo "==> Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y git build-essential cmake nodejs npm

# --- 2. claude-code CLI ----------------------------------------------------

echo "==> Installing @anthropic-ai/claude-code CLI..."
sudo npm install -g @anthropic-ai/claude-code

# --- 3. activate conda env -------------------------------------------------

echo "==> Activating Conda environment LightshowAI..."

# Load conda into this non-interactive shell

if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
source "$HOME/anaconda3/etc/profile.d/conda.sh"
else
echo "ERROR: Could not find conda.sh. Make sure Conda is installed."
exit 1
fi

conda activate LightshowAI

echo "==> Python version:"
python --version

pip install --upgrade pip wheel

# --- 4. chatbot deps -------------------------------------------------------

echo "==> Installing chatbot requirements..."
pip install -r "${CHATBOT_DIR}/requirements.txt"

# --- 5. LightshowAI package ------------------------------------------------

echo "==> Installing LightshowAI from ${LIGHTSHOWAI_DIR}..."
pip install -e "${LIGHTSHOWAI_DIR}"

# --- 6. .env ---------------------------------------------------------------

if [ ! -f "${CHATBOT_DIR}/.env" ]; then
echo "==> Copying .env.example -> .env (EDIT IT!)"
cp "${CHATBOT_DIR}/.env.example" "${CHATBOT_DIR}/.env"
fi

cat <<EOF

==> Done.

Next steps:

1. Edit ${CHATBOT_DIR}/.env and fill in:
   ANTHROPIC_API_KEY
   MP_API_KEY
   CHAINLIT_PASSWORD
   CLAUDE_MODEL (optional)

2. Open port 8000 in your EC2 security group
   (and 8001 if using plots)

3. Test interactively:
   cd ${CHATBOT_DIR}
   conda activate LightshowAI
   chainlit run app.py -h --host 0.0.0.0 --port 8000

4. Or install as a systemd service (update paths accordingly)

URL: http://<ec2-public-ip>:8000
EOF
