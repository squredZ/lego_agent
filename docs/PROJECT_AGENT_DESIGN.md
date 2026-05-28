# Project-Oriented Agent Framework Design

## 1. Background

`lego_agent` is being redesigned as a project-oriented agent framework.

The framework input is a project goal. After receiving the goal, the system creates a `Project`. Every project must first create one primary project manager. The project manager is responsible for understanding the goal, planning the work, producing a staffing plan, coordinating execution in later phases, and delivering the final project result.

The previous `Organization` concept is removed. A project may contain a staff graph internally, but `Project` is the only top-level runtime concept.

## 2. Core Principles

1. Project-first
   The system starts from a project goal, not from a prebuilt organization.

2. Project manager is mandatory
   Every project must have exactly one primary project manager.

3. Project manager is also staff
   Project manager is not a special model class. It is a `Staff` configured with project management responsibilities and capabilities.

4. All project members are staff
   Project manager, engineer, reviewer, researcher, tester, and other roles share the same `Staff` data model.

5. Staff workflow is unified
   Every staff member follows the same abstract workflow. Role differences come from responsibilities, capabilities, assistant configuration, assigned tasks, and project context.

6. First version is project-manager-only
   Version 1 does not dynamically create and run recruited staff. The project manager outputs a `staffing_plan`. Dynamic staff creation and multi-staff execution are deferred to Version 2.

7. Runtime behavior should be observable
   Important lifecycle transitions, staff work steps, task state changes, and failures should produce clear logs or structured events. Logs and events must help beginners understand what happened without exposing secrets such as API keys or tokens.

## 2.1 Concept Overview

```mermaid
graph TD
    User[User Project Goal] --> Runtime[ProjectRuntime]
    Runtime --> Project[Project]
    Project --> PM[Primary Project Manager Staff]
    PM --> Workflow[SinglePassStaffWorkflow]
    Workflow --> Result[ProjectRunResult]

    PM --> StaffingPlan[StaffingPlan]
    StaffingPlan -. "Version 2" .-> RecruitedStaff[Recruited Staff]

    subgraph StaffModel[Unified Staff Model]
        PM
        RecruitedStaff
    end
```

## 3. Target Runtime Flow

Version 1 runtime:

```text
project goal
  -> create Project
  -> create primary project manager Staff
  -> create project task for manager
  -> project manager analyzes goal
  -> project manager outputs structured ProjectResult
  -> project completes
```

Version 1 output must include:

- project understanding
- assumptions
- risks
- staffing plan
- staffing profile resolution
- task breakdown
- execution plan
- final output

### 3.1 Version 1 Sequence

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI
    participant RT as ProjectRuntime
    participant ORCH as ProjectManagerOnlyOrchestrator
    participant WF as SinglePassStaffWorkflow
    participant A as Assistant

    U->>CLI: project run "project goal"
    CLI->>RT: run(goal, config)
    RT->>ORCH: create Project and PM Staff
    ORCH->>WF: run(project, manager, manager_task)
    WF->>WF: build context, select skills/tools, retrieve memory
    WF->>A: AssistantRequest
    A-->>WF: AssistantResponse
    WF->>WF: parse ProjectResult, update state
    WF-->>ORCH: WorkResult
    ORCH-->>RT: ProjectRunResult
    RT-->>CLI: ProjectRunResult
    CLI-->>U: human or JSON output
```

## 4. Domain Model

### 4.1 Project

`Project` is the top-level runtime aggregate.

```python
class Project(BaseModel):
    id: str
    goal: str
    name: str | None = None
    description: str | None = None

    status: ProjectStatus

    manager_id: str
    staff: dict[str, Staff] = {}
    tasks: dict[str, Task] = {}

    staffing_plan: StaffingPlan | None = None
    result: ProjectResult | None = None
    error: ProjectError | None = None

    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None

    metadata: dict[str, Any] = {}
```

### 4.1.1 Core Entity Relationship

```mermaid
graph TD
    Project[Project]
    Staff[Staff]
    Task[Task]
    Responsibility[Responsibility]
    Capability[Capability]
    StaffingPlan[StaffingPlan]
    StaffRolePlan[StaffRolePlan]
    ProjectResult[ProjectResult]

    Project -->|primary manager| Staff
    Project -->|project members| Staff
    Project -->|owns| Task
    Staff -->|has| Responsibility
    Staff -->|has| Capability
    Staff -->|assigned| Task
    ProjectResult -->|includes| StaffingPlan
    StaffingPlan -->|requires| StaffRolePlan
