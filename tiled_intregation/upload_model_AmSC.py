"""
Upload a LightshowAI XAS model checkpoint to American Science Cloud (MLflow).

Single-file version of the upload cell from model_inference.ipynb.
All configuration is hardcoded below — just run:

    python upload_to_amsc.py
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import urllib.request
import urllib3
from typing import List
from urllib3.exceptions import InsecureRequestWarning

import numpy as np
import torch
from torch import nn
from lightning import LightningModule

import mlflow
import mlflow.pytorch


# ---------------------------------------------------------------------------
# Configuration (edit these if needed)
# ---------------------------------------------------------------------------
ELEMENT = "Ti"
THEORY = "VASP"

CHECKPOINT_PATH = "/home/sairam/LightshowAI/LightshowAI/tiled_intregation/model_checkpoints/xasblock/v1.1.1/V_FEFF.ckpt"

EXPERIMENT_NAME = "xas_ti_vasp"
REGISTERED_MODEL_NAME = "XAS_Ti_VASP"
RUN_NAME = "Manual_Upload"

AMSC_TRACKING_URI = "https://mlflow.american-science-cloud.org"
AMSC_API_KEY = "AgG4qPXXX82mJlpb2g2ogBq0lbkeyy66BVlJWyqzwPnnN16gVXt7CBg494Nv1jbEg9q4yQd5owMNkOu9WBDbnCGoO2VfpYXvVHyD3V1"


# ---------------------------------------------------------------------------
# Checkpoint download configuration
# ---------------------------------------------------------------------------
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/AI-multimodal/LightshowAI/main/model_checkpoints"
)

PARENT_DIRECTORY = pathlib.Path.cwd().resolve()
MODEL_CHECKPOINTS_PATH = PARENT_DIRECTORY / "model_checkpoints"
XASBLOCKS_PATH = MODEL_CHECKPOINTS_PATH / "xasblock" / "v1.1.1"
M3GNET_PATH = MODEL_CHECKPOINTS_PATH / "M3GNet-MP-2021.2.8-PES"

XASBLOCK_FILES = [
    "Co_FEFF.ckpt", "Cr_FEFF.ckpt", "Cu_FEFF.ckpt", "Cu_VASP.ckpt",
    "Fe_FEFF.ckpt", "Mn_FEFF.ckpt", "Ni_FEFF.ckpt", "Ti_FEFF.ckpt",
    "Ti_VASP.ckpt", "V_FEFF.ckpt",
]
M3GNET_FILES = ["LICENSE", "README.md", "model.json", "model.pt", "state.pt"]


def _download_file(url: str, destination: pathlib.Path, overwrite: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        return
    print(f"Downloading {destination.name} ...")
    urllib.request.urlretrieve(url, destination)


def ensure_model_checkpoints(overwrite: bool = False) -> None:
    """Create model folders and download required checkpoint files."""
    XASBLOCKS_PATH.mkdir(parents=True, exist_ok=True)
    M3GNET_PATH.mkdir(parents=True, exist_ok=True)

    for filename in XASBLOCK_FILES:
        _download_file(
            f"{GITHUB_RAW_BASE}/xasblock/v1.1.1/{filename}",
            XASBLOCKS_PATH / filename,
            overwrite=overwrite,
        )
    for filename in M3GNET_FILES:
        _download_file(
            f"{GITHUB_RAW_BASE}/M3GNet-MP-2021.2.8-PES/{filename}",
            M3GNET_PATH / filename,
            overwrite=overwrite,
        )


# ---------------------------------------------------------------------------
# Model definitions (copied from the notebook so state_dict keys line up)
# ---------------------------------------------------------------------------
class XASBlock(nn.Sequential):
    """Simple feed-forward block used by the released checkpoint."""
    DROPOUT = 0.5

    def __init__(self, input_dim: int, hidden_dims: List[int], output_dim: int):
        dims = [input_dim] + hidden_dims + [output_dim]
        layers = []
        for i, (w1, w2) in enumerate(zip(dims[:-1], dims[1:])):
            layers.append(nn.Linear(w1, w2))
            if i < len(dims) - 2:
                layers.append(nn.BatchNorm1d(w2))
                layers.append(nn.SiLU())
                layers.append(nn.Dropout(self.DROPOUT))
            else:
                layers.append(nn.Softplus())
        super().__init__(*layers)


class XASBlockModule(LightningModule):
    """Lightning wrapper around the XAS block checkpoint."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model(x)

    @classmethod
    def load(cls, element: str, spectroscopy_type: str) -> "XASBlockModule":
        path = XASBLOCKS_PATH / f"{element}_{spectroscopy_type}.ckpt"
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        # These dimensions match the published v1.1.1 checkpoint layout.
        model = XASBlock(input_dim=64, hidden_dims=[500, 500, 550], output_dim=141)
        module = cls.load_from_checkpoint(checkpoint_path=str(path), model=model)
        return module


