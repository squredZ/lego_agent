# Project-Oriented Development Plan

## Current Status

The project-oriented runtime foundation, synchronous multi-staff execution
slice, iterative staff workflow, first tool-call loop, and model package
refactor are implemented. The Project Console is designed but not yet
implemented.

Current runtime behavior:

```text
project goal
  -> ProjectRuntime
  -> Project
  -> primary project manager Staff
  -> project manager planning Task
  -> SinglePassStaffWorkflow
  -> ProjectResult with staffing_plan
  -> create recruited Staff from staffing_plan
  -> create and dispatch child Tasks
  -> execute child Tasks through SinglePassStaffWorkflow
  -> TaskExecutionResult for each child Task
  -> ProjectRunResult
```

Optional V2B iterative workflow:

```text
Staff task
  -> IterativeStaffWorkflow
  -> assistant response
  -> optional assistant-requested tool calls
  -> ToolManager executes enabled tools
  -> tool results are appended to runtime messages
  -> strict structured output validation
  -> validation feedback retry when needed
  -> WorkResult
```

Current documentation state:

- `docs/PROJECT_AGENT_DESIGN.md` describes the project-oriented runtime and
  staff workflow design.
- `docs/CLI_CALL_FLOW.md` explains the CLI startup and runtime call chain.
- `docs/PROJECT_CONSOLE_DESIGN.md` defines the minimal frontend interaction
  layer and development plan.

Verified commands:

```bash
.venv/bin/python -m pytest
.venv/bin/lego-agent project run --config configs/project_runtime.json "Build a configurable agent framework"
```

Current test result:

```text
49 passed
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

## Engineering Rules

Every development task must follow these rules:

1. Comments and docstrings must be clear for beginners.
   - Explain why a class or function exists.
   - Explain non-obvious design choices.
   - Avoid noisy comments that merely restate a line of code.

2. Code must follow SOLID principles.
   - Single Responsibility: each class or function should have one clear reason to change.
   - Open/Closed: extension points should prefer registries, composition, or new classes over modifying stable code paths.
   - Liskov Substitution: implementations of common protocols should be replaceable without surprising callers.
   - Interface Segregation: avoid forcing components to depend on methods they do not use.
   - Dependency Inversion: high-level runtime and workflow code should depend on abstractions or injected collaborators where practical.

3. Code should act as documentation.
   - Prefer clear names, explicit types, small functions, and obvious module boundaries.
   - Let Pydantic models, Protocols, and tests describe contracts and examples.
   - Use comments to explain why a design exists, not to repeat what a line does.
   - Tests should read like executable examples of framework usage.

4. Runtime behavior must be observable through clear logs and events.
   - Important lifecycle transitions should produce structured events or logs.
   - Logs should explain what happened, which project/task/staff was involved, and why a failure occurred.
   - Avoid logging secrets such as API keys, tokens, and raw credentials.
   - Prefer stable event names and structured metadata over long free-form messages.
   - Tests should cover important logging or event behavior when it is part of the contract.

5. After every completed task, perform a short review.
   - Are comments and docstrings enough for a beginner to understand intent?
   - Does the code explain itself through names, types, structure, and tests?
   - Does the implementation keep responsibilities separated?
   - Are dependencies injected or isolated where future replacement is likely?
   - Did the change avoid unnecessary coupling between runtime, workflow, assistant, tools, skills, memory, and output parsing?
   - Are logs and events sufficient to understand normal flow and failures?
   - Did the change avoid logging secrets or noisy implementation details?
   - Are tests updated for the behavior or extension point that changed?

This review is part of the task definition, not optional cleanup.

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

Implemented in the `lego_agent/core/models/` package and re-exported from
`lego_agent.core.models` for compatibility:

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
- Models are split by concern under `lego_agent/core/models/`.
- `lego_agent.core.models` remains the stable import path through package
  re-exports.
- Core model classes and fields include beginner-friendly descriptions.
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

Runtime logs can be enabled from the CLI:

```bash
lego-agent --log-level INFO project run --config configs/project_runtime.json "project goal"
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

Status: complete for current Version 1 scope; ongoing for new Version 2 work.

Implemented:

- README updated for project-first usage.
- `docs/PROJECT_AGENT_DESIGN.md` updated with Mermaid diagrams.
- `docs/DEVELOPMENT_PLAN.md` refreshed with current progress.
- `docs/CLI_CALL_FLOW.md` added for the complete CLI call chain.
- `docs/PROJECT_CONSOLE_DESIGN.md` added for the frontend interaction layer.
- Beginner-oriented docstrings and comments added to key modules.
- Core Pydantic models now have class docstrings and field descriptions.

