# Materials Project MCP Server

MCP server that exposes core Materials Project queries as tools for AI agents.
It targets the current Materials Project API at `https://api.materialsproject.org`
and uses a simple HTTP client, so it works even if `mp_api` is not installed.

## Setup

### Dependencies

```bash
pip install "mcp[cli]" requests
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MP_API_KEY` | — | Materials Project API key from your MP dashboard |
| `MP_API_BASE_URL` | `https://api.materialsproject.org` | Materials Project API base URL |

### Run

```bash
# stdio mode (default, for Claude Code / MCP clients)
python mcp/materials_project_server.py
```

### Claude Code Configuration

```json
{
  "mcpServers": {
    "materials-project": {
      "command": "python",
      "args": ["./mcp/materials_project_server.py"],
      "env": {
        "MP_API_KEY": "your-materials-project-api-key"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `authenticate_materials_project(api_key)` | Store and verify an MP API key |
| `mp_get_summary(material_id, fields?)` | Fetch summary data for one material |
| `mp_search_materials(...)` | Screen materials with common summary filters |
| `mp_get_structure(material_id, final?)` | Retrieve final or initial structures |
| `mp_get_endpoint_data(endpoint, material_id, fields?, limit?)` | Query a specific `/materials/...` endpoint |

## Example Prompts

- `Authenticate to Materials Project with this key: ...`
- `Find stable Li-Fe-O materials with band gaps between 1 and 3 eV`
- `Get the structure for mp-149`
- `Fetch dielectric data for mp-149`

## Notes

- The linked page `https://legacy.materialsproject.org/open` documents the legacy API.
- This server uses the current API instead.
- The officially supported Python client is `mp-api`, but direct HTTPS access is also supported by the Materials Project API.