class XASModel(nn.Module):
    """
    High-level wrapper that loads an XAS block checkpoint.

    For *uploading* we only need the XAS block weights, so featurization (M3GNet)
    is skipped. If you need end-to-end inference from the registered model later,
    the notebook version of XASModel includes the featurizer.
    """

    def __init__(self, element: str, spectroscopy_type: str):
        super().__init__()
        self.element = element
        self.spectroscopy_type = spectroscopy_type
        self.model = XASBlockModule.load(
            element=element, spectroscopy_type=spectroscopy_type
        )
        self.model.eval()

    def forward(self, x):
        return self.model(x)


# ---------------------------------------------------------------------------
# AMSC / MLflow setup
# ---------------------------------------------------------------------------
def enable_amsc_x_api_key() -> None:
    """Monkey-patch mlflow's HTTP layer to inject the AMSC X-Api-Key header."""
    import mlflow.utils.rest_utils as rest_utils

    _orig = rest_utils.http_request

    def patched(host_creds, endpoint, method, *args, **kwargs):
        h = dict(kwargs.get("headers") or kwargs.get("extra_headers") or {})
        h["X-Api-Key"] = AMSC_API_KEY
        kwargs["headers" if "headers" in kwargs else "extra_headers"] = h
        return _orig(host_creds, endpoint, method, *args, **kwargs)

    rest_utils.http_request = patched


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def upload_local_model() -> None:
    # 1. Make sure the checkpoint layout exists so XASBlockModule.load can find it.
    ensure_model_checkpoints()

    # 2. Copy the user-supplied checkpoint into the expected location if needed.
    src = pathlib.Path(CHECKPOINT_PATH)
    if not src.exists():
        print(f"ERROR: checkpoint not found: {src}", file=sys.stderr)
        sys.exit(1)

    expected_path = XASBLOCKS_PATH / f"{ELEMENT}_{THEORY}.ckpt"
    if src.resolve() != expected_path.resolve():
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        if expected_path.exists():
            expected_path.unlink()
        shutil.copy2(src, expected_path)
        print(f"Copied checkpoint into {expected_path}")

    # 3. Build the model.
    print(f"Loading XAS model: element={ELEMENT}, theory={THEORY}")
    model = XASModel(element=ELEMENT, spectroscopy_type=THEORY)
    model.eval()

    # 4. Configure MLflow for AMSC.
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    urllib3.disable_warnings(InsecureRequestWarning)
    enable_amsc_x_api_key()
    mlflow.set_tracking_uri(AMSC_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    # 5. Log + register.
    with mlflow.start_run(run_name=RUN_NAME) as run:
        print("Uploading local model to MLflow...")
        mlflow.pytorch.log_model(
            pytorch_model=model,
            artifact_path="model",
            registered_model_name=REGISTERED_MODEL_NAME,
        )
        print(f"Successfully uploaded. Run ID: {run.info.run_id}")
        print(f"Registered model name: {REGISTERED_MODEL_NAME}")


if __name__ == "__main__":
    upload_local_model()