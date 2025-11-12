# Conductor Parallel Execution - Key Files Index

## Critical Files for Understanding Parallel Execution

### 1. Parallel Orchestrator (Core Implementation)
**File**: `/home/user/Conductor/src/conductor/orchestrator_parallel.py` (645 lines)

Key Components:
- `ParallelOrchestrator` class - Main parallel execution engine
- `_initialize_mcp_pool()` - Creates N MCP clients and browsers
- `_execute_tasks_parallel()` - Launches parallel task execution
- `_process_dependent_tasks()` - Handles dependency-aware scheduling
- `_execute_task_with_semaphore()` - Semaphore-controlled execution
- `_execute_task_with_retry()` - Per-task retry logic
- Semaphore: `asyncio.Semaphore(max_parallel)`

Key Lines:
- Line 36-53: Initialization with semaphore creation
- Line 52: `self.semaphore = asyncio.Semaphore(self.max_parallel)`
- Line 100-135: MCP client pool initialization
- Line 169-226: Main task execution loop
- Line 227-276: Semaphore-controlled execution wrapper
- Line 195-225: Dependent task processing algorithm
- Line 622-643: Resource cleanup

### 2. Task Models (Data Structures)
**File**: `/home/user/Conductor/src/conductor/tasks/models.py` (257 lines)

Key Components:
- `TaskStatus` enum - PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
- `Task` class - Individual task with dependencies
- `TaskList` class - Collection with validation
- Circular dependency detection algorithm

Key Lines:
- Line 11-18: TaskStatus enum definition
- Line 48-165: Task model with all fields
- Line 107-113: Dependency validation
- Line 167-217: TaskList with circular dependency detection algorithm
- Line 194-206: DFS-based cycle detection
- Line 230-246: `get_runnable_tasks()` method

### 3. Configuration (Execution Settings)
**File**: `/home/user/Conductor/src/conductor/utils/config.py` (120 lines)

Key Components:
- `ExecutionConfig` class with parallel settings
- `max_parallel_tasks` field (1-10)
- `parallel_mode` boolean flag

Key Lines:
- Line 46-57: ExecutionConfig definition
- Line 49-54: max_parallel_tasks field definition
- Line 55-57: parallel_mode flag definition

### 4. CLI Entry Point (Command-Line Interface)
**File**: `/home/user/Conductor/src/conductor/main.py` (306 lines)

Key Components:
- `--parallel N` / `-p N` command-line flag
- Configuration loading and CLI argument handling
- Orchestrator selection logic (sequential vs parallel)

Key Lines:
- Line 75-81: --parallel CLI option definition
- Line 119-124: CLI parallel handling
- Line 166-175: Orchestrator selection based on parallel_mode

### 5. Sequential Orchestrator (For Comparison)
**File**: `/home/user/Conductor/src/conductor/orchestrator.py` (458 lines)

Key Components:
- Simple sequential execution for comparison
- Dependency checking logic pattern
- Same execution flow, but without parallelization

Key Lines:
- Line 122-161: Simple for-loop task execution
- Line 163-169: _dependencies_met() method

### 6. Session Persistence (State Management)
**File**: `/home/user/Conductor/src/conductor/browser/session.py` (250 lines)

Key Components:
- `SessionManager` class for persistence
- JSONL append-only log format
- Session recovery across crashes

Key Lines:
- Line 60-84: SessionManager initialization
- Line 86-119: add_session() for recording new sessions
- Line 190-202: _persist_session() for JSONL logging
- Line 230-249: load_sessions() for recovery

### 7. MCP Client (Connection Management)
**File**: `/home/user/Conductor/src/conductor/mcp/client.py` (245 lines)

Key Components:
- `MCPClient` class for individual connections
- Connection pooling support
- Async connection management

Key Lines:
- Line 31-60: MCPClient initialization
- Line 61-137: Connection methods (stdio and SSE)
- Line 139-151: Disconnect/cleanup methods

### 8. Browser Controller (Browser Automation)
**File**: `/home/user/Conductor/src/conductor/mcp/browser.py` (572 lines)