```

### 4.2 ProjectStatus

```python
class ProjectStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    STAFFING = "staffing"
    RUNNING = "running"
    REVIEWING = "reviewing"
    DONE = "done"
    FAILED = "failed"
```

Version 1 uses:

- `CREATED`
- `PLANNING`
- `DONE`
- `FAILED`

The other statuses are reserved for later phases.

### 4.3 Staff

`Staff` is the unified project member model.

```python
class Staff(BaseModel):
    id: str
    project_id: str

    name: str
    role: str
    title: str
    description: str | None = None

    responsibilities: list[Responsibility]
    capabilities: list[Capability]
    assistant: Assistant | None = None

    manager_id: str | None = None
    report_ids: list[str] = []

    status: StaffStatus
    current_task_id: str | None = None

    metadata: dict[str, Any] = {}
```

The project manager is represented as:

```python
role = "project_manager"
```

### 4.4 StaffStatus

```python
class StaffStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    OFFLINE = "offline"
```

### 4.5 Responsibility

Responsibilities describe what a staff member is accountable for.

Examples:

- requirements analysis
- planning
- staffing
- coordination
- implementation
- review
- testing

```python
class Responsibility(BaseModel):
    name: str
    description: str
```

### 4.6 Capability

Capabilities describe what a staff member can do.

Examples:

- task decomposition
- staff recruitment
- delegation
- code generation
- quality review
- test planning

```python
class Capability(BaseModel):
    name: str
    description: str
```

### 4.7 Task

`Task` represents work assigned to staff.

Version 1 creates one manager task for the project manager.

```python
class Task(BaseModel):
    id: str
    project_id: str

    title: str
    goal: str

    assigned_to: str | None = None
    created_by: str | None = None
    parent_task_id: str | None = None

    status: TaskStatus
    result: str | None = None
    error: TaskError | None = None

    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    metadata: dict[str, Any] = {}
```

### 4.8 StaffingPlan

Version 1 does not execute recruited staff. It only outputs a staffing plan.

```python
class StaffingPlan(BaseModel):
    required_roles: list[StaffRolePlan]
    rationale: str
```

```python
class StaffRolePlan(BaseModel):
    role: str
    title: str
    responsibilities: list[str]
    capabilities: list[str]
    task_focus: str
    priority: int = 1
```

### 4.8.1 StaffProfileResolution

Version 1 does not create recruited staff yet, but it resolves each planned role
to configured staff profiles so users can see whether the future project team
can be built from current configuration.

```python
class StaffProfileMatch(BaseModel):
    planned_role: str
    planned_title: str
    matched: bool
    profile_name: str | None = None
    profile_role: str | None = None
    profile_title: str | None = None
    reason: str
```

```python
class StaffProfileResolution(BaseModel):
    matches: list[StaffProfileMatch] = []
```

### 4.9 ProjectResult

`ProjectResult` is the structured project-level output.

```python
class ProjectResult(BaseModel):
    summary: str
    project_understanding: str
    assumptions: list[str] = []
    risks: list[str] = []
    staffing_plan: StaffingPlan
    task_breakdown: list[str] = []
    execution_plan: list[str] = []
    final_output: str
```

### 4.10 ProjectRunResult

`ProjectRunResult` is returned by CLI/API execution.

```python
class ProjectRunResult(BaseModel):
    run_id: str
    project_id: str
    project_goal: str
    status: ProjectStatus

    manager_id: str
    manager_name: str

    result: ProjectResult | None = None
    staffing_profile_resolution: StaffProfileResolution | None = None
    error: ProjectError | None = None
    events: list[ProjectEvent] = []

    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
```

### 4.11 ProjectEvent and TaskEvent

Events provide lightweight in-memory observability for Version 1.

```python
class ProjectEvent(BaseModel):
    id: str
    project_id: str
    type: str
    message: str
    level: EventLevel
    actor_id: str | None = None
    task_id: str | None = None
    data: dict[str, Any] = {}
    created_at: datetime