### Phase 9: Tighten Version 1 Runtime Quality

Status: complete for current Version 1 scope.

Completed:

1. Added event models:
   - `EventLevel`
   - `ProjectEvent`
   - `TaskEvent`
2. Added `EventRecorder`.
3. Added in-memory project/task event recording for:
   - project created
   - manager created
   - task created
   - project planning started
   - workflow started
   - workflow hooks
   - workflow completed
   - workflow failed
   - task failed
   - project completed
   - project failed
4. Added `events` to `ProjectRunResult`.
5. Improved CLI error display for config/runtime creation failures.
6. Added tests for:
   - successful event recording
   - failed workflow event recording
   - CLI config error handling

Decisions:

1. Human CLI output hides events by default.
2. Human CLI output supports `--events`.
3. JSON output includes `ProjectRunResult.events` by default.
4. LangGraph remains a dependency for future multi-staff orchestration, but it is not used in the single-node PM-only runtime.

Remaining:

1. Consider a persistent event store after the runtime model stabilizes.
2. Reevaluate LangGraph when Version 2 multi-staff orchestration starts.

## Known Gaps

These are intentionally not blocking Version 1, but should be addressed soon.

1. LangGraph is no longer used by the new project runtime.
   - It remains a dependency.
   - Decision: keep the dependency for now, but do not use it in single-node PM-only runtime. Reevaluate when Version 2 multi-staff orchestration starts.

2. Real model structured output is prompt-based.
   - Dry-run returns valid structured data.
   - Live model output is parsed as JSON with fallback.
   - V2B iterative validation retries are implemented.
   - Provider-native structured output support is still deferred.

3. Tool execution is implemented but tool registration is still too centralized.
   - `BuiltinToolManager` currently owns the first built-in tool implementations.
   - Next step is V2B-3: introduce a `Tool` protocol and `ToolRegistry`.

4. Workflow/orchestrator/skill/output parser registries are deferred.
   - Current code has stable classes but not full registries for every extension point.

5. Event recording is in-memory only.
   - Project and task events are available in the current run result.
   - Persistent event storage is still deferred.

6. No persistent storage.
   - Projects and tasks exist only for a single run.

7. No skill runtime.
   - Skills are currently selected as workflow/prompt context only.
   - Real skill execution is planned after tool and iterative workflow semantics stabilize.

8. No frontend runtime implementation yet.
   - `docs/PROJECT_CONSOLE_DESIGN.md` defines the minimal interaction hub,
     local HTTP API, and static console direction.
   - Implementation starts in Version 2E.

## Next Development Plan

### Phase 10: Improve Structured Output Contract

Status: complete for current Version 1 scope.

Objective: make live assistant output more reliable.

Tasks:

1. Add a reusable `OutputContract` model: done.
2. Pass `ProjectResult` JSON schema into `AssistantRequest.output_schema`: done.
3. Update `DefaultPromptBuilder` to include explicit schema instructions: done.
4. Keep fallback parsing: done.
5. Add tests for valid JSON, invalid JSON, and partial JSON: done.
6. Use Chat Completions for OpenAI-compatible providers: done.
7. Investigate provider-native structured output support later: deferred until live provider integration hardening.

Acceptance:

- Live model prompt includes a concrete schema.
- Parser handles bad model output predictably.
- Dry-run remains deterministic.

### Phase 11: Staff Profile Expansion

Status: complete for current Version 1 scope.

Objective: prepare for dynamic staffing without executing recruited staff yet.
Configured staff profiles are templates, not a whitelist. Missing profiles no
longer block project-manager planning output when dynamic staff creation is
enabled.

Tasks:

1. Add example profiles:
   - implementation staff
   - review staff
   - testing staff
   - research staff
   Status: done.
2. Add `StaffProfileResolver`: done.
3. Match `StaffRolePlan.role` to configured profiles when templates exist: done.
4. Mark roles without templates as dynamically creatable when `dynamic_staff.enabled=true`: done.
5. Add CLI option to print planned staff profile matches: done.
6. Add `DynamicStaffConfig`: done.
7. Add `StaffFactory` for profile-template or dynamic staff creation: done.
8. Normalize model-generated dynamic staff roles to stable snake_case ids: done.

Acceptance:

- PM staffing plan can be matched against configured profiles when profiles exist.
- Missing profile cases are treated as dynamic staff when dynamic staff is enabled.
- Human role labels such as `Frontend Developer` become stable internal ids such as `frontend_developer`.
- Human CLI output can show planned role/profile matches with `--staffing-matches`.

## Version 2 Plan: Dynamic Staff Creation and Execution

