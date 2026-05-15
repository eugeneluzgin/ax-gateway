# Composio integration via Gateway connectors

Gateway connectors are the **outbound toolbelt** for managed agents: Composio (and future providers) run **outside** agent context, with secrets brokered by Gateway and tool exposure controlled by operator policy.

This document is the operator reference for phases 1–7 of the connector stack. For a runnable graph demo, see [`examples/gateway_langgraph_composio/README.md`](../examples/gateway_langgraph_composio/README.md).

## Two trust boundaries

| Layer | Who authenticates | What it owns |
|-------|-------------------|--------------|
| **aX / Gateway** | Human bootstrap login + per-agent PATs | Spaces, messages, managed agent identity, connector registry rows |
| **Composio** | API key + `user_id` (entity) per connector | Connected accounts (GitHub, Slack, …), tool catalog, tool execution |

Rules:

- **Never** put Composio API keys, OAuth tokens, or connected-account secrets in `connectors.json`, agent registry rows, workspace `.ax/config.toml`, chat, or PRs.
- Store secrets only in Gateway-managed auth files (`gateway:managed`) or operator-chosen external env files referenced by `auth_ref`.
- Runtime messages and activity rows use **redacted** connector metadata (name, provider, tool slug)—not secret values.

## Connectors vs Claude Code MCP

| Approach | Best for |
|----------|----------|
| **`ax gateway connectors`** (this doc) | Gateway-supervised agents, LangGraph bridges, CLI/scripted tool calls, centralized allow/deny policy |
| **`ax channel setup` + `.mcp.json`** | Live Claude Code Channel sessions talking to remote aX MCP |
| **Composio hosted MCP** (`https://mcp.composio.dev`) | Direct MCP clients (Cursor, ChatGPT connectors) **without** Gateway policy |

Gateway connectors call Composio’s **HTTP tool API** directly. They do not require the Composio Python SDK at install time. Intent search uses Composio’s `COMPOSIO_SEARCH_TOOLS` plus Gateway filtering—not a full tool dump into the model.

## On-disk layout

Under `AX_GATEWAY_DIR` (default `~/.ax/gateway`, or `~/.ax/gateway/envs/<env>` when `AX_GATEWAY_ENV` is set):

```text
<connectors.json>              # registry rows (no secrets)
connectors/auth/<connector-id>.env   # managed secrets (mode 0600) when auth_ref = gateway:managed
activity.jsonl                 # connector_tool_* events on execute
```

Inspect paths:

```bash
ax gateway status --json    # connectors_registry_path, connectors_auth_env_dir
```

## Golden path setup

### 1. Start Gateway and log in

```bash
pip install -e .
ax gateway login
ax gateway start
```

### 2. Register a Composio connector

```bash
ax gateway connectors add my_composio \
  --provider composio \
  --managed-auth \
  --config-json '{
    "user_id": "your-composio-entity-id",
    "allowed_tools": ["GITHUB_*", "SLACK_*"],
    "denied_tools": ["*_DELETE_*"],
    "toolkits": ["github"],
    "tools_limit": 25,
    "search_mode": "auto",
    "agent_name": "hermes"
  }'
```

`user_id` is the Composio entity id for this connector (one human or one automation principal per connector row is recommended).

Optional non-secret config keys:

| Key | Purpose |
|-----|---------|
| `base_url` | Composio API base (default `https://backend.composio.dev`) |
| `tool_version` / `version` | Tool version passed to execute |
| `connected_account_id` | Execute as a specific connected account |
| `agent_name` | Link activity rows to a Gateway registry agent name |
| `allowed_tools` / `allow_tools` | fnmatch allowlist applied **after** Composio returns candidates |
| `denied_tools` / `deny_tools` | fnmatch denylist |
| `toolkits` / `toolkit_slug` / `toolkit` | Restrict catalog listing to toolkit slugs |
| `tools_limit` | Max tools per list/search page (default 50, max 200) |
| `search_mode` | `auto` \| `intent` \| `catalog` for `tools search` |

### 3. Write auth secrets (managed)

Create a local file **outside git** (example `composio.env`):

```env
COMPOSIO_API_KEY=your_key_here
# Optional overrides:
# COMPOSIO_USER_ID=entity-id
# COMPOSIO_BASE_URL=https://backend.composio.dev
```

```bash
ax gateway connectors auth write my_composio --from-file ./composio.env
ax gateway connectors auth status my_composio
```

