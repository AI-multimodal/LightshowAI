# Testing Local Data Streaming with Tiled and LightshowAI

This guide explains how to test a local data source folder with a local Tiled server, and how a subscriber can listen for newly written data and react when new files appear.

## Overview

In this setup:

1. A local data folder is registered with a Tiled catalog.
2. Tiled serves that folder through a local server.
3. A subscriber listens for new entries through Tiled notifications.
4. When a new XDI file is written into the monitored data workflow, the subscriber receives the update and can fetch and inspect the streamed data.

## Architecture

![Local Tiled streaming workflow](./local_tiled_streaming_workflow.png)

## Prerequisites

Make sure the following are available in your environment:

- Docker
- Redis image access
- `tiled`
- Your custom XDI adapter module, for example:
  - `xdi_adapter:XDIAdapter`
- The test scripts:
  - `subscribe_tiled.py`
  - `write_xdi_tiled.py`

## Example Folder Inputs

This test uses:

- Data folder to register with Tiled: `/home/sairam/LightshowAI/LightshowAI/data`
- Source XDI file to write: `/home/sairam/LightshowAI/LightshowAI/data_source/AnataseNor.xdi`

Adjust these paths to match your machine if needed.

## Step 1: Run Redis Server

Tiled streaming notifications use Redis. Start Redis locally with Docker:

```bash
docker run -d --rm --name tiled-redis -p 6379:6379 docker.io/redis:7-alpine
```

In your `config.yml`, make sure the streaming cache is configured to use Redis on the same port:

```yaml
streaming_cache:
  uri: redis://localhost:6379
```

## Step 2: Create the Tiled Catalog (first time only)

Initialize the catalog database:

```bash
tiled catalog init sqlite+aiosqlite:///catalog.db
```

This only needs to be done the first time.

## Step 3: Run the Tiled Server

Start the local Tiled server:

```bash
PYTHONPATH=$(pwd) tiled serve config config.yml --api-key secret
```

This serves the catalog locally, typically at `http://localhost:8000`.

## Step 4: Register the Local Data Folder in the Catalog

Register the folder that Tiled should expose:

```bash
TILTED_LOG_LEVEL=INFO PYTHONPATH=$(pwd) tiled register http://localhost:8000   --api-key secret   --verbose   --ext '.xdi=text/x-xdi'   --adapter 'text/x-xdi=xdi_adapter:XDIAdapter'   /home/sairam/LightshowAI/LightshowAI/data
```

This command tells Tiled:

- files ending in `.xdi` should be treated as `text/x-xdi`
- the MIME type `text/x-xdi` should be handled by `xdi_adapter:XDIAdapter`
- the local data folder should be indexed and served by Tiled

## Step 5: Run the Subscriber

Start the subscriber that listens for new data appearing in Tiled:

```bash
python subscribe_tiled.py
```

The subscriber should remain running and wait for notifications.

Expected behavior:

- it subscribes to child creation events
- when a new spectrum appears, it prints:
  - the key
  - metadata summary
  - number of rows
  - a preview of the data

## Step 6: Write Test Content

In another terminal, write a test XDI file into the workflow:

```bash
python write_xdi_tiled.py /home/sairam/LightshowAI/LightshowAI/data_source/AnataseNor.xdi
```

This script parses the XDI file and writes it into Tiled.

## Expected End-to-End Behavior

Once the test file is written:

1. `write_xdi_tiled.py` writes the parsed table into Tiled.
2. Tiled updates the catalog.
3. Redis-backed streaming notifications publish the change.
4. The running subscriber receives the new child notification.
5. The subscriber fetches the new entry and prints a preview.

## Full Command Summary

```bash
# 1. Run Redis
docker run -d --rm --name tiled-redis -p 6379:6379 docker.io/redis:7-alpine

# 2. Configure config.yml
# streaming_cache:
#   uri: redis://localhost:6379

# 3. Initialize catalog (first time only)
tiled catalog init sqlite+aiosqlite:///catalog.db

# 4. Run tiled server
PYTHONPATH=$(pwd) tiled serve config config.yml --api-key secret

# 5. Register local data folder
TILTED_LOG_LEVEL=INFO PYTHONPATH=$(pwd) tiled register http://localhost:8000   --api-key secret   --verbose   --ext '.xdi=text/x-xdi'   --adapter 'text/x-xdi=xdi_adapter:XDIAdapter'   /home/sairam/LightshowAI/LightshowAI/data

# 6. Start subscriber
python subscribe_tiled.py

# 7. Write a test file
python write_xdi_tiled.py /home/sairam/LightshowAI/LightshowAI/data_source/AnataseNor.xdi
```

## Troubleshooting

### No notifications received
Check that:

- Redis is running on port `6379`
- `streaming_cache.uri` in `config.yml` points to `redis://localhost:6379`
- the subscriber is connected to the same Tiled server
- the Tiled server was started with the intended `config.yml`

### File is skipped as already present
Your writer may skip a file if the key already exists in the catalog. Remove the existing entry or use a new file/key for repeated tests.

### Adapter errors
Verify that:

- `xdi_adapter.py` is importable from the current working directory
- `PYTHONPATH=$(pwd)` is set when running Tiled commands
- `xdi_adapter:XDIAdapter` matches the actual module and class name

## Notes

- The subscriber should be started before writing the test file.
- In a Jupyter notebook, run the subscriber in a background thread so the notebook does not block.
- Replace the example paths with your local paths where appropriate.
