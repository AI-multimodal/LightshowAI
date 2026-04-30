#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import mlflow
from mlflow.entities import ViewType
from mlflow.tracking import MlflowClient
from mcp.server.fastmcp import FastMCP


AMSC_API_KEY_ENV = "AM_SC_API_KEY"
DEFAULT_TRACKING_URI = "https://mlflow.american-science-cloud.org"
DEFAULT_MAX_RESULTS = 20


# ── helpers ───────────────────────────────────────────────────────────────────

def load_examples_env():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def configure_insecure_tls_warnings():
    insecure = os.environ.get("MLFLOW_TRACKING_INSECURE_TLS", "").strip().lower() in {"1", "true", "yes", "on"}
    if not insecure:
        return
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning
    urllib3.disable_warnings(InsecureRequestWarning)


def enable_amsc_x_api_key():
    if AMSC_API_KEY_ENV not in os.environ:
        return
    import mlflow.utils.rest_utils as rest_utils
    api_key = os.environ[AMSC_API_KEY_ENV]
    original_http_request = rest_utils.http_request

    def patched(host_creds, endpoint, method, *args, **kwargs):
        headers = dict(kwargs.get("extra_headers") or {})
        if kwargs.get("headers") is not None:
            headers.update(dict(kwargs["headers"]))
        headers["X-Api-Key"] = api_key
        kwargs["extra_headers"] = headers
        kwargs.pop("headers", None)
        return original_http_request(host_creds, endpoint, method, *args, **kwargs)

    rest_utils.http_request = patched


def parse_experiment_ids(experiment_names_csv: str) -> list[str]:
    client = MlflowClient()
    names = [n.strip() for n in experiment_names_csv.split(",") if n.strip()]
    if not names:
        return []
    ids = []
    for name in names:
        exp = client.get_experiment_by_name(name)
        if exp:
            ids.append(exp.experiment_id)
    return ids


def run_to_dict(run) -> dict:
    return {
        "run_id": run.info.run_id,
        "run_name": run.data.tags.get("mlflow.runName"),
        "status": run.info.status,
        "experiment_id": run.info.experiment_id,
        "start_time": run.info.start_time,
        "end_time": run.info.end_time,
        "metrics": dict(run.data.metrics),
        "params": dict(run.data.params),
        "tags": dict(run.data.tags),
    }


def experiment_to_dict(exp) -> dict:
    return {
        "experiment_id": exp.experiment_id,
        "name": exp.name,
        "lifecycle_stage": exp.lifecycle_stage,
        "artifact_location": exp.artifact_location,
        "creation_time": getattr(exp, "creation_time", None),
        "last_update_time": getattr(exp, "last_update_time", None),
    }


def model_version_to_dict(mv) -> dict:
    return {
        "name": mv.name,
        "version": mv.version,
        "status": mv.status,
        "current_stage": getattr(mv, "current_stage", None),
        "run_id": mv.run_id,
        "source": mv.source,
        "description": mv.description,
        "creation_timestamp": mv.creation_timestamp,
        "last_updated_timestamp": mv.last_updated_timestamp,
        "aliases": getattr(mv, "aliases", []),
        "tags": {t.key: t.value for t in (mv.tags or [])},
    }


def registered_model_to_dict(rm) -> dict:
    return {
        "name": rm.name,
        "description": rm.description,
        "creation_timestamp": rm.creation_timestamp,
        "last_updated_timestamp": rm.last_updated_timestamp,
        "latest_versions": [model_version_to_dict(mv) for mv in (rm.latest_versions or [])],
        "tags": {t.key: t.value for t in (rm.tags or [])},
    }


def parse_view_type(view_type: str) -> ViewType:
    value = (view_type or "").strip().lower()
    if value == "all":
        return ViewType.ALL
    if value == "deleted_only":
        return ViewType.DELETED_ONLY
    return ViewType.ACTIVE_ONLY


def effective_max_results(max_results: int) -> int:
    if max_results and max_results > 0:
        return max_results
    return int(os.environ.get("MLFLOW_MCP_MAX_RESULTS", str(DEFAULT_MAX_RESULTS)))


# ── startup ───────────────────────────────────────────────────────────────────

