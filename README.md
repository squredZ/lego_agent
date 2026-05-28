# lego_agent

A project-oriented agent framework.

The framework starts from a project goal. It creates a `Project`, creates one mandatory project manager `Staff`, and runs the first version in `project_manager_only` mode. The project manager analyzes the goal and produces a structured project result, including a staffing plan.

The previous Organization runtime has been removed. Project is the only top-level runtime aggregate.

## Design

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

## Runtime Events

JSON output includes project events by default:

```bash
lego-agent project run --json --config configs/project_runtime.json "Build a configurable agent framework"
```

Human-readable output keeps events hidden unless requested:

```bash
lego-agent project run --events --config configs/project_runtime.json "Build a configurable agent framework"
```

The runtime also resolves the project manager's planned roles against configured
staff profiles. Show those matches in human-readable output with:

```bash
lego-agent project run --staffing-matches --config configs/project_runtime.json "Build a configurable agent framework"
```

CLI logging uses Python's standard `logging` module. It is quiet by default;
enable runtime logs when debugging:

```bash
lego-agent --log-level INFO project run --config configs/project_runtime.json "Build a configurable agent framework"
```

## Orchestration Note

`langgraph` remains a dependency for future multi-staff orchestration, but the current `project_manager_only` runtime does not use it. A single project-manager pass is simpler without a graph; this should be revisited when `project_manager_with_staff` is implemented.
