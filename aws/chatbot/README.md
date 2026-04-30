# LightshowAI XANES Chatbot — EC2 Deployment

Self-contained Chainlit chatbot. Uses the Claude Agent SDK to orchestrate two
local MCP servers vendored inside this folder:

- **`materials-project`** — search Materials Project for crystal structures
- **`lightshowai`** — predict K-edge XANES via OmniXAS (FEFF for Co/Cr/Cu/Fe/Mn/Ni/Ti/V; VASP for Ti and Cu)

The whole stack lives under `examples/LightshowAI/`. You can copy that one
directory to a server and run it — no other parts of `agentic_workflows` are
needed.

## Layout (self-contained)

```
LightshowAI/
├── lightshowai/             # the python package (pip install -e .)
├── model_checkpoints/       # baked OmniXAS .ckpt files (75 MB)
├── mcp/                     # vendored MCP server scripts
│   ├── lightshowai_server.py
│   ├── materials_project_server.py
│   └── materials_project_client.py
└── aws/chatbot/             # this folder
    ├── app.py               # Chainlit handler
    ├── requirements.txt
    ├── .env.example
    ├── setup.sh             # one-shot installer for Ubuntu 22.04
    ├── lightshowai-chatbot.service
    └── README.md
```

## Architecture

```
Browser  →  http://<ec2-ip>:8000  →  Chainlit UI
                                       │
                                       │  ClaudeSDKClient (one per session)
                                       ▼
                              Anthropic API (model from CLAUDE_MODEL env)
                                       │
                          ┌────────────┴────────────┐
                          │                         │
                  materials-project MCP      lightshowai MCP
                  (stdio subprocess)         (stdio subprocess)
                          │                         │
                  Materials Project API      Local OmniXAS checkpoints
```

## Deploy on EC2 (Ubuntu 22.04, t3.large or larger)

You only need this directory on the box — not the broader `agentic_workflows`
repo. The simplest way is sparse-checkout:

```bash
# On the EC2 box
cd ~
git clone --depth 1 --filter=blob:none --no-checkout <YOUR-REPO-URL> tmp_repo
cd tmp_repo
git sparse-checkout set examples/LightshowAI
git checkout
mv examples/LightshowAI ~/LightshowAI
cd ~ && rm -rf tmp_repo
```

(If you already have `~/LightshowAI/` from an earlier copy, skip the above.)

Then:

```bash
cd ~/LightshowAI/aws/chatbot
./setup.sh                # creates ~/venv-chatbot, installs everything
nano .env                 # fill in 3 keys + optional CLAUDE_MODEL
source ~/venv-chatbot/bin/activate
chainlit run app.py -h --host 0.0.0.0 --port 8000
```

Visit `http://<ec2-public-ip>:8000`. (Open port 8000 in the SG first — `My IP` source.)
For inline HTML plots, also run `lightshowai-plots.service` and allow the
browser to reach `PLOTS_PUBLIC_URL` (default `http://localhost:8001`; on EC2,
usually `http://<ec2-public-ip>:8001`).

For background operation as a service:

```bash
sudo cp lightshowai-chatbot.service /etc/systemd/system/
sudo cp lightshowai-plots.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lightshowai-chatbot lightshowai-plots
sudo journalctl -u lightshowai-chatbot -f
```

## Configuration (`.env`)

| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Anthropic API key |
| `MP_API_KEY` | yes | Materials Project API key (https://next-gen.materialsproject.org/api) |
| `CHAINLIT_PASSWORD` | recommended | Shared password for collaborators. Blank ⇒ any non-empty username works. |
| `CLAUDE_MODEL` | optional | Default `claude-opus-4-7`. Set to `claude-sonnet-4-6` if your key lacks 4-7 access (`400 Invalid model name`). |
| `PLOTS_PUBLIC_URL` | recommended | Browser-visible URL for `~/tmp/*.html` artifacts served by `lightshowai-plots.service`, e.g. `http://<ec2-public-ip>:8001`. |
| `MLFLOW_EXPERIMENT` | optional | Default `LightshowAI-XANES-chatbot`. Parent chat runs and nested LightshowAI tool runs are written here. |
| `MLFLOW_TRACKING_INSECURE_TLS` | optional | Default `false`. Set to `true` only as a temporary workaround for a certificate-chain problem. |
| `MLFLOW_HTTP_REQUEST_TIMEOUT` | optional | Default `10`. Bounds MLflow network calls so logging cannot stall the chat for minutes. |
| `MLFLOW_HTTP_REQUEST_MAX_RETRIES` | optional | Default `1`. Keeps MLflow logging failures quick. |
| `CHAINLIT_CHAT_TURN_TIMEOUT_S` | optional | Default `900`. Resets a wedged Claude SDK turn instead of leaving an empty assistant bubble indefinitely. |

## Try it

After signing in:

> Compare Ti K-edge XANES for the three TiO₂ polymorphs (rutile, anatase, brookite) using FEFF.

> Search Materials Project for stable Cu oxides and predict the Cu K-edge XANES for each.

The agent will call the MCP tools, render each tool call as a collapsible *Step*,
stream the prose answer, and embed any `~/tmp/*.html` plots/viewers inline.

When `AM_SC_API_KEY` is set, each chat turn is logged to MLflow as a parent run
with the full prompt, system prompt, response, uploaded files, rendered HTML
artifacts, structured tool-call JSON, and collected Materials Project metadata.
LightshowAI prediction tools also create nested MLflow runs with model metadata,
material identifiers, formula/site/symmetry tags, energy-grid parameters,
plot artifacts, sidecar spectrum CSV artifacts, and spectrum metrics for
single-material predictions.

## Cost

- **EC2 `t3.large`**: ~$60/mo always-on; ~$2/mo storage-only when stopped
- **Anthropic API**: ~$0.05/turn on `claude-opus-4-7`; ~$0.015/turn on `claude-sonnet-4-6`
- **Materials Project**: free
- A few dollars/month for light demo use

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `400 Invalid model name passed in model=claude-opus-4-7` | Your key lacks Opus 4.7 access — set `CLAUDE_MODEL=claude-sonnet-4-6` in `.env` and restart |
| Browser shows nothing at the URL | Port 8000 not allowed in the EC2 security group |
| HTML plot message appears but iframe is blank | `lightshowai-plots.service` is not running, port 8001 is blocked, or `PLOTS_PUBLIC_URL` points somewhere the browser cannot reach |
| Agent asks for an experimental data path after upload | Restart after deploying this version. Uploaded files are copied to `~/tmp/uploads/<session>/...` and their paths are appended to the agent prompt. |
| Old plots from previous questions appear | Restart after deploying this version. Each turn now gets a unique `~/tmp/turns/<session>/<turn>/` output directory, and auto-render fallback only scans that directory. |
| Chat reply completes but UI stays busy for a while | MLflow logging is slow. Set `MLFLOW_HTTP_REQUEST_TIMEOUT=10` and `MLFLOW_HTTP_REQUEST_MAX_RETRIES=1`, or unset `AM_SC_API_KEY` to disable chatbot auto-logging. |
| Empty assistant bubble never finishes | The Claude SDK turn is wedged. Set/keep `CHAINLIT_CHAT_TURN_TIMEOUT_S=900`; after timeout, refresh and start a new chat. |
| Repeated `InsecureRequestWarning` from `urllib3` | Set `MLFLOW_TRACKING_INSECURE_TLS=false` in `.env` and restart. If TLS verification then fails, install/update CA certificates or fix the MLflow server certificate chain. |
| `ANTHROPIC_API_KEY not set` on startup | `.env` not loaded — check the file exists and the systemd `EnvironmentFile=` path |
| MCP "tool not found" | The MCP subprocess crashed — `journalctl -u lightshowai-chatbot` for stderr |
| First inference call hangs 30–60 s | Loading 75 MB of OmniXAS weights into memory. One-time per process. |
| Chainlit login screen but rejects the password | The value of `CHAINLIT_PASSWORD` in `.env` is what you typed (any email is fine; only the password is checked) |

## Known limitations

- **No HTTPS** — fine for `My IP` SG rule, not public demos. Add Caddy in front.
- **Shared password only** — for per-user accounts, swap to Chainlit OAuth + Cognito.
- **No persistence** — chat history is per browser tab. Enable Chainlit's data layer for cross-session storage.
- **No per-user rate limiting** — a chatty user can burn API credit fast.