load_examples_env()
os.environ.setdefault("MLFLOW_TRACKING_INSECURE_TLS", "false")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "10")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
configure_insecure_tls_warnings()
enable_amsc_x_api_key()
mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI))

mcp = FastMCP("mlflow-amsc")


# ── read: experiments & runs ──────────────────────────────────────────────────

@mcp.tool()
def list_experiments(max_results: int = DEFAULT_MAX_RESULTS, view_type: str = "active_only") -> list[dict]:
    """List MLflow experiments.

    Args:
        max_results: Max experiments to return.
        view_type: active_only | deleted_only | all
    """
    client = MlflowClient()
    exps = client.search_experiments(
        view_type=parse_view_type(view_type),
        max_results=effective_max_results(max_results),
    )
    return [experiment_to_dict(exp) for exp in exps]


@mcp.tool()
def get_experiment(experiment_name: str) -> dict:
    """Get a single experiment by name."""
    client = MlflowClient()
    exp = client.get_experiment_by_name(experiment_name)
    if exp is None:
        return {"error": f"Experiment not found: {experiment_name}"}
    return experiment_to_dict(exp)


@mcp.tool()
def list_runs(
    experiment_names_csv: str = "",
    filter_string: str = "",
    max_results: int = DEFAULT_MAX_RESULTS,
    order_by: str = "attributes.start_time DESC",
) -> list[dict]:
    """List runs from experiments.

    Args:
        experiment_names_csv: Comma-separated experiment names. Empty uses all active experiments.
        filter_string: MLflow run filter expression.
        max_results: Max runs to return.
        order_by: Single MLflow order expression.
    """
    client = MlflowClient()
    experiment_ids = parse_experiment_ids(experiment_names_csv)
    if not experiment_ids:
        experiment_ids = [
            e.experiment_id
            for e in client.search_experiments(view_type=ViewType.ACTIVE_ONLY, max_results=1000)
        ]

    runs = client.search_runs(
        experiment_ids=experiment_ids,
        filter_string=filter_string,
        max_results=effective_max_results(max_results),
        run_view_type=ViewType.ACTIVE_ONLY,
        order_by=[order_by] if order_by else None,
    )
    return [run_to_dict(r) for r in runs]


@mcp.tool()
def get_run(run_id: str) -> dict:
    """Get details for a single MLflow run by run_id."""
    client = MlflowClient()
    run = client.get_run(run_id)
    return run_to_dict(run)


# ── read: model registry ──────────────────────────────────────────────────────