```

```python
class TaskEvent(BaseModel):
    id: str
    project_id: str
    task_id: str
    type: str
    message: str
    level: EventLevel
    actor_id: str | None = None
    data: dict[str, Any] = {}
    created_at: datetime
```

The initial `EventRecorder` appends events to the current `Project` and `Task`.
It is not persistent storage.

### 4.12 WorkContext

`WorkContext` is the contextual package used by `StaffWorkflow`.

It should not be stored directly on `Staff`. It is built for each task run.

```python
class WorkContext(BaseModel):
    project_id: str
    task_id: str
    staff_id: str

    project_goal: str
    task_goal: str

    role_context: str | None = None
    task_context: str | None = None
    memory_context: str | None = None
    tool_context: str | None = None
    skill_context: str | None = None

    variables: dict[str, Any] = {}
```

### 4.13 AssistantRequest and AssistantResponse

The assistant interface should use request and response models instead of a narrow `respond(staff, task, context)` signature.

```python
class OutputContract(BaseModel):
    name: str
    json_schema: dict[str, Any]
    instructions: str
```

```python
class AssistantRequest(BaseModel):
    project: Project
    staff: Staff
    task: Task
    context: WorkContext
    messages: list[Message] = []
    output_contract: OutputContract | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = {}
```

```python
class AssistantResponse(BaseModel):
    content: str
    structured: dict[str, Any] = {}
    raw: Any | None = None
    metadata: dict[str, Any] = {}
```

### 4.14 Tools

Tools represent callable external actions.

Examples:

- file read/write
- web search
- database query
- HTTP call
- running tests

```python
class ToolSpec(BaseModel):
    name: str
    description: str
    parameters_schema: dict[str, Any] = {}
```

```python
class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}
```

```python
class ToolResult(BaseModel):
    tool_name: str
    success: bool
    content: str | None = None
    error: str | None = None
    data: dict[str, Any] = {}
```

Version 1 defines tool interfaces and a noop implementation. It does not execute model-requested tool calls.

### 4.15 Skills

Skills represent reusable work methods, domain procedures, or expert workflows.

Tool and skill are intentionally separate:

```text
Tool = a callable action
Skill = a reusable method or process
```

Examples:

- requirements analysis
- technical design
- project planning
- code review
- test planning

```python
class SkillSpec(BaseModel):
    name: str
    description: str
    instructions: str
    required_capabilities: list[str] = []
    available_tools: list[str] = []
```

Version 1 injects selected skill instructions into prompts. It does not implement nested skill runtimes.

### 4.16 Memory

Memory is divided by scope:

```text
working memory: current task context
project memory: current project history
staff memory: one staff member's reusable experience
global memory: cross-project reusable knowledge
```

```python
class MemoryItem(BaseModel):
    id: str
    scope: str
    content: str
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    created_at: datetime
```

Version 1 defines memory interfaces and uses `NoopMemoryManager` or project events as simple memory. Long-term storage and vector retrieval are out of scope.

## 5. Agent Modules

The framework has these necessary agent modules:

1. State module
   Owns `Project`, `Staff`, `Task`, run state, and events.

2. Config module
   Loads project runtime config and staff profiles.

3. Registry module
   Registers responsibilities, capabilities, assistants, workflows, orchestrators, tools, skills, and output parsers.

4. Assistant module
   Connects to OpenAI-compatible model providers through `AssistantRequest -> AssistantResponse`.

5. Prompt module
   Builds prompts from project, staff, task, context, responsibilities, capabilities, skills, tools, and output contracts.

6. Capability module
   Describes what staff can do. Version 1 treats capabilities as prompt context. Later versions may execute capability functions.

7. Tool module
   Describes and later executes external actions. Version 1 uses noop tool management.

8. Skill module
   Describes and selects reusable work methods. Version 1 injects skill instructions into prompts.

9. Memory module
   Retrieves and stores useful context. Version 1 uses noop memory.

10. Workflow module
    Executes the unified staff workflow.

11. Orchestration module
    Runs project-level orchestration such as `project_manager_only`.

12. Output module
    Parses, validates, and falls back for structured outputs such as `ProjectResult`.

13. Observability module
    Records project and task events for debugging and later persistence.

### 5.1 Module Dependency Graph

```mermaid
graph LR
    CLI[CLI] --> Runtime[ProjectRuntime]
    Runtime --> Config[ConfigLoader]
    Runtime --> Registry[Registries]
    Runtime --> Orchestrator[ProjectManagerOnlyOrchestrator]

    Orchestrator --> Workflow[StaffWorkflow]
    Workflow --> Context[ContextManager]
    Workflow --> Memory[MemoryManager]
    Workflow --> Skills[SkillManager]
    Workflow --> Tools[ToolManager]
    Workflow --> Prompt[PromptBuilder]
    Workflow --> Assistant[Assistant]
    Workflow --> Output[OutputParser]
    Workflow --> State[StateManager]
    Workflow --> Events[EventRecorder]

    Registry --> Responsibilities[Responsibilities]
    Registry --> Capabilities[Capabilities]
    Registry --> SkillSpecs[Skill Specs]
    Registry --> ToolSpecs[Tool Specs]
    Registry --> AssistantFactories[Assistant Factories]
