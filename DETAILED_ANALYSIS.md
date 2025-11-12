# Conductor - Parallel Task Execution Analysis

## Executive Summary

Conductor **DOES support parallel task execution** with a dedicated `ParallelOrchestrator` implementation already in place. However, it also has a sequential version for simpler use cases. The parallel execution is:

- **Implemented**: Full parallel orchestrator with semaphore-based concurrency control
- **Configurable**: Via CLI (`--parallel N`) or config file (`execution.max_parallel_tasks`)
- **Dependency-aware**: Respects task dependencies correctly
- **Resource-managed**: Uses asyncio semaphores and independent MCP clients per task
- **TUI-integrated**: Works seamlessly with the Terminal User Interface

## 1. Current Task Execution Architecture

### Sequential Execution (Default)
**File**: `/src/conductor/orchestrator.py`

```
┌─────────────────────────────────────────┐
│   Orchestrator (Sequential)             │
├─────────────────────────────────────────┤
│ • Single MCP client connection          │
│ • Single browser instance               │
│ • Tasks execute one at a time           │
│ • Simple for-loop over task list        │
│ • Dependency checking before each task  │
└─────────────────────────────────────────┘
```

**Key Code** (orchestrator.py:122-161):
```python
async def _execute_tasks(self) -> None:
    """Execute all tasks in order."""
    for task in self.task_list.tasks:
        # Check if dependencies are met
        if not self._dependencies_met(task):
            task.skip()
            continue
        
        # Execute task
        await self._execute_task(task)
```

**Characteristics**:
- No concurrent execution
- Tasks run sequentially, one per browser tab
- Useful for simple use cases or resource-constrained environments
- Default mode when no parallel configuration is specified

### Parallel Execution (Implemented)
**File**: `/src/conductor/orchestrator_parallel.py`

```
┌──────────────────────────────────────────────────────┐
│   ParallelOrchestrator                               │
├──────────────────────────────────────────────────────┤
│ • N MCP client connections (pool)                    │
│ • N independent browser instances                    │
│ • Asyncio semaphore for concurrency control         │
│ • Tasks execute in parallel up to max_parallel      │
│ • Dependency-aware task scheduling                   │
│ • Real-time TUI updates for each task               │
└──────────────────────────────────────────────────────┘
```

**Key Configuration** (config.py:46-57):
```python
class ExecutionConfig(BaseModel):
    """Task execution configuration."""
    
    max_parallel_tasks: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Maximum number of tasks to run in parallel (1-10)",
    )
    parallel_mode: bool = Field(
        default=False, description="Enable parallel task execution"
    )
```

**Characteristics**:
- Configurable 1-10 concurrent tasks
- Independent MCP client and browser for each parallel slot
- Semaphore-based concurrency control
- Proper dependency resolution with iterative processing
- TUI integration with real-time updates for all tasks

## 2. Task Runner/Executor Implementation