@mcp.tool()
def list_registered_models(max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    """List all registered models in the Model Registry."""
    client = MlflowClient()
    models = client.search_registered_models(max_results=effective_max_results(max_results))
    return [registered_model_to_dict(rm) for rm in models]


@mcp.tool()
def get_registered_model(model_name: str) -> dict:
    """Get details of a registered model, including all versions and aliases.

    Args:
        model_name: Name of the registered model.
    """
    client = MlflowClient()
    try:
        rm = client.get_registered_model(model_name)
        return registered_model_to_dict(rm)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_model_versions(model_name: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    """List all versions of a registered model.

    Args:
        model_name: Name of the registered model.
        max_results: Max versions to return.
    """
    client = MlflowClient()
    versions = client.search_model_versions(
        filter_string=f"name='{model_name}'",
        max_results=effective_max_results(max_results),
    )
    return [model_version_to_dict(mv) for mv in versions]


# ── read: server config ───────────────────────────────────────────────────────

@mcp.tool()
def describe_server_config() -> dict:
    """Show effective MLflow connection config used by this MCP server."""
    return {
        "mlflow_tracking_uri": os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI),
        "mlflow_tracking_insecure_tls": os.environ.get("MLFLOW_TRACKING_INSECURE_TLS", "false"),
        "mlflow_http_request_timeout": os.environ.get("MLFLOW_HTTP_REQUEST_TIMEOUT", "10"),
        "mlflow_http_request_max_retries": os.environ.get("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1"),
        "has_am_sc_api_key": AMSC_API_KEY_ENV in os.environ and bool(os.environ.get(AMSC_API_KEY_ENV)),
        "default_max_results": int(os.environ.get("MLFLOW_MCP_MAX_RESULTS", str(DEFAULT_MAX_RESULTS))),
    }


# ── write: experiments & runs ─────────────────────────────────────────────────

@mcp.tool()
def create_experiment(name: str, artifact_location: str = "", tags: dict = {}) -> dict:
    """Create a new MLflow experiment.

    Args:
        name: Experiment name (must be unique).
        artifact_location: Optional artifact root URI. Leave empty for server default.
        tags: Key/value string tags, e.g. {"team": "ml", "project": "mnist"}.
    """
    client = MlflowClient()
    existing = client.get_experiment_by_name(name)
    if existing is not None:
        return {"error": f"Experiment '{name}' already exists", "experiment_id": existing.experiment_id}
    exp_id = client.create_experiment(
        name=name,
        artifact_location=artifact_location or None,
        tags=tags or None,
    )
    return {"experiment_id": exp_id, "name": name}


@mcp.tool()
def create_run(
    experiment_name: str,
    run_name: str = "",
    tags: dict = {},
) -> dict:
    """Create a new run inside an experiment. Returns the run_id for subsequent logging calls.
    The experiment is created automatically if it does not exist.

    Args:
        experiment_name: Experiment to create the run in.
        run_name: Human-readable name for the run.
        tags: Key/value string tags to attach to the run.
    """
    client = MlflowClient()
    exp = client.get_experiment_by_name(experiment_name)
    exp_id = exp.experiment_id if exp else client.create_experiment(experiment_name)

    tag_dict = dict(tags or {})
    run = client.create_run(experiment_id=exp_id, run_name=run_name or None, tags=tag_dict or None)
    return {
        "run_id": run.info.run_id,
        "experiment_id": exp_id,
        "experiment_name": experiment_name,
        "run_name": run_name,
        "status": run.info.status,
    }


@mcp.tool()
def log_params(run_id: str, params: dict) -> dict:
    """Log hyperparameters (string key/value pairs) to a run.

    Args:
        run_id: Target run.
        params: Param key/value pairs, e.g. {"lr": "0.001", "batch_size": "32"}.
                Values are converted to strings automatically.
    """
    client = MlflowClient()
    for key, value in params.items():
        client.log_param(run_id, key, value)
    return {"logged_params": list(params.keys()), "run_id": run_id}


@mcp.tool()
def log_metrics(run_id: str, metrics: dict, step: int = 0) -> dict:
    """Log numeric metrics to a run.

    Args:
        run_id: Target run.
        metrics: Metric name to numeric value, e.g. {"loss": 0.42, "accuracy": 0.91}.
        step: Training step or epoch index (default 0).
    """
    client = MlflowClient()
    for key, value in metrics.items():
        client.log_metric(run_id, key, float(value), step=step)
    return {"logged_metrics": list(metrics.keys()), "step": step, "run_id": run_id}


@mcp.tool()
def set_tags(run_id: str, tags: dict) -> dict:
    """Set or update tags on a run.

    Args:
        run_id: Target run.
        tags: Key/value string tags, e.g. {"dataset": "cifar10", "owner": "alice"}.
    """
    client = MlflowClient()
    for key, value in tags.items():
        client.set_tag(run_id, key, value)
    return {"set_tags": list(tags.keys()), "run_id": run_id}


@mcp.tool()
def end_run(run_id: str, status: str = "FINISHED") -> dict:
    """Mark a run as finished, failed, or killed.

    Args:
        run_id: Run to end.
        status: FINISHED | FAILED | KILLED
    """
    valid = {"FINISHED", "FAILED", "KILLED"}
    status_upper = status.strip().upper()
    if status_upper not in valid:
        return {"error": f"Invalid status '{status}'. Must be one of {sorted(valid)}"}
    client = MlflowClient()
    client.update_run(run_id, status=status_upper)
    return {"run_id": run_id, "status": status_upper}


@mcp.tool()
def delete_run(run_id: str) -> dict:
    """Soft-delete a run (moves it to 'deleted' lifecycle stage, recoverable).

    Args:
        run_id: ID of the run to delete.
    """
    client = MlflowClient()
    client.delete_run(run_id)
    return {"deleted_run_id": run_id}


@mcp.tool()
def log_artifact_text(run_id: str, content: str, filename: str) -> dict:
    """Log a text string as an artifact file attached to a run.
    Useful for logging configs, evaluation notes, or small result files from an AI agent.

    Args:
        run_id: Target run.
        content: Text content to write.
        filename: Artifact filename, e.g. 'config.yaml' or 'eval_notes.txt'.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        client = MlflowClient()
        client.log_artifact(run_id, path)
    return {"run_id": run_id, "artifact": filename}


# ── write: model registry ─────────────────────────────────────────────────────

@mcp.tool()
def register_model(run_id: str, artifact_path: str, model_name: str, description: str = "") -> dict:
    """Register a logged model artifact in the MLflow Model Registry.

    Args:
        run_id: The run that contains the logged model.
        artifact_path: Path within the run's artifact store (e.g. 'model').
        model_name: Registry name to register under (created if it doesn't exist).
        description: Optional description for this model version.
    """
    model_uri = f"runs:/{run_id}/{artifact_path}"
    mv = mlflow.register_model(model_uri, model_name)
    if description:
        MlflowClient().update_model_version(model_name, mv.version, description=description)
    return {
        "name": mv.name,
        "version": mv.version,
        "status": mv.status,
        "model_uri": model_uri,
    }


@mcp.tool()
def set_model_alias(model_name: str, alias: str, version: str) -> dict:
    """Assign an alias (e.g. 'champion', 'staging') to a specific model version.
    The model can then be loaded with models:/<model_name>@<alias>.

    Args:
        model_name: Name of the registered model.
        alias: Alias string, e.g. 'champion', 'challenger', 'production'.
        version: Model version number to point the alias at.
    """
    MlflowClient().set_registered_model_alias(model_name, alias, version)
    return {"model_name": model_name, "alias": alias, "version": version}


@mcp.tool()
def delete_model_alias(model_name: str, alias: str) -> dict:
    """Remove an alias from a registered model.

    Args:
        model_name: Name of the registered model.
        alias: Alias to remove.
    """
    MlflowClient().delete_registered_model_alias(model_name, alias)
    return {"model_name": model_name, "deleted_alias": alias}


@mcp.tool()
def set_model_version_tag(model_name: str, version: str, key: str, value: str) -> dict:
    """Set a tag on a specific model version.

    Args:
        model_name: Name of the registered model.
        version: Model version number.
        key: Tag key.
        value: Tag value.
    """
    MlflowClient().set_model_version_tag(model_name, version, key, value)
    return {"model_name": model_name, "version": version, "tag": {key: value}}


@mcp.tool()
def update_registered_model(model_name: str, description: str) -> dict:
    """Update the description of a registered model.

    Args:
        model_name: Name of the registered model.
        description: New description text.
    """
    MlflowClient().update_registered_model(model_name, description=description)
    return {"model_name": model_name, "description": description}


@mcp.tool()
def delete_registered_model(model_name: str) -> dict:
    """Permanently delete a registered model and all its versions.
    This action cannot be undone.

    Args:
        model_name: Name of the registered model to delete.
    """
    MlflowClient().delete_registered_model(model_name)
    return {"deleted_model": model_name}


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MLflow MCP server")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a quick MLflow query and exit (no MCP server start).",
    )
    parser.add_argument(
        "--list-experiments",
        action="store_true",
        help="List experiments and exit (no MCP server start).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=1000,
        help="Max results for --list-experiments (default: 1000).",
    )
    args = parser.parse_args()

    if args.self_test:
        cfg = describe_server_config()
        print("MCP config:", cfg)
        rows = list_experiments(max_results=3, view_type="active_only")
        print(f"Self-test OK. Fetched {len(rows)} experiment(s).")
        if rows:
            print("Sample experiment:", rows[0]["name"])
        sys.exit(0)

    if args.list_experiments:
        rows = list_experiments(max_results=args.max_results, view_type="all")
        print(f"Experiments found: {len(rows)}")
        for exp in rows:
            print(f"{exp['experiment_id']}\t{exp['name']}\t{exp['lifecycle_stage']}")
        sys.exit(0)

    print(
        "Starting MLflow MCP server on stdio. This process waits for an MCP client and may appear idle.",
        file=sys.stderr,
        flush=True,
    )
    mcp.run()