```

## 6. Unified Staff Workflow

All staff share one abstract workflow:

```text
receive_task
  -> build_context
  -> retrieve_memory
  -> select_skills
  -> select_tools
  -> plan_work
  -> execute_work
  -> parse_output
  -> update_memory
  -> report_result
```

Version 1 uses this workflow only for the project manager.

The project manager task is:

```text
Analyze the project goal, define assumptions and risks, create a staffing plan,
break down work, propose an execution plan, and produce an initial project result.
```

The workflow should be implemented with explicit hooks:

```python
class StaffWorkflow:
    def receive_task(...): ...
    def build_context(...): ...
    def retrieve_memory(...): ...
    def select_skills(...): ...
    def select_tools(...): ...
    def plan_work(...): ...
    def execute_work(...): ...
    def parse_output(...): ...
    def update_memory(...): ...
    def report_result(...): ...
```

Version 1 should provide:

- `SinglePassStaffWorkflow`
- `DefaultContextManager`
- `NoopMemoryManager`
- `NoopToolManager`
- `NoopSkillManager`
- `DefaultPromptBuilder`
- `ProjectResultOutputParser`

The project manager should not use a separate workflow class. It uses the same workflow with a project-manager output contract.

### 6.1 StaffWorkflow State Flow

```mermaid
graph TD
    Start([Start]) --> ReceiveTask
    ReceiveTask --> BuildContext
    BuildContext --> RetrieveMemory
    RetrieveMemory --> SelectSkills
    SelectSkills --> SelectTools
    SelectTools --> PlanWork
    PlanWork --> ExecuteWork
    ExecuteWork --> ParseOutput
    ParseOutput --> UpdateMemory
    UpdateMemory --> ReportResult
    ReportResult --> End([End])

    ExecuteWork -->|execution error| ReportResult
    ParseOutput -->|parse fallback or failure| ReportResult
```

### 6.2 Workflow Collaboration

```mermaid
graph TD
    Task[Task] --> Receive[receive_task]
    Staff[Staff] --> Receive
    Project[Project] --> Build[build_context]
    Receive --> Build

    Build --> Memory[retrieve_memory]
    Memory --> Skills[select_skills]
    Skills --> Tools[select_tools]
    Tools --> Plan[plan_work]
    Plan --> Prompt[PromptBuilder]
    Prompt --> Execute[execute_work]
    Execute --> Assistant[AssistantRequest -> AssistantResponse]
    Assistant --> Parse[parse_output]
    Parse --> Update[update_memory]
    Update --> Report[report_result]
    Report --> WorkResult[WorkResult]
```

## 7. Context, Tools, Skills, and Memory Interfaces

### 7.1 ContextManager

```python
class ContextManager:
    def build_context(
        self,
        project: Project,
        staff: Staff,
        task: Task,
    ) -> WorkContext:
        ...
```

Version 1 context includes project goal, task goal, staff responsibilities, and staff capabilities.

### 7.2 ToolManager

```python
class ToolManager:
    def list_tools(self, staff: Staff, task: Task) -> list[ToolSpec]:
        ...

    def call_tool(self, call: ToolCall) -> ToolResult:
        ...