### Async Foundation
- **Framework**: asyncio (Python's built-in async library)
- **Concurrency Control**: asyncio.Semaphore
- **Context Manager**: Used for safe resource acquisition/release

### Parallel Orchestrator Flow

**File**: `orchestrator_parallel.py:169-226`

1. **Initialize Phase**
   ```python
   async def _initialize_mcp_pool(self) -> None:
       """Initialize pool of MCP clients and browsers."""
       for i in range(self.max_parallel):
           client = MCPClient(...)
           await client.connect()
           browser = BrowserController(client)
           self.mcp_clients.append(client)
           self.browsers.append(browser)
   ```

2. **Task Execution with Semaphore**
   ```python
   async def _execute_task_with_semaphore(self, task: Task) -> None:
       async with self.semaphore:  # Enforce max_parallel limit
           browser_index = len(self.running_tasks) % len(self.browsers)
           browser = self.browsers[browser_index]
           await self._execute_task_with_retry(task, browser)
   ```

3. **Dependent Task Processing**
   ```python
   async def _process_dependent_tasks(self) -> None:
       """Process tasks that have dependencies."""
       while iteration < max_iterations:
           # Find tasks with met dependencies
           runnable = [t for t in tasks if deps_met(t)]
           
           if not runnable:
               break
           
           # Execute all runnable tasks in parallel
           await asyncio.gather(*coroutines, return_exceptions=True)
   ```

### Retry Logic
**File**: `utils/retry.py`

```python
async def retry_async(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 5.0,
    backoff_factor: float = 2.0,
    max_delay: float = 300.0,
    jitter: float = 0.2,
) -> Any:
    """
    Retry with exponential backoff and jitter.
    Formula: delay = min(initial * (factor^attempt), max) + random jitter
    """
```

**Features**:
- Exponential backoff (2x multiplier by default)
- Configurable jitter (±20% randomization)
- Per-task retry configuration via RetryPolicy
- Respects max_delay cap (5 minutes default)

## 3. Task Dependencies Handling

### Dependency Validation
**File**: `tasks/models.py:181-216`

TaskList validates:
1. **Unique IDs**: All task IDs must be unique
2. **Dependency Existence**: All dependencies must refer to existing tasks
3. **Circular Dependencies**: Depth-first search to detect cycles

```python
def has_cycle(task_id: str, visited: set, rec_stack: set) -> bool:
    """Check for circular dependencies using DFS."""
    visited.add(task_id)
    rec_stack.add(task_id)
    
    for dep in dep_map.get(task_id, []):
        if dep not in visited:
            if has_cycle(dep, visited, rec_stack, dep_map):
                return True
        elif dep in rec_stack:  # Back edge = cycle
            return True
    
    rec_stack.remove(task_id)
    return False
```

### Dependency-Aware Execution

**Sequential Mode** (orchestrator.py:163-169):
```python
def _dependencies_met(self, task: Task) -> bool:
    """Check if task dependencies are met."""
    for dep_id in task.dependencies:
        dep_task = self.task_list.get_task(dep_id)
        if not dep_task or dep_task.status != TaskStatus.COMPLETED:
            return False
    return True
```

**Parallel Mode** (orchestrator_parallel.py:195-225):
```python
async def _process_dependent_tasks(self) -> None:
    """Process tasks that have dependencies."""
    # Iteratively find and execute tasks with satisfied dependencies
    # Allows earlier completion of independent task groups
    # to trigger dependent tasks sooner
```

### Task Execution States
**File**: `tasks/models.py:11-18`

```python
class TaskStatus(str, Enum):
    PENDING = "pending"     # Not yet started
    RUNNING = "running"     # Currently executing
    COMPLETED = "completed" # Finished successfully
    FAILED = "failed"       # Encountered error
    SKIPPED = "skipped"     # Dependency not met
```

## 4. State Management

### In-Memory State
**File**: `tasks/models.py:48-165`

Each Task object maintains:
```python
# Identity
id: str                              # Unique identifier
name: str                            # Display name

# Configuration
prompt: str                          # Task instruction
dependencies: List[str]              # Prerequisite task IDs
retry_policy: RetryPolicy            # Retry configuration

# Runtime State
status: TaskStatus                   # Current state
created_at: datetime                 # Creation timestamp
started_at: Optional[datetime]       # When execution started
completed_at: Optional[datetime]     # When execution finished
session_id: Optional[str]            # Claude Code session ID
branch_name: Optional[str]           # Git branch created
error_message: Optional[str]         # Error if failed
retry_count: int                     # Number of retries attempted
```

### Session Persistence
**File**: `browser/session.py:60-249`

```python
class SessionManager:
    """Manages Claude Code sessions and tracks branch names."""
    
    def __init__(self, log_file: Optional[Path] = None):
        # JSONL log file for append-only persistence
        self.log_file = Path.home() / ".conductor" / "sessions.jsonl"
        self.sessions: List[SessionInfo] = []
```

**Persistence Features**:
- Append-only JSONL log (one session per line)
- Survives application crashes
- Maintains rolling log of all sessions
- Tracks timestamps for each session

**Example Session Log Entry**:
```json
{
  "session_id": "session_011CV4beKrFjCAcPw3r7tC3u",
  "task_id": "AUTH-001",
  "branch_name": "claude/auth-tests-011CV4beKrFjCAcPw3r7tC3u",
  "started_at": "2024-11-12T20:53:14.123456",
  "url": "https://claude.ai/code/session_011CV4beKrFjCAcPw3r7tC3u"
}
```

### Parallel Execution State Tracking
**File**: `orchestrator_parallel.py:56-58`

```python
self.running_tasks: Dict[str, Task] = {}      # Currently executing
self.completed_tasks: List[Task] = []         # Successfully finished
self.failed_tasks: List[Task] = []            # Encountered errors
```

## 5. Resource Management

### Semaphore-Based Concurrency Control
**File**: `orchestrator_parallel.py:36-53`

```python
def __init__(self, config: Config, task_list: TaskList):
    # Semaphore limits concurrent tasks
    self.max_parallel = config.execution.max_parallel_tasks
    self.semaphore = asyncio.Semaphore(self.max_parallel)
    
    # MCP clients - one per parallel slot
    self.mcp_clients: List[MCPClient] = []
    self.browsers: List[BrowserController] = []
```

**How it works**:
```python
async def _execute_task_with_semaphore(self, task: Task) -> None:
    async with self.semaphore:  # Acquire semaphore slot
        # Only self.max_parallel tasks can be here simultaneously
        await self._execute_task_with_retry(task, browser)
    # Release semaphore slot when done
```

### Resource Cleanup
**File**: `orchestrator_parallel.py:622-643`

```python
async def _cleanup(self) -> None:
    """Clean up all resources."""
    # Close all browsers
    for browser in self.browsers:
        try:
            await browser.close()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
    
    # Disconnect all MCP clients
    for client in self.mcp_clients:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting MCP client: {e}")
```

### Tab Management
Each BrowserController maintains independent tabs:
- **Create Tab**: `browser.create_tab()` - Creates new browser tab
- **Switch Tab**: `browser.switch_tab(index)` - Switches between tabs
- **Independent State**: Each tab has its own session/context

## 6. Configuration Options for Parallel Execution

### Command-Line Options
**File**: `main.py:75-81`

```bash
conductor run tasks.yaml --parallel 3
# or
conductor run tasks.yaml -p 3
```

**CLI Parameters**:
- `--parallel N` or `-p N`: Enable parallel with N concurrent tasks
- Valid range: 1-10
- Overrides config file settings

### Configuration File
**File**: `config/default.yaml:31-38`

```yaml
execution:
  parallel_mode: false              # Enable/disable
  max_parallel_tasks: 1             # Concurrent limit (1-10)
  # Examples:
  #   1 = Sequential execution (default)
  #   3 = Run up to 3 tasks simultaneously
  #   5 = Run up to 5 tasks simultaneously
```

### Config Loading
**File**: `main.py:166-175`

```python
async def run_orchestrator_tui(config, task_list):
    """Run the TUI orchestrator (parallel or sequential based on config)."""
    if config.execution.parallel_mode:
        from conductor.orchestrator_parallel import run_with_tui_parallel
        await run_with_tui_parallel(config, task_list)
    else:
        from conductor.orchestrator_tui import run_with_tui
        await run_with_tui(config, task_list)
```

## 7. What's Implemented ✓

### Core Features
- ✓ Full ParallelOrchestrator with semaphore control
- ✓ Independent MCP client pool per parallel slot
- ✓ Asyncio-based concurrent execution
- ✓ Dependency-aware task scheduling
- ✓ Configurable 1-10 parallel tasks
- ✓ CLI flag `--parallel N` for quick enablement
- ✓ Configuration file support
- ✓ Exponential backoff with jitter
- ✓ Session persistence across runs
- ✓ TUI integration with real-time updates
- ✓ Proper error handling and cleanup
- ✓ Per-task retry policies
- ✓ Circular dependency detection

### Testing
- Partial test coverage in `test_conductor_fixes.py`
- Tests for browser controller, orchestrator, and completion detection

## 8. What's Missing or Could Be Improved

### Task Scheduling Syntax (Not Implemented)
The example `tasks.yaml` includes this syntax:
```yaml
execution_order:
  - "INIT-001"
  - parallel:          # ← Not implemented in loader
    - "AUTH-001"
    - "BUG-001"
  - "DOC-001"
```

**Status**: Documented in examples but TaskLoader doesn't parse this syntax.
**Impact**: Currently depends on dependency declarations for parallel resolution.

### Features Listed as Future
From STORIES.md and PRD.md:
1. Cloud sync across machines
2. Plugin system
3. Web-based dashboard
4. Advanced scheduling (beyond dependencies)
5. Task priority-based preemption

### Potential Improvements

#### 1. Explicit Parallel Groups
```python
# Could add to Task model
parallel_group: Optional[str]  # Tasks with same group run together
```

#### 2. Task Prioritization
```python
# Currently has priority enum but not used in scheduling
priority: Priority = Field(default=Priority.MEDIUM)
# Could implement priority-based semaphore (high priority cuts queue)
```

#### 3. Resource Constraints
```python
# Add per-task resource limits
cpu_cores: int = 1
memory_gb: float = 0.5
# Scheduler respects these constraints
```

#### 4. Advanced Dependency Conditions
```python
# Current: must complete before dependent runs
# Could add:
depends_on:
  - task_id: "AUTH-001"
    condition: "completed"  # or "successful", "any_status"
```

#### 5. Task Weights/Priorities in Semaphore
Current: Simple FIFO with semaphore.
Could: Implement priority queue instead of asyncio.gather().

#### 6. Dynamic Task Generation
```python
# Could support tasks that spawn sub-tasks
spawn_dependent_tasks:
  - template: "test-{module}"
    parameters:
      - modules: ["auth", "db", "api"]
```

#### 7. Monitoring & Observability
- Prometheus metrics export
- Detailed execution trace logging
- Performance profiling per task
- Resource usage tracking

## 9. Known Limitations & Blockers

### 1. Single Browser Authentication
**Blocker**: Currently only the first browser authenticates to Claude Code
**Impact**: All browser instances share the same authentication session
**Mitigation**: Parallel tasks execute in different tabs of the same browser session
**Solution**: Could implement multi-user auth or browser session sharing

### 2. MCP Server Connection Limits
**Potential Issue**: Creating N MCP clients means N processes
**Impact**: Resource consumption scales with max_parallel_tasks
**Mitigation**: Default limit of 10 parallel tasks is reasonable
**Solution**: Could implement connection pooling if needed

### 3. Tab Management Simplicity
**Current**: Basic tab switching by index
**Issue**: If a tab crashes, index mapping breaks
**Solution**: Implement tab health checking and recovery

### 4. Task State Synchronization
**Current**: In-memory task state with append-only log persistence
**Issue**: No transactional guarantees between state and persistence
**Solution**: Could implement SQLite database for stronger consistency

### 5. No Task Preemption
**Current**: Once a task starts, it runs to completion or timeout
**Issue**: Can't interrupt or pause a running task
**Solution**: Could add task cancellation support with cleanup

## 10. Architecture Recommendations

### For Immediate Use
1. Use `--parallel 3` or `--parallel 5` for most workloads
2. Define clear task dependencies for correct execution order
3. Use retry policies for flaky tasks
4. Monitor first few runs before scaling up

### For Future Enhancement
1. **Implement YAML `execution_order` syntax** - Would provide explicit control
2. **Add task priority-based scheduling** - Allow high-priority tasks to start sooner
3. **Implement task cancellation** - Support stopping long-running tasks
4. **Add resource constraints** - Limit concurrent tasks by resource needs
5. **Enhance monitoring** - Collect metrics and expose via Prometheus

### For Enterprise Use
1. **Task persistence database** - SQLite/PostgreSQL for state
2. **Distributed execution** - Support running tasks on multiple machines
3. **Role-based access** - Control who can create/run tasks
4. **Audit logging** - Full trace of all task executions
5. **Webhook integration** - Trigger external systems on task completion

## Conclusion

Conductor **successfully supports parallel task execution** with a well-architected implementation. The `ParallelOrchestrator` properly handles:

- Concurrent task execution via asyncio and semaphores
- Dependency resolution with iterative scheduling
- Resource management through MCP client pooling
- State persistence and recovery
- Real-time TUI updates

The implementation is production-ready for:
- Running 1-10 concurrent Claude Code tasks
- Tasks with dependencies
- Configurable retry policies
- Long-running operations (10+ minutes)

For advanced use cases (cloud sync, plugin system, dynamic task generation), additional features would be needed but the core architecture is solid and extensible.

