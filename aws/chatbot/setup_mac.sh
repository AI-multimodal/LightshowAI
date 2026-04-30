#!/bin/bash -e
# One-shot installer for the LightshowAI chatbot on macOS (Apple Silicon / M1+).
#
# Expected layout (everything under one folder, no broader repo needed):
#   <root>/lightshowai/        -- the python package
#   <root>/model_checkpoints/  -- baked OmniXAS .ckpt files
#   <root>/mcp/                -- materials_project + lightshowai MCP servers
#   <root>/aws/chatbot/        -- this app
#
# Prerequisites: Homebrew (https://brew.sh) + conda (miniconda / anaconda)
# Run from anywhere; all paths resolve relative to this script.

set -euo pipefail

CHATBOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIGHTSHOWAI_DIR="$(cd "${CHATBOT_DIR}/../.." && pwd)"
CONDA_ENV_NAME="LightshowAI"

echo "==> LightshowAI root: ${LIGHTSHOWAI_DIR}"
echo "==> Chatbot dir:      ${CHATBOT_DIR}"
echo "==> Conda env:        ${CONDA_ENV_NAME}"

# --- 1. Homebrew system packages -------------------------------------------
echo "==> Installing/checking Homebrew packages..."
# Install cmake < 3.27 to avoid boltztrap2 CMakeLists minimum_required issue.
# Homebrew's latest cmake (>=3.27) removed cmake<3.5 compatibility; conda-forge
# ships a sufficiently old cmake that still works.
brew install node || true     # node/npm for @anthropic-ai/claude-code

# --- 2. claude-code CLI (claude_agent_sdk runtime dependency) --------------
echo "==> Installing @anthropic-ai/claude-code CLI..."
npm install -g @anthropic-ai/claude-code

# --- 3. Create / reuse conda environment -----------------------------------
echo "==> Setting up conda environment '${CONDA_ENV_NAME}'..."
# Initialise conda in this shell without requiring the user's .bashrc to be
# sourced (works even when running via `bash setup_mac.sh`).
CONDA_BASE="$(conda info --base 2>/dev/null || echo "${HOME}/opt/anaconda3")"
# shellcheck disable=SC1091
source "${CONDA_BASE}/etc/profile.d/conda.sh"

if conda env list | grep -q "^${CONDA_ENV_NAME}\s"; then
    echo "    Conda env '${CONDA_ENV_NAME}' already exists, reusing."
else
    echo "    Creating new conda env '${CONDA_ENV_NAME}' with Python 3.11..."
    conda create -y -n "${CONDA_ENV_NAME}" python=3.11
fi

conda activate "${CONDA_ENV_NAME}"

# --- 4. Install cmake via conda-forge (avoids system cmake>=3.27 conflict) -
echo "==> Installing cmake<3.27 via conda-forge (required for boltztrap2)..."
conda install -y -c conda-forge "cmake<3.27"

# --- 5. Install boltztrap2 via conda-forge (avoids source build entirely) --
echo "==> Installing boltztrap2 via conda-forge (pre-built, no cmake needed)..."
conda install -y -c conda-forge boltztrap2

# --- 6. Install numba/llvmlite via conda-forge (avoid LLVM source builds) ---
echo "==> Installing numba + llvmlite via conda-forge (pre-built binaries)..."
# llvmlite source builds require an LLVM CMake package config (LLVMConfig.cmake),
# which is often missing on macOS. Installing pre-built conda packages avoids this.
conda install -y -c conda-forge numba llvmlite

# --- 7. chatbot Python deps ------------------------------------------------
echo "==> Installing chatbot requirements..."
pip install --upgrade pip wheel
export PIP_PREFER_BINARY=1
pip install -r "${CHATBOT_DIR}/requirements.txt"

# --- 8. LightshowAI package (editable, picks up local model checkpoints) ---
echo "==> Installing LightshowAI from ${LIGHTSHOWAI_DIR}..."
# boltztrap2 is already satisfied by conda, so pip won't try to build it.
pip install -e "${LIGHTSHOWAI_DIR}"

# --- 9. .env ---------------------------------------------------------------
if [ ! -f "${CHATBOT_DIR}/.env" ]; then
    echo "==> Copying .env.example -> .env (EDIT IT!)"
    cp "${CHATBOT_DIR}/.env.example" "${CHATBOT_DIR}/.env"
fi

cat <<EOF

==> Done.

Next steps:
  1. Edit ${CHATBOT_DIR}/.env and fill in:
       ANTHROPIC_AUTH_TOKEN     (required — your AmSC i2 gateway key)
       MP_API_KEY               (required)
       AM_SC_API_KEY            (required — MLflow tracking)
       CHAINLIT_PASSWORD        (recommended)
       ANTHROPIC_MODEL          (optional; default claude-sonnet-4-6)

  2. Activate the conda env and start Chainlit:
       conda activate ${CONDA_ENV_NAME}
       cd ${CHATBOT_DIR}
       chainlit run app.py -h --host 0.0.0.0 --port 8000

  3. Open http://localhost:8000 in your browser.

  4. For inline XANES plots to render, start the static plot server in a
     second terminal:
       conda activate ${CONDA_ENV_NAME}
       cd ${LIGHTSHOWAI_DIR}
       python -m http.server 8001 --directory /tmp/lightshowai_plots
     (PLOTS_PUBLIC_URL in .env should be http://localhost:8001)

Notes:
  - boltztrap2 was installed via conda-forge to avoid the macOS cmake build
    issue (CMakeLists minimum_required < 3.5 incompatible with cmake >= 3.27).
  - The cmake installed in the conda env shadows the Homebrew cmake only
    inside the activated conda env; your system cmake is untouched.
EOF
