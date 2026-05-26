# Project-Oriented Development Plan

## Current Status

The first project-oriented runtime slice is implemented.

Current runtime behavior:

```text
project goal
  -> ProjectRuntime
  -> Project
  -> primary project manager Staff
  -> project manager planning Task
  -> SinglePassStaffWorkflow
  -> ProjectResult with staffing_plan
  -> ProjectRunResult
```

Verified commands:

```bash
.venv/bin/python -m pytest
.venv/bin/lego-agent project run --config configs/project_runtime.json "Build a configurable agent framework"
```

Current test result:

```text
10 passed
```

## Version 1 Scope

Version 1 establishes the project-first framework foundation.

Included:

- Project-first runtime
- Mandatory primary project manager staff
- Unified staff data model
- Unified staff workflow abstraction
- Context, tools, skills, and memory interfaces
- Default/noop managers for first-version workflow slots
- Project manager only orchestration
- Staffing plan output
- OpenAI-compatible assistant
- CLI project run command
- pytest coverage
- Beginner-oriented code comments and docstrings

Excluded:

- Dynamic staff creation and execution
- Multi-staff collaboration
- Persistent storage
- UI
- Long-running background jobs
- Streaming output
- Real multi-round tool calling
- Skill runtime execution
- Long-term memory retrieval

## Completed Work

### Phase 0: Remove Organization Direction

Status: complete.

Completed:

1. Removed `lego_agent/organization` runtime source files.
2. Removed `configs/organization.json`.
3. Removed `examples/run_organization.py`.
4. Replaced organization tests with project runtime tests.
5. Updated README to describe project-first usage.

Acceptance status:

- No runtime code imports `lego_agent.organization`.
- No CLI path depends on organization or leader-only mode.
- Project is the only top-level runtime aggregate.

### Phase 1: Core Project Models

Status: complete.

Implemented in `lego_agent/core/models.py`:

- `Project`
- `ProjectStatus`
- `Staff`
- `StaffStatus`
- `Task`
- `TaskStatus`
- `Responsibility`
- `Capability`
- `StaffingPlan`
- `StaffRolePlan`
- `ProjectResult`
- `ProjectRunResult`
- `ProjectError`
- `TaskError`
- `WorkContext`
- `AssistantRequest`
- `AssistantResponse`
- `ToolSpec`
- `ToolCall`
- `ToolResult`
- `SkillSpec`
- `MemoryItem`
- `WorkResult`

Acceptance status:

- Models use Pydantic `BaseModel`.
- IDs and timestamps use default factories.
- Project validates that `manager_id` exists and points to role `project_manager`.
- Tests cover invalid project manager role.

### Phase 2: Runtime Configuration

Status: complete.

Implemented in `lego_agent/project/config.py`:

- `ProjectRuntimeConfig`
- `ProjectDefaultsConfig`
- `StaffProfileConfig`
- `AssistantConfig`
- `OrchestrationConfig`
- JSON config loading

Supported assistant fields:

- `model`
- `api_key`
- `base_url`
- `timeout_seconds`
- `thinking`
- `reasoning_effort`
- `token_limit`
- `dry_run`

Supported token limit aliases:

- `token_limit`
- `tokenlimit`
- `max_output_tokens`

Acceptance status:

- `configs/project_runtime.json` creates a project manager profile.
- Tests cover config parsing and assistant option mapping.

### Phase 3: Registries and Built-in Modules

Status: mostly complete for Version 1.

Implemented:

- Generic `Registry`
- Module import loader
- Built-in project-oriented responsibilities:
  - `requirements_analysis`
  - `planning`
  - `staffing`
  - `coordination`
  - `acceptance`
  - `implementation`
  - `review`
  - `testing`
- Built-in capabilities:
  - `task_decomposition`
  - `staff_recruitment`
  - `delegation`
  - `quality_review`
  - `execution_planning`
- Assistant factory registry
- Custom module loading test

Deferred:

- Workflow factory registry
- Orchestrator factory registry
- Tool spec registry
- Skill spec registry
- Output parser registry

Reason for deferral:

Version 1 only has one workflow, one orchestrator, noop tools, noop skills, and one output parser. Registries for these extension points should be added when the second implementation appears.

### Phase 4: Assistant, Context, Tools, Skills, Memory, and Staff Workflow

Status: complete for Version 1.

Implemented:

- `OpenAIAssistant`
- `AssistantRequest -> AssistantResponse` boundary
- OpenAI-compatible config mapping
- Environment fallback:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
- Deterministic dry-run response returning valid `ProjectResult`
- `DefaultContextManager`
- `NoopMemoryManager`
- `NoopToolManager`
- `NoopSkillManager`
- `DefaultPromptBuilder`
- `ProjectResultOutputParser`
- `SinglePassStaffWorkflow`

Workflow hooks implemented:

```text
receive_task
build_context
retrieve_memory
select_skills
select_tools
plan_work
execute_work
parse_output
update_memory
report_result
```

Acceptance status:

- Workflow returns a valid project result in dry-run.
- Hook order is tested.
- Noop tool, skill, and memory managers are wired into workflow.
- Output parser has fallback behavior.
- Version 1 does not execute assistant-requested tools.

### Phase 5: Project Manager Only Orchestration

Status: complete.

Implemented:

- `lego_agent/project/runtime.py`
- `lego_agent/project/orchestrator.py`
- `ProjectRuntime`
- `ProjectManagerOnlyOrchestrator`

Runtime flow:

```text
receive goal
  -> create project
  -> create manager from configured staff profile
  -> create manager planning task
  -> run SinglePassStaffWorkflow
  -> set project result/status
  -> return ProjectRunResult
```

Acceptance status:

- `project_manager_only` succeeds in dry-run.
- Unsupported strategies fail clearly.
- Project ends with manager, one manager task, result, staffing plan, and `done` status.

### Phase 6: CLI

Status: complete.

Implemented:

```bash
lego-agent project run --config configs/project_runtime.json "project goal"
```

Also supported:

```bash
lego-agent project run --config configs/project_runtime.json --json "project goal"
```

Human output includes:

- project id
- manager
- status
- summary
- staffing plan
- final output

Acceptance status:

- CLI dry-run works through installed entry point.
- JSON output is a valid `ProjectRunResult`.

### Phase 7: Tests

Status: complete for current Version 1 scope.

Implemented in `tests/test_project_runtime.py`:

- Project manager validation
- Project runtime config parsing
- Dry-run project manager result
- Workflow hook order
- Noop manager behavior
- Assistant config mapping
- Assistant env var fallback
- Custom module loading
- Unsupported orchestration strategy failure
- CLI JSON run

Acceptance status:

- `pytest` passes.
- Test names reflect project concepts.

### Phase 8: Documentation and Comments

Status: complete for current Version 1 scope.

Implemented:

- README updated for project-first usage.
- `docs/PROJECT_AGENT_DESIGN.md` updated with Mermaid diagrams.
- `docs/DEVELOPMENT_PLAN.md` refreshed with current progress.
- Beginner-oriented docstrings and comments added to key modules.

## Known Gaps

These are intentionally not blocking Version 1, but should be addressed soon.

1. LangGraph is no longer used by the new project runtime.
   - It remains a dependency.
   - Decision needed: reintroduce LangGraph in project orchestration or remove the dependency until multi-node orchestration starts.

2. Real model structured output is prompt-based.
   - Dry-run returns valid structured data.
   - Live model output is parsed as JSON with fallback.
   - Next step should improve structured output reliability.

3. Workflow/orchestrator/tool/skill/output parser registries are deferred.
   - Current code has stable classes but not full registries for every extension point.

4. No project event log yet.
   - Workflow state changes happen in memory.
   - A `ProjectEvent` model and event recorder would improve observability.

5. No persistent storage.
   - Projects and tasks exist only for a single run.

6. No real tool execution or skill runtime.
   - Noop managers are in place as extension slots.

## Next Development Plan

### Phase 9: Tighten Version 1 Runtime Quality

Objective: make the current project-manager-only runtime more robust before adding dynamic staff.

Tasks:

1. Add `ProjectEvent` and `TaskEvent` models.
2. Add `EventRecorder`.
3. Record major runtime events:
   - project created
   - manager created
   - task created
   - workflow hook started/completed
   - project completed/failed
4. Improve CLI error display.
5. Add tests for failed assistant/workflow paths.
6. Decide LangGraph dependency direction:
   - reintroduce LangGraph for `project_manager_only`
   - or remove it until Version 2 orchestration

Acceptance:

- Failed runs produce useful `ProjectRunResult.error`.
- Runtime events can be inspected in tests.
- Dependency direction is documented.

### Phase 10: Improve Structured Output Contract

Objective: make live assistant output more reliable.

Tasks:

1. Add a reusable `OutputContract` model.
2. Pass `ProjectResult` JSON schema into `AssistantRequest.output_schema`.
3. Update `DefaultPromptBuilder` to include explicit schema instructions.
4. Investigate OpenAI Responses API structured output support for current SDK.
5. Keep fallback parsing.
6. Add tests for valid JSON, invalid JSON, and partial JSON.

Acceptance:

- Live model prompt includes a concrete schema.
- Parser handles bad model output predictably.
- Dry-run remains deterministic.

### Phase 11: Staff Profile Expansion

Objective: prepare for dynamic staffing without executing recruited staff yet.

Tasks:

1. Add example profiles:
   - implementation staff
   - review staff
   - testing staff
   - research staff
2. Add `StaffProfileResolver`.
3. Match `StaffRolePlan.role` to configured profiles.
4. Return unresolved roles clearly.
5. Add CLI option to print planned staff profile matches.

Acceptance:

- PM staffing plan can be matched against configured profiles.
- Missing profile cases are tested.

## Version 2 Plan: Dynamic Staff Creation and Execution

Objective: move from PM-only planning to PM-led multi-staff execution.

Planned orchestration strategy:

```text
project_manager_with_staff
```

Tasks:

1. Project manager creates a structured `StaffingPlan`.
2. Runtime maps `StaffRolePlan` to `StaffProfileConfig`.
3. Runtime creates recruited staff inside the project.
4. Project manager creates tasks for recruited staff.
5. Staff execute tasks through the same `SinglePassStaffWorkflow`.
6. Project manager reviews staff outputs.
7. Project manager produces final `ProjectResult`.

Acceptance:

- A project can create at least two recruited staff from profiles.
- Recruited staff execute assigned tasks.
- PM receives staff outputs and produces final output.
- Existing PM-only mode remains supported.

## Version 3 Preview

Version 3 should deepen agent capabilities after multi-staff execution is stable.

Candidates:

- Real tool calling loop
- Skill runtime execution
- Persistent project/task/event store
- Project memory retrieval
- Staff memory
- Streaming CLI/API output
- Web/API service layer
