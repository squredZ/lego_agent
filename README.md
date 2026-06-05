# lego_agent

A project-oriented agent framework.

The framework starts from a project goal. It creates a `Project`, creates one mandatory project manager `Staff`, and runs the first version in `project_manager_only` mode. The project manager analyzes the goal and produces a structured project result, including a staffing plan.

The previous Organization runtime has been removed. Project is the only top-level runtime aggregate.

## Design

- [中文重审版设计文档](docs/AGENT_FRAMEWORK_REDESIGN_CN.md)
- [Project Agent Design](docs/PROJECT_AGENT_DESIGN.md)
- [Development Plan](docs/DEVELOPMENT_PLAN.md)
- [CLI Call Flow](docs/CLI_CALL_FLOW.md)

## Target Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
lego-agent project run --config configs/project_runtime.json "Build a configurable agent framework"
pytest
```

The included OpenAI-compatible assistant should support dry-run mode when no API key is configured, so local examples and tests do not require network access.

`configs/project_runtime.json` can also provide the default project goal and
CLI output preferences. With the included config, the shortest run command is:

```bash
lego-agent project run
```

Use CLI flags only when temporarily overriding the config.

## Runtime Events

JSON output includes project events by default:

```bash
lego-agent project run --json --config configs/project_runtime.json "Build a configurable agent framework"
```

The same behavior can be configured with:

```json
{
  "cli": {
    "output_json": true,
    "include_events": true,
    "include_staffing_matches": true,
    "log_level": "INFO"
  }
}
```

Human-readable output follows the `cli.include_events` config value. Override it
for one run with:

```bash
lego-agent project run --events --config configs/project_runtime.json "Build a configurable agent framework"
lego-agent project run --no-events
```

The runtime also resolves the project manager's planned roles against configured
staff profiles. Show those matches in human-readable output with:

```bash
lego-agent project run --staffing-matches --config configs/project_runtime.json "Build a configurable agent framework"
```

CLI logging uses Python's standard `logging` module. The level is resolved from
`--log-level`, then `cli.log_level`, then `LEGO_AGENT_LOG_LEVEL`, then
`WARNING`:

```bash
lego-agent --log-level INFO project run --config configs/project_runtime.json "Build a configurable agent framework"
```

## Orchestration Note

`project_manager_only` runs only the primary project manager. `project_manager_with_staff` creates recruited staff, runs child tasks serially, records manager decisions, and performs a final manager review. `langgraph` remains a dependency for future graph or concurrent orchestration, but the current runtime path does not require it.