Key Components:
- `BrowserController` class for browser operations
- Tab management (create, switch, close)
- Snapshot-based element interaction

Key Lines:
- Line 33-42: BrowserController initialization
- Line 367-396: create_tab() method
- Line 433-458: switch_tab() method
- Line 460-485: close_tab() method

### 9. Retry Logic (Exponential Backoff)
**File**: `/home/user/Conductor/src/conductor/utils/retry.py` (115 lines)

Key Components:
- `exponential_backoff()` function
- Jitter implementation
- `retry_async()` for async function retries

Key Lines:
- Line 31-57: exponential_backoff() calculation
- Line 60-114: retry_async() decorator/wrapper
- Line 16-28: jitter calculation

### 10. Task Loader (YAML Parsing)
**File**: `/home/user/Conductor/src/conductor/tasks/loader.py` (196 lines)

Key Components:
- `TaskLoader` class for YAML parsing
- Validation of tasks
- Missing: execution_order syntax support

Key Lines:
- Line 36-66: load_from_file() method
- Line 68-130: load_from_dict() with validation
- Line 172-195: Task summary extraction

## Configuration Files

### Default Configuration
**File**: `/home/user/Conductor/config/default.yaml`

Key Sections:
- execution.parallel_mode (default: false)
- execution.max_parallel_tasks (default: 1, range: 1-10)

### Example Tasks with Dependencies
**File**: `/home/user/Conductor/examples/simple-tasks.yaml`

Shows basic task definition with dependencies.

### Complex Example with Parallel Syntax
**File**: `/home/user/Conductor/examples/tasks.yaml`

Note: Line 178-189 shows `execution_order: parallel:` syntax
WARNING: This syntax is NOT currently parsed by TaskLoader!

## Test Files

### Main Test Suite
**File**: `/home/user/Conductor/test_conductor_fixes.py` (340+ lines)

Tests:
- BrowserController snapshot interactions
- Orchestrator task execution
- Repository selection
- Completion detection
- Full task execution flow

## Documentation Files

### PRD (Product Requirements)
**File**: `/home/user/Conductor/PRD.md`

Key Sections:
- FR-031: Multiple browser tabs for parallel workstreams
- Requirements for task execution
- Technology stack (asyncio, Textual, MCP)

### Stories (User Stories)
**File**: `/home/user/Conductor/STORIES.md`

Key Sections:
- Future Story: Parallel Execution (marked as backlog)
- Status: Listed as future enhancement

### README
**File**: `/home/user/Conductor/README.md`

Features section mentions batch processing and task orchestration.
Line 300: [ ] Parallel execution (unchecked TODO)

## Summary of What's Implemented vs Missing

### Fully Implemented and Production-Ready
1. ParallelOrchestrator with semaphore control
2. Dependency validation (circular detection)
3. Dependency-aware task scheduling
4. Session persistence
5. Retry logic with exponential backoff
6. MCP client pooling
7. CLI --parallel flag
8. TUI integration
9. Async/await architecture

### Partially Implemented
1. Test coverage (sequential works well, parallel has basic tests)

### Not Implemented
1. YAML execution_order syntax parsing (documented but not loaded)
2. Task prioritization in scheduler
3. Task cancellation/preemption
4. Tab health monitoring
5. Resource constraints per task
6. Metrics/observability (Prometheus)

## How to Use Parallel Execution

### Quick Start
```bash
cd /home/user/Conductor
conductor run examples/tasks.yaml --parallel 3
```

### With Configuration File
```bash
# Edit ~/.conductor/config.yaml
execution:
  parallel_mode: true
  max_parallel_tasks: 5

# Then run without --parallel flag
conductor run examples/tasks.yaml
```

### With Dependencies
```bash
# Edit tasks.yaml
tasks:
  - id: task-1
    dependencies: []           # Starts immediately
  
  - id: task-2
    dependencies: [task-1]     # Waits for task-1
  
  - id: task-3
    dependencies: [task-1]     # Waits for task-1
    # task-2 and task-3 will run in parallel
```