Objective: move from PM-only planning to PM-led multi-staff execution.

Planned orchestration strategy:

```text
project_manager_with_staff
```

Design rule:

```text
Staff do not directly call other Staff.
They coordinate through Task state, Events, Messages, and the Orchestrator.
```

Staffing rule:

```text
Only the project manager is mandatory and preconfigured.
Other project staff are created from the project manager's staffing plan.
Configured staff profiles are reusable templates, not a whitelist.
```

### Version 2A: Synchronous Multi-Staff Semantics

Status: in progress. Foundation models, in-memory collaboration components,
staffing bootstrap, and synchronous worker execution are implemented. Manager
review is still pending.

Objective: model multi-staff collaboration without real concurrency.

Tasks:

1. Add interaction models:
   - `StaffMessage`
   - `StaffInbox`
   Status: done.
2. Add state/communication interfaces:
   - `TaskStore`
   - `MessageBus`
   - optional `EventBus`
   Status: `TaskStore` and `MessageBus` done; `EventBus` remains optional.
3. Add in-memory implementations:
   - `InMemoryTaskStore`
   - `InMemoryMessageBus`
   Status: done.
4. Add coordination helpers:
   - `TaskDispatcher`
   - `TaskCompletionHandler`
   Status: done.
5. Runtime maps `StaffRolePlan` to profile templates or dynamic staff creation.
   Status: done for `project_manager_with_staff` bootstrap.
6. Runtime creates recruited staff inside the project.
   Status: done for `project_manager_with_staff` bootstrap.
7. Runtime creates child tasks assigned to recruited staff.
   Status: done for `project_manager_with_staff` bootstrap.
8. Staff execute child tasks one by one through `SinglePassStaffWorkflow`.
   Status: done. Non-manager staff now use the `TaskExecutionResult` output
   contract while the project manager keeps using `ProjectResult`.
9. Child task completion updates task state, emits task events, and sends manager inbox messages.
   Status: done for synchronous `project_manager_with_staff` execution.
10. Manager reviews after all child tasks complete.
   Status: pending.

Acceptance:

- A project can create at least two recruited staff from profile templates or dynamic role plans.
- Recruited staff receive child tasks.
- Recruited staff execute child tasks synchronously in Version 2A.
- Each child task completion creates:
  - updated task state
  - task event
  - manager inbox message
- Manager final review uses task state as source of truth.
- Existing PM-only mode remains supported.

### Version 2B: Iterative Staff Workflow

Objective: make one staff task capable of realistic multi-round execution before
adding concurrency. `SinglePassStaffWorkflow` remains the simple baseline;
`IterativeStaffWorkflow` should share the same `run(project, staff, task) ->
WorkResult` interface so orchestrators do not depend on workflow internals.

Development sequence:

1. V2B-1: no-tool iterative workflow.
   - Add workflow configuration.
   - Add multi-step loop control.
   - Retry when structured output validation fails.
   - Stop clearly when step or retry limits are reached.
   Status: done.
2. V2B-2: real tool loop.
   - Parse assistant-requested tool calls.
   - Execute tools through `ToolManager`.
   - Append tool results to runtime messages.
   - Continue until valid final output or failure.
   Status: done.

Tasks:

1. Add `WorkflowConfig`:
   - `type`
   - `max_steps`
   - `max_tool_calls`
   - `max_output_retries`
   - `fail_on_tool_error`
   Status: done.
2. Add workflow construction from runtime config.
   Status: done.
3. Add `IterativeStaffWorkflow` with no-tool multi-step output validation retries.
   Status: done.
4. Extend `AssistantResponse` with:
   - `tool_calls`
   - `finish_reason`
   Status: done.
5. Extend `ToolCall` with provider call id.
   Status: done.
6. Parse Chat Completions `message.tool_calls` into framework `ToolCall` objects.
   Status: done.
7. Add tool-call loop:
   - execute tool calls through `ToolManager.call_tool`
   - append tool results to runtime messages
   - continue until valid output or failure
   Status: done.
8. Add first built-in safe tools:
   - `echo` for deterministic tool-loop tests.
   - `read_project_file` for controlled local project context reads.
   - Implement built-in tools in the Codex style: narrow schemas, explicit
     contracts, `ToolManager`-mediated execution, structured `ToolResult`,
     clear logs/events, secret redaction, and workspace safety boundaries.
   Status: done.
9. Add events:
   - `workflow_step_started`
   - `workflow_step_completed`
   - `tool_call_requested`
   - `tool_call_completed`
   - `tool_call_failed`
   - `output_validation_failed`
   - `workflow_step_limit_reached`
   Status: done for V2B iterative workflow and tool loop.
