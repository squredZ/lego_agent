# lego_agent

A project-oriented agent framework.

The framework starts from a project goal. It creates a `Project`, creates one mandatory project manager `Staff`, and runs the first version in `project_manager_only` mode. The project manager analyzes the goal and produces a structured project result, including a staffing plan.

The previous Organization runtime has been removed. Project is the only top-level runtime aggregate.

## Design

- [Project Agent Design](docs/PROJECT_AGENT_DESIGN.md)
- [Development Plan](docs/DEVELOPMENT_PLAN.md)

## Target Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
lego-agent project run --config configs/project_runtime.json "Build a configurable agent framework"
pytest
```

The included OpenAI-compatible assistant should support dry-run mode when no API key is configured, so local examples and tests do not require network access.
