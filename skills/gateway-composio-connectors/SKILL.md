---
name: gateway-composio-connectors
description: |
  Register, authenticate, search, filter, and execute Composio tools through
  the Gateway connector registry. Use when setting up outbound toolbelt access
  for managed agents, running ax gateway connectors commands, debugging connector
  auth or policy, or wiring langgraph_composio agents with --connector-ref.
---

# Gateway Composio Connectors

Use this skill when the task is **outbound SaaS tools via Composio** brokered by
Gateway—not when configuring Claude Code `.mcp.json` or remote aX MCP (see
`docs/composio-integration.md` for boundaries).

## Principles

1. **Gateway is the trust boundary for secrets.**
   - Registry row: name, provider, `auth_ref`, non-secret `config`.
   - Secrets: `connectors/auth/<id>.env` (`gateway:managed`) or an external env path.
   - Never copy API keys into `connectors.json`, agent registry, workspace config, or chat.

2. **Filter after Composio, before execute.**
   - Composio intent search narrows thousands of tools to a small candidate set.
   - Gateway `allowed_tools` / `denied_tools` (fnmatch) applies on catalog, search, and `call`.
   - Prefer `tools search` over dumping full catalogs into agent context.

3. **One Composio `user_id` per principal.**
   - Map each connector row to one automation identity (agent, team bot, or human).
   - Do not share entities across unrelated agents without an explicit operator decision.

4. **Runtime actions use agent identity on aX.**
   - User PAT bootstraps Gateway only.
   - Managed agents use Gateway-minted agent tokens for platform calls.

## First checks

```bash
uv run ax gateway status --json
uv run ax gateway connectors list --json
```

Confirm `connectors_registry_path` and that the target connector row exists and is `enabled`.

## Golden path

### 1. Register connector (managed auth)

```bash
uv run ax gateway connectors add my_composio \
  --provider composio \
  --managed-auth \
  --config-json '{"user_id":"<composio-entity-id>","allowed_tools":["GITHUB_*"],"search_mode":"auto"}'
```

### 2. Write secrets offline

Create `composio.env` (never commit):

```env
COMPOSIO_API_KEY=<key>
```

```bash
uv run ax gateway connectors auth write my_composio --from-file ./composio.env
uv run ax gateway connectors auth status my_composio
```

### 3. Search before execute

```bash
uv run ax gateway connectors tools search my_composio \
  --use-case "list GitHub stargazers for owner/repo" \
  --json

uv run ax gateway connectors tools list my_composio --toolkit github --limit 10 --json
```

### 4. Execute one tool

```bash
uv run ax gateway connectors call my_composio \
  --tool GITHUB_LIST_STARGAZERS \
  --args-json '{"owner":"ORG","repo":"REPO","per_page":5}' \
  --json
```

### 5. Verify activity

```bash
uv run ax gateway activity
```

Expect `connector_tool_started` / `connector_tool_completed` (or `_failed`) with `tool_name` like `composio/GITHUB_LIST_STARGAZERS`.

## LangGraph demo agent

When the operator wants mention-driven search + optional execute:

```bash
uv run ax gateway agents add composio-graph \
  --template langgraph_composio \
  --connector-ref my_composio
```

Mention patterns:

- Natural language → intent search only.
- `RUN:<TOOL_SLUG> {"arg": "value"}` → search round + `execute_connector_tool`.

Update connector binding without recreating the agent:

```bash
uv run ax gateway agents update composio-graph --connector-ref my_composio
```

## Policy tuning

Edit connector config (non-secret) via `connectors set`:

```bash
uv run ax gateway connectors set my_composio \
  --config-json '{"allowed_tools":["GITHUB_*"],"denied_tools":["*_DELETE_*"],"tools_limit":20}'
```

If `call` fails with “not allowed”, fix patterns before disabling the connector.

## Optional activity linkage

Set `agent_name` in connector config to the Gateway registry name of a managed agent so activity rows include that agent’s identity fields when present.

## Output standard

When finishing connector setup, report:

- Connector name/id and provider
- Whether auth status shows required keys (redacted)
- A successful `tools search` or `call` result summary (tool slugs only, no secrets)
- Any allow/deny patterns in effect
- Next step (LangGraph agent, Hermes integration, or manual `call` only)

## Anti-patterns

- Putting `COMPOSIO_API_KEY` in `--config-json` or agent registry.
- Sharing one Composio entity across unrelated agents without documenting it.
- Executing tools before search when the slug is unknown (wastes context and risks wrong tool).
- Using user bootstrap token to author agent messages while testing connectors.
- Assuming PyPI `axctl` has `connectors` without verifying `pip install -e .` from this repo.

## References

- Operator doc: `docs/composio-integration.md`
- Example bridge: `examples/gateway_langgraph_composio/README.md`
- General Gateway agents: `skills/gateway-agent-setup/SKILL.md`