`auth status` is redacted—it confirms keys are present, not their values.

### 4. Discover and test tools

```bash
# Intent / catalog search (Composio-native, then Gateway policy)
ax gateway connectors tools search my_composio \
  --use-case "list stargazers for a GitHub repo"

# Catalog browse
ax gateway connectors tools list my_composio --toolkit github --query stargazers

# Execute one tool
ax gateway connectors call my_composio \
  --tool GITHUB_LIST_STARGAZERS \
  --args-json '{"owner":"ComposioHQ","repo":"composio","per_page":5}'
```

### 5. Observe activity

```bash
ax gateway activity
```

On execute, Gateway appends `connector_tool_started`, `connector_tool_completed`, or `connector_tool_failed` with tool name `composio/<TOOL_SLUG>`.

## LangGraph demo agent

Register an agent that searches (and optionally executes) via connectors on each mention:

```bash
ax gateway agents add composio-graph \
  --template langgraph_composio \
  --connector-ref my_composio
```

Mention examples:

```text
@composio-graph find GitHub tools for listing repository stargazers
@composio-graph RUN:GITHUB_LIST_STARGAZERS {"owner":"ComposioHQ","repo":"composio","per_page":3}
```

The bridge sets `AX_GATEWAY_CONNECTOR_REF` from the agent’s `connector_ref` field. See the example README for manual bridge runs.

Agents setting up connectors should use the companion skill [`skills/gateway-composio-connectors/SKILL.md`](../skills/gateway-composio-connectors/SKILL.md).

## External auth file (advanced)

Instead of `--managed-auth`, reference an existing env file:

```bash
ax gateway connectors add my_composio \
  --provider composio \
  --auth-ref /absolute/path/to/composio.env \
  --config-json '{"user_id":"entity-id"}'
```

Gateway does not copy or chmod external files; the operator owns permissions and rotation.

## Security checklist

- [ ] API keys only in managed `connectors/auth/*.env` or approved external paths
- [ ] `connectors.json` and `gateway/registry.json` contain no secrets
- [ ] Allow/deny patterns documented for each connector (`allowed_tools`, `denied_tools`)
- [ ] One Composio `user_id` per automation principal (avoid shared entities across unrelated agents)
- [ ] Agent runtime uses **agent PAT**, not user bootstrap PAT, for aX calls
- [ ] PRs and chat never include `composio.env` contents

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `Composio API key missing` | Auth file empty or wrong key name | `auth write` with `COMPOSIO_API_KEY`; `auth status` |
| `user_id missing` | Config and env both empty | Set `config.user_id` or `COMPOSIO_USER_ID` in auth env |
| `tool … is not allowed` | Gateway allow/deny policy | Adjust `allowed_tools` / `denied_tools`; `tools search` to see filtered set |
| `unknown connector` | Typo or wrong Gateway dir | `connectors list`; confirm `AX_GATEWAY_DIR` / `AX_GATEWAY_ENV` |
| `No such command 'connectors'` | Old PyPI `axctl` install | `pip install -e .` from this repo |
| Bridge: `AX_GATEWAY_CONNECTOR_REF` required | Agent missing `--connector-ref` | `agents update <name> --connector-ref my_composio` |
| 401 from Composio | Invalid or short API key | Rotate key in Composio dashboard; re-`auth write` |

## CLI reference

| Command | Purpose |
|---------|---------|
| `ax gateway connectors list` | Registry rows |
| `ax gateway connectors show <ref>` | Row + redacted auth status |
| `ax gateway connectors add` | New row (`--managed-auth`, `--config-json`) |
| `ax gateway connectors set` | Enable/disable, update config |
| `ax gateway connectors remove` | Remove row; release managed auth if unused |
| `ax gateway connectors auth write` | Copy secrets into managed env |
| `ax gateway connectors auth status` | Redacted key presence |
| `ax gateway connectors tools list` | Composio catalog + policy |
| `ax gateway connectors tools search` | Intent/catalog search + policy |
| `ax gateway connectors call` | Execute tool by slug |
| `ax gateway connectors providers` | Supported provider ids (`composio`) |

## Related docs

- [Gateway agent runtimes](gateway-agent-runtimes.md) — managed agents and exec bridges
- [Credential security](credential-security.md) — PAT handling and workspace boundaries
- [Gateway demo script](gateway-demo-script.md) — broader Gateway walkthrough
