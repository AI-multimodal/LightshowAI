#!/bin/bash -e
# One-shot installer for the LightshowAI chatbot on Linux.
#
# Expected layout (everything under one folder, no broader repo needed):
#   <root>/lightshowai/        -- the python package
#   <root>/model_checkpoints/  -- baked OmniXAS .ckpt files
#   <root>/mcp/                -- materials_project + lightshowai MCP servers
#   <root>/aws/chatbot/        -- this app
#
# Prerequisites: apt-based Linux + conda (miniconda / anaconda)
# Run from anywhere; all paths resolve relative to this script.

set -euo pipefail

CHATBOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIGHTSHOWAI_DIR="$(cd "${CHATBOT_DIR}/../.." && pwd)"
CONDA_ENV_NAME="LightshowAI"

echo "==> LightshowAI root: ${LIGHTSHOWAI_DIR}"
echo "==> Chatbot dir:      ${CHATBOT_DIR}"
echo "==> Conda env:        ${CONDA_ENV_NAME}"

mkdir -p "${HOME}/tmp"

# --- 1. system packages ----------------------------------------------------
echo "==> Installing/checking Linux system packages..."
sudo apt-get update -y
sudo apt-get install -y git build-essential nodejs npm

# --- 2. claude-code CLI (claude_agent_sdk runtime dependency) --------------
echo "==> Installing @anthropic-ai/claude-code CLI..."
sudo npm install -g @anthropic-ai/claude-code

# --- 3. Create / reuse conda environment -----------------------------------
echo "==> Setting up conda environment '${CONDA_ENV_NAME}'..."
# Initialise conda in this shell without requiring the user's .bashrc to be
# sourced (works even when running via `bash setup.sh`).
CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [ -z "${CONDA_BASE}" ]; then
    if [ -d "${HOME}/miniconda3" ]; then
        CONDA_BASE="${HOME}/miniconda3"
    elif [ -d "${HOME}/anaconda3" ]; then
        CONDA_BASE="${HOME}/anaconda3"
    else
        echo "ERROR: Could not find Conda. Install Miniconda/Anaconda and rerun."
        exit 1
    fi
fi

# shellcheck disable=SC1091
source "${CONDA_BASE}/etc/profile.d/conda.sh"

if conda env list | awk '{print $1}' | grep -qx "${CONDA_ENV_NAME}"; then
    echo "    Conda env '${CONDA_ENV_NAME}' already exists, reusing."
else
    echo "    Creating new conda env '${CONDA_ENV_NAME}' with Python 3.11..."
    conda create -y -n "${CONDA_ENV_NAME}" python=3.11
fi

conda activate "${CONDA_ENV_NAME}"

# --- 4. Native/scientific deps from conda-forge ----------------------------
echo "==> Installing cmake<3.27 via conda-forge (required for boltztrap2)..."
conda install -y -c conda-forge "cmake<3.27"

echo "==> Installing boltztrap2 via conda-forge (pre-built, no source build)..."
conda install -y -c conda-forge boltztrap2

echo "==> Installing numba + llvmlite via conda-forge (pre-built binaries)..."
conda install -y -c conda-forge numba llvmlite

# --- 5. chatbot Python deps ------------------------------------------------
echo "==> Installing chatbot requirements..."
pip install --upgrade pip wheel
export PIP_PREFER_BINARY=1
pip install -r "${CHATBOT_DIR}/requirements.txt"

# --- 6. LightshowAI package (editable, picks up local model checkpoints) ---
echo "==> Installing LightshowAI from ${LIGHTSHOWAI_DIR}..."
# boltztrap2 is already satisfied by conda, so pip won't try to build it.
pip install -e "${LIGHTSHOWAI_DIR}"

# --- 7. .env ---------------------------------------------------------------
if [ ! -f "${CHATBOT_DIR}/.env" ]; then
    echo "==> Copying .env.example -> .env (EDIT IT!)"
    cp "${CHATBOT_DIR}/.env.example" "${CHATBOT_DIR}/.env"
fi

cat <<EOF

==> Done.

Next steps:
  1. Edit ${CHATBOT_DIR}/.env and fill in:
       ANTHROPIC_AUTH_TOKEN     (required for AmSC i2 gateway)
       ANTHROPIC_API_KEY        (alternative for direct Anthropic)
       MP_API_KEY               (required)
       AM_SC_API_KEY            (required for MLflow tracking)
       CHAINLIT_PASSWORD        (recommended)
       ANTHROPIC_MODEL          (optional; default claude-sonnet-4-6)

  2. Activate the conda env and start Chainlit:
       conda activate ${CONDA_ENV_NAME}
       cd ${CHATBOT_DIR}
       env -u DEBUG chainlit run app.py -h --host 0.0.0.0 --port 8000

  3. Open http://localhost:8000 in your browser, or use Apache at:
       https://localhost:8445/

  4. For inline XANES plots to render, start the static plot server in a
     second terminal:
       conda activate ${CONDA_ENV_NAME}
       cd ${LIGHTSHOWAI_DIR}
       python -m http.server 8001 --directory ~/tmp
     (PLOTS_PUBLIC_URL in .env should be http://localhost:8001)

Notes:
  - boltztrap2, numba, and llvmlite were installed via conda-forge to avoid
    fragile local source builds.
  - The cmake installed in the conda env shadows the system cmake only inside
    the activated conda env; your system cmake is untouched.
EOF