```

Version 1 implements `NoopToolManager`. It may list configured tool specs, but does not execute assistant-requested tool calls.

### 7.3 SkillManager

```python
class SkillManager:
    def list_skills(self, staff: Staff, task: Task) -> list[SkillSpec]:
        ...

    def select_skills(
        self,
        staff: Staff,
        task: Task,
        context: WorkContext,
    ) -> list[SkillSpec]:
        ...
```

Version 1 implements `NoopSkillManager` or a simple configured-skill selector.

### 7.4 MemoryManager

```python
class MemoryManager:
    def retrieve(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        query: str,
    ) -> list[MemoryItem]:
        ...

    def remember(
        self,
        project: Project,
        staff: Staff,
        item: MemoryItem,
    ) -> None:
        ...
```

Version 1 implements `NoopMemoryManager`.

## 8. Assistant Configuration

Assistant configuration stays OpenAI-compatible.

```json
{
  "type": "openai",
  "model": "deepseek-v4-pro",
  "api_key": "sk-...",
  "base_url": "https://api.deepseek.com",
  "timeout_seconds": 30,
  "thinking": {
    "type": "enabled"
  },
  "reasoning_effort": "high",
  "token_limit": 4096
}
```

Supported token limit aliases:

- `token_limit`
- `tokenlimit`
- `max_output_tokens`

`OPENAI_API_KEY` and `OPENAI_BASE_URL` may be used for environment-based configuration.

## 9. Runtime Configuration

The new configuration should be project runtime oriented.

```json
{
  "project": {
    "default_manager_profile": "project_manager"
  },
  "orchestration": {
    "strategy": "project_manager_only"
  },
  "staff_profiles": {
    "project_manager": {
      "name": "Ava",
      "role": "project_manager",
      "title": "Project Manager",
      "responsibilities": [
        "requirements_analysis",
        "planning",
        "staffing",
        "coordination",
        "acceptance"
      ],
      "capabilities": [
        "task_decomposition",
        "staff_recruitment",
        "delegation",
        "quality_review"
      ],
      "assistant": {
        "type": "openai",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com",
        "timeout_seconds": 30,
        "reasoning_effort": "high",
        "token_limit": 4096
      }
    }
  },
  "modules": []
}
```

## 10. CLI Design

Target CLI:

```bash
lego-agent project run --config configs/project_runtime.json "Build a configurable agent framework"
```

JSON output:

```bash
lego-agent project run --config configs/project_runtime.json --json "Build a configurable agent framework"
```

The old organization CLI and configuration should be removed during the rewrite.

For the detailed runtime call chain from CLI entry to `ProjectRunResult`, see
[CLI Call Flow](CLI_CALL_FLOW.md).

## 11. Orchestration

Version 1 supports exactly one orchestration strategy:

```text
project_manager_only
```

The orchestrator must:

1. create a project
2. create the manager staff from the configured manager profile
3. create the manager task
4. run the project manager staff workflow
5. parse or construct `ProjectResult`
6. complete or fail the project
7. return `ProjectRunResult`

## 11.1 Staff Interaction Model

Version 2 should not make staff call each other directly. Staff interaction
should happen through project state, events, messages, and orchestration.

Core rule:

```text
Staff do not directly invoke other Staff.
Staff create/update Tasks, publish Events, and send Messages.
The Orchestrator decides what runs next.
```

### 11.1.1 Interaction Layers

```text
Task State: the source of truth
Event Log: what happened
Inbox Message: who should be notified
```

Example:

```text
Staff completes task
  -> Task.status = done
  -> Task.result = ...
  -> publish task_completed event
  -> send task_completed message to manager inbox
```

Manager awareness should come from:

1. `TaskStore` queries for reliable state.
2. `StaffMessage` inbox entries for notifications.
3. Project/task events for audit and debugging.
4. Staff status as supporting information.

### 11.1.2 Proposed Models

```python
class StaffMessage(BaseModel):
    id: str
    project_id: str
    sender_id: str
    recipient_id: str
    type: str
    task_id: str | None = None
    content: str
    data: dict[str, Any] = {}
    created_at: datetime
    read_at: datetime | None = None
```

```python
class StaffInbox(BaseModel):
    staff_id: str
    project_id: str
    messages: list[StaffMessage] = []