10. Keep `TaskStatus` unchanged until a UI/API needs stronger intermediate states.
   Status: pending.

V2B-3: Tool Registry Refactor.

Status: pending.

The current V2B-2 implementation keeps the first built-in tools inside
`BuiltinToolManager` as a minimal working implementation. The next refactor
should make tools extensible without continuing to grow that class.

Tasks:

1. Add a `Tool` protocol with:
   - `name`
   - `description`
   - `parameters_schema`
   - `call(arguments) -> ToolResult`
   Status: pending.
2. Add `ToolRegistry`.
   Status: pending.
3. Extract `EchoTool`.
   Status: pending.
4. Extract `ReadProjectFileTool`.
   Status: pending.
5. Make `BuiltinToolManager` delegate to `ToolRegistry`.
   Status: pending.
6. Keep existing `enabled_tools`, logging, structured `ToolResult`, and workspace safety behavior unchanged.
   Status: pending.

V2B-3 acceptance:

- adding a built-in tool does not require editing `BuiltinToolManager`;
- existing tool-loop tests still pass;
- `echo` and `read_project_file` behavior remains unchanged;
- workflows still depend only on `ToolManager.call_tool`, not concrete tool classes.

Version 2B acceptance:

- A staff task can recover from invalid structured output by retrying with validation feedback.
- A staff task can execute at least one assistant-requested tool call and continue the model conversation.
- Tool execution is observable through events and does not bypass `ToolManager`.
- Step limits and tool-call limits produce clear task failure events.
- Existing `SinglePassStaffWorkflow` and PM-only mode remain supported.
- Orchestrators can switch workflow implementation through config without direct code changes.

### Version 2C: Asyncio Concurrent Staff Execution

Objective: make staff task execution concurrent while keeping the same state/message abstractions.

Tasks:

1. Add async orchestration path using `asyncio`.
2. Run child staff workflows concurrently.
3. Keep `TaskStore` as source of truth.
4. Use events/messages for notification.
5. Add timeout and failure handling.

Acceptance:

- Multiple staff tasks can run concurrently.
- Failed child tasks are visible to manager and project state.
- Manager review waits for completion criteria rather than direct staff calls.

### Version 2D: Distributed Execution Readiness

Objective: prepare the same interaction model for external workers.

Tasks:

1. Define store/bus contracts that can be backed by SQLite/Postgres/Redis.
2. Add serialization tests for tasks, events, and messages.
3. Define retry and idempotency expectations.
4. Keep project orchestration independent of storage implementation.

Acceptance:

- In-memory implementation can be replaced without changing workflow logic.
- Task/event/message models are safe to persist.

### Version 2E: Project Console and User Interaction

Status: pending.

Detailed design:

```text
docs/PROJECT_CONSOLE_DESIGN.md
```

Objective: add a minimal frontend interaction layer without making workflows or
orchestrators depend on UI code.

Planned phases:

1. Add `ProjectInteractionHub`.
2. Let `EventRecorder` optionally publish events and snapshots to the hub.
3. Add a local HTTP API.
4. Add a static web console.
5. Later, let runtime consume selected user commands and feedback.

Acceptance:

- user can see project status, staff, tasks, and event stream;
- user can submit feedback into the interaction hub;
- core runtime remains usable from CLI without the console;
- frontend never directly mutates workflow or orchestrator internals.

### Original Version 2 Capabilities

1. Project manager creates a structured `StaffingPlan`.
2. Runtime maps `StaffRolePlan` to `StaffProfileConfig`.
3. Runtime creates recruited staff inside the project.
4. Project manager creates tasks for recruited staff.
5. Staff execute tasks through the same workflow interface.
6. Project manager reviews staff outputs.
7. Project manager produces final `ProjectResult`.

Manager awareness must come from:

1. `TaskStore` state queries.
2. Manager inbox messages.
3. Project/task events.
4. Staff status only as supporting information.

## Version 3 Preview

Version 3 should deepen agent capabilities after multi-staff execution is stable.

Skill runtime starts in Version 3, not V2B. V2B should keep skills as selected
prompt instructions while tool execution and iterative workflow semantics
stabilize. A later skill runtime can then be designed as a reusable process
that may bundle prompt instructions, allowed tools, validation rules, and
possibly nested workflow behavior.

Built-in skills should reference Codex skill design principles: a skill is a
reusable method with instructions, capability requirements, allowed tools, and
validation expectations. It should not be modeled as a raw callable tool unless
it performs one concrete external action.

Candidates:

- Skill runtime execution
- Persistent project/task/event store
- Project memory retrieval
- Staff memory
- Streaming CLI/API output
- Web/API service layer
