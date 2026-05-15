# gateway_langgraph_composio — LangGraph + Gateway Composio connector demo

Runnable example showing how a Gateway-managed LangGraph agent can use the
**connector toolbelt** (phases 1–6) instead of dumping thousands of Composio
tools into context.

## What it proves

- **Intent search** via `search_connector_tools` (Composio `COMPOSIO_SEARCH_TOOLS` + Gateway allow/deny).
- **Optional execute** when the operator includes `RUN:<TOOL_SLUG> {"arg": "value"}` in the mention.
- **Activity**: Gateway records connector execute events; the bridge emits `tool_start` / `tool_result` for search.

## Prerequisites

1. Gateway repo installed editable: `pip install -e .`
2. A Composio connector registered and authed:

```bash
ax gateway connectors add my_composio --provider composio --managed-auth \
  --config-json '{"user_id":"your-composio-user-id","allowed_tools":["GITHUB_*"]}'
ax gateway connectors auth write my_composio --from-file ./composio.env
```

3. Optional: `pip install langgraph` (bridge runs without it using the same logic sequentially).

## Register the agent

```bash
ax gateway agents add composio-graph \
  --template langgraph_composio \
  --connector-ref my_composio
```

Send a mention, for example:

```text
@composio-graph list stargazers for ComposioHQ/composio
```

To execute after search:

```text
@composio-graph RUN:GITHUB_LIST_STARGAZERS {"owner":"ComposioHQ","repo":"composio","per_page":3}
```

## Manual bridge run

```bash
export AX_GATEWAY_DIR=~/.ax/gateway   # or your gateway dir
export AX_GATEWAY_CONNECTOR_REF=my_composio
python3 examples/gateway_langgraph_composio/langgraph_composio_bridge.py "list github stars tools"
```

## Architecture

```
  mention → Gateway exec → langgraph_composio_bridge.py
                │
                ├─ search_connector_tools (Gateway + Composio API)
                ├─ optional execute_connector_tool (RUN: directive)
                └─ stdout reply + AX_GATEWAY_EVENT tool/status lines
```

Secrets stay in `connectors/auth/<id>.env` (managed) — never in the agent registry row.