```

### 11.1.3 Proposed Interfaces

```python
class TaskStore(Protocol):
    def create(self, task: Task) -> Task: ...
    def update(self, task: Task) -> Task: ...
    def get(self, task_id: str) -> Task: ...
    def children_of(self, parent_task_id: str) -> list[Task]: ...
```

```python
class MessageBus(Protocol):
    def send(self, message: StaffMessage) -> None: ...
    def unread_for(self, staff_id: str, project_id: str) -> list[StaffMessage]: ...
    def mark_read(self, message_id: str) -> None: ...
```

```python
class TaskDispatcher:
    def assign(
        self,
        project: Project,
        task: Task,
        assignee: Staff,
        created_by: Staff,
    ) -> None:
        ...
```

```python
class TaskCompletionHandler:
    def complete(
        self,
        project: Project,
        task: Task,
        staff: Staff,
        result: WorkResult,
    ) -> None:
        ...
```

### 11.1.4 Manager Notification Flow

```mermaid
sequenceDiagram
    participant M as Manager Staff
    participant O as Orchestrator
    participant TS as TaskStore
    participant S as Worker Staff
    participant EB as EventBus
    participant MB as MessageBus

    M->>O: staffing/task plan
    O->>TS: create child tasks
    O->>EB: publish task_assigned
    S->>TS: claim assigned task
    S->>TS: update status=in_progress
    S->>EB: publish task_started
    S->>TS: update status=done, result=...
    S->>EB: publish task_completed
    EB->>MB: send task_completed message to manager
    O->>TS: check child task statuses
    O->>M: wake for review/synthesis
```

### 11.1.5 Implementation Strategy

Do not start with distributed async execution.

Version 2 should progress in three steps:

1. Synchronous multi-staff with event/message semantics.
   - Create recruited staff.
   - Create child tasks.
   - Execute staff tasks one by one.
   - Emit events and manager messages.
   - Manager reviews after all child tasks complete.

2. `asyncio` concurrent staff tasks.
   - Use the same stores and buses.
   - Replace sequential execution with concurrent task execution.

3. Distributed execution.
   - Replace in-memory stores/buses with Redis, database-backed queues, or workers.

The source of truth remains task state. Events and messages are notifications,
not the final authority.

### 11.2 Project Manager Only Orchestration

```mermaid
graph TD
    Goal[Project Goal] --> CreateProject[Create Project]
    CreateProject --> CreatePM[Create Project Manager Staff]
    CreatePM --> CreateTask[Create Manager Task]
    CreateTask --> RunWorkflow[Run SinglePassStaffWorkflow]
    RunWorkflow --> ParseResult[Parse ProjectResult]
    ParseResult --> HasResult{Valid result?}
    HasResult -->|yes| Done[Project status DONE]
    HasResult -->|no| Failed[Project status FAILED]
    Done --> RunResult[ProjectRunResult]
    Failed --> RunResult
```

### 11.3 Version Evolution

```mermaid
graph LR
    V1[V1 project_manager_only] --> V2[V2 project_manager_with_staff]
    V2 --> V3[V3 persistent memory and tool execution]

    V1 --> V1A[PM outputs staffing_plan]
    V2 --> V2A[Runtime creates recruited staff]
    V2 --> V2B[PM delegates tasks]
    V2 --> V2C[Staff execute same workflow]
    V3 --> V3A[Multi-round tool calling]
    V3 --> V3B[Long-term memory retrieval]
```

## 12. Version 1 Acceptance Criteria

Version 1 is complete when:

1. `Organization` is removed from public and internal runtime code.
2. `Project` is the only top-level runtime aggregate.
3. Every project creates exactly one primary project manager staff.
4. `project_manager_only` mode runs from CLI.
5. Dry-run mode returns a valid `ProjectRunResult`.
6. Real OpenAI-compatible assistant calls are supported.
7. The project manager output includes a valid `staffing_plan`.
8. Staff workflow has explicit hooks for context, memory, skills, tools, planning, execution, output parsing, and reporting.
9. Version 1 includes default/noop managers for context, memory, skills, and tools.
10. pytest covers model validation, config parsing, CLI, dry-run execution, workflow hooks, and error cases.
