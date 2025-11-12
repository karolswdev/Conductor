# Parallel Execution Guide

## Overview

Conductor supports **parallel task execution**, allowing you to run multiple tasks concurrently to maximize throughput and reduce overall execution time. This feature is particularly useful when you have independent tasks that can be processed simultaneously.

## Configuration

### Method 1: CLI Flag (Recommended for One-off Use)

Use the `--parallel` or `-p` flag to enable parallel execution:

```bash
# Run 3 tasks in parallel
conductor run tasks.yaml --parallel 3

# Run 5 tasks in parallel
conductor run tasks.yaml -p 5

# Maximum is 10 concurrent tasks
conductor run tasks.yaml --parallel 10
```

### Method 2: Configuration File (Recommended for Persistent Use)

Edit `~/.conductor/config.yaml`:

```yaml
execution:
  parallel_mode: true
  max_parallel_tasks: 3  # Number of concurrent tasks
```

Then run normally:

```bash
conductor run tasks.yaml
```

### Method 3: Interactive Wizard

When running `conductor init --wizard`, you'll be prompted for execution settings:

```
Parallel execution mode? [y/N]: y
Maximum parallel tasks (1-10) [1]: 3
```

## How It Works

### Architecture

```
Conductor Orchestrator
├─ Semaphore (max_parallel_tasks)
│  ├─ Task 1 → Browser Session 1 → MCP Client 1
│  ├─ Task 2 → Browser Session 2 → MCP Client 2
│  └─ Task 3 → Browser Session 3 → MCP Client 3
└─ Task Queue (waiting tasks)
```

### Execution Flow

1. **Initialization**: Creates N browser sessions (where N = max_parallel_tasks)
2. **Authentication**: User authenticates once (shared across sessions)
3. **Parallel Execution**:
   - Tasks without dependencies start immediately
   - Up to N tasks run concurrently
   - When a task completes, the next runnable task starts
4. **Dependency Handling**: Tasks wait for their dependencies to complete
5. **Resource Management**: Each task gets its own browser session

## Examples

### Example 1: Independent Tasks

**tasks.yaml**:
```yaml
tasks:
  - id: "TEST-001"
    name: "Unit Tests"
    prompt: "Run all unit tests"
    expected_deliverable: "Test results"

  - id: "LINT-001"
    name: "Code Linting"
    prompt: "Lint all code files"
    expected_deliverable: "Lint report"

  - id: "DOC-001"
    name: "Update Docs"
    prompt: "Update API documentation"
    expected_deliverable: "Updated docs"
```

**Run in parallel**:
```bash
conductor run tasks.yaml --parallel 3
```

**Result**: All 3 tasks run simultaneously, completing in ~1/3 the time!

### Example 2: Tasks with Dependencies

**tasks.yaml**:
```yaml
tasks:
  # These run first (no dependencies)
  - id: "BUILD-001"
    name: "Build Frontend"
    prompt: "Build frontend assets"
    expected_deliverable: "Built assets"

  - id: "BUILD-002"
    name: "Build Backend"
    prompt: "Compile backend code"
    expected_deliverable: "Compiled binaries"

  # These wait for dependencies
  - id: "TEST-001"
    name: "Test Frontend"
    prompt: "Test frontend"
    expected_deliverable: "Test results"
    dependencies: ["BUILD-001"]

  - id: "TEST-002"
    name: "Test Backend"
    prompt: "Test backend"
    expected_deliverable: "Test results"
    dependencies: ["BUILD-002"]

  # This waits for all tests
  - id: "DEPLOY-001"
    name: "Deploy"
    prompt: "Deploy to staging"
    expected_deliverable: "Deployment confirmation"
    dependencies: ["TEST-001", "TEST-002"]
```

**Run with 2 parallel tasks**:
```bash
conductor run tasks.yaml --parallel 2
```

**Execution timeline**:
```
Time  | Slot 1        | Slot 2
------|---------------|----------------
0-5m  | BUILD-001     | BUILD-002
5-10m | TEST-001      | TEST-002
10-15m| DEPLOY-001    | (idle)
```

### Example 3: Repository-Specific Tasks

```yaml
tasks:
  - id: "REPO-001"
    name: "Update Repo 1"
    prompt: "Add feature X to repo 1"
    expected_deliverable: "Feature X implemented"
    repository: "user/repo1"

  - id: "REPO-002"
    name: "Update Repo 2"
    prompt: "Add feature Y to repo 2"
    expected_deliverable: "Feature Y implemented"
    repository: "user/repo2"

  - id: "REPO-003"
    name: "Update Repo 3"
    prompt: "Add feature Z to repo 3"
    expected_deliverable: "Feature Z implemented"
    repository: "user/repo3"
```

**Run all repos in parallel**:
```bash
conductor run tasks.yaml --parallel 3
```

**Benefit**: Update 3 repositories simultaneously!

## Performance Comparison

### Sequential vs Parallel

**Sequential Execution** (default):
```
Task 1: ████████████ (5 min)
Task 2:             ████████████ (5 min)
Task 3:                         ████████████ (5 min)
Total:  ═══════════════════════════════════ 15 min
```

**Parallel Execution** (3 concurrent):
```
Task 1: ████████████ (5 min)
Task 2: ████████████ (5 min)
Task 3: ████████████ (5 min)
Total:  ═══════════ 5 min
```

**Time Savings**: 66% reduction (from 15 min to 5 min)!

## Resource Requirements

### Memory Usage

| Parallel Tasks | Estimated Memory |
|----------------|------------------|
| 1 (sequential) | ~100 MB          |
| 3 parallel     | ~300 MB          |
| 5 parallel     | ~500 MB          |
| 10 parallel    | ~1 GB            |

### CPU Usage

Each browser session uses:
- ~10-20% CPU (idle)
- ~30-50% CPU (active execution)

**Recommendation**: For most machines, 3-5 parallel tasks is optimal.

## Best Practices

### 1. Start Small

Begin with 2-3 parallel tasks to understand behavior:
```bash
conductor run tasks.yaml --parallel 2
```

### 2. Group Independent Tasks

Organize tasks so independent ones can run together:
```yaml
# Good: All independent
tasks:
  - id: "A"
    # no dependencies
  - id: "B"
    # no dependencies
  - id: "C"
    # no dependencies

# Suboptimal: Chain of dependencies
tasks:
  - id: "A"
  - id: "B"
    dependencies: ["A"]
  - id: "C"
    dependencies: ["B"]
```

### 3. Monitor Resources

Watch system resources:
```bash
# Linux/Mac
htop

# Check memory
free -h

# Windows
Task Manager
```

### 4. Consider Task Duration

Parallel execution works best when tasks have similar duration:
- ✅ 3 tasks × 5 minutes each = good parallelization
- ⚠️ 1 task × 15 minutes + 2 tasks × 1 minute = less benefit

### 5. Remote Browser Setup

For parallel execution with remote browsers, ensure:
- Sufficient network bandwidth
- Low latency connection
- Remote server has enough resources

## TUI Display

The TUI shows all parallel tasks in real-time:

```
┌─ Task Queue ──────┬─ Current Execution ─────┐
│ ▶ TASK-001 [Run] │ Task: TASK-001          │
│ ▶ TASK-002 [Run] │ Status: Running (1/3)   │
│ ▶ TASK-003 [Run] │ Progress: ████░░ 67%    │
│ ▷ TASK-004 [Wait]│                          │
└───────────────────┴──────────────────────────┘

Note: Multiple tasks marked with ▶ are running concurrently
```

## Troubleshooting

### Issue: "Too many open files"

**Cause**: Running too many parallel tasks

**Solution**: Reduce max_parallel_tasks or increase system limits:
```bash
# Linux/Mac - increase file descriptor limit
ulimit -n 4096
```

### Issue: High memory usage

**Cause**: Too many browser sessions

**Solution**: Reduce parallel tasks:
```bash
conductor run tasks.yaml --parallel 2  # Instead of 5
```

### Issue: Tasks interfere with each other

**Cause**: Shared resources or race conditions

**Solution**: Add explicit dependencies:
```yaml
tasks:
  - id: "TASK-001"
    # ...
  - id: "TASK-002"
    dependencies: ["TASK-001"]  # Force sequential
```

### Issue: One task blocks others

**Cause**: Long-running task holding a slot

**Solution**:
1. Break long tasks into smaller ones
2. Increase max_parallel_tasks
3. Run long tasks separately

## Advanced Configuration

### Config File Options

```yaml
execution:
  parallel_mode: true
  max_parallel_tasks: 5

  # Future options (not yet implemented):
  # task_timeout: 3600  # Max time per task
  # retry_failed_immediately: false
  # priority_scheduling: true
```

### Per-Task Priority (Future)

```yaml
tasks:
  - id: "HIGH-001"
    priority: high  # Runs first
    # ...
  - id: "LOW-001"
    priority: low   # Runs when slots available
    # ...
```

## When NOT to Use Parallel Execution

❌ **Don't use parallel for**:
- Tasks with many dependencies (limited benefit)
- Very short tasks (<1 minute each)
- When system resources are limited
- When tasks modify shared state
- During initial setup/testing

✅ **Use parallel for**:
- Independent tasks
- Long-running tasks (>5 minutes)
- Repository-specific updates
- Test suite runs
- Documentation updates

## Comparison Table

| Feature              | Sequential | Parallel (3) | Parallel (10) |
|---------------------|------------|--------------|---------------|
| Setup Time          | Fast       | Medium       | Slow          |
| Memory Usage        | Low        | Medium       | High          |
| CPU Usage           | Low        | Medium       | High          |
| Time for 10 tasks   | 50 min     | ~17 min      | ~5 min        |
| Resource Efficiency | High       | Medium       | Low           |
| Complexity          | Simple     | Medium       | Complex       |

## FAQ

**Q: What's the maximum number of parallel tasks?**
A: 10 concurrent tasks. This limit ensures system stability.

**Q: Can I run more than 10 tasks total?**
A: Yes! You can have 100+ tasks in your YAML. Only 10 will run *concurrently*.

**Q: Do parallel tasks share the same browser?**
A: No, each parallel slot gets its own browser session.

**Q: What happens if a parallel task fails?**
A: It's retried according to its retry policy, then marked as failed. Other tasks continue.

**Q: Can I change parallel settings during execution?**
A: No, you must restart Conductor with new settings.

**Q: Does parallel work with --no-tui?**
A: Technically yes, but TUI provides much better visibility. Console mode falls back to sequential.

**Q: How does authentication work in parallel mode?**
A: You authenticate once, and the session is shared across all browser instances.

## Performance Tips

### 1. Optimize Task Count

```bash
# Good: Tasks match parallel slots
conductor run tasks.yaml --parallel 3  # For 3, 6, 9... tasks

# Suboptimal: Uneven distribution
conductor run tasks.yaml --parallel 3  # For 10 tasks (3+3+3+1)
```

### 2. Use Appropriate Hardware

**Minimum**:
- 4 GB RAM (for 1-2 parallel)
- Dual-core CPU

**Recommended**:
- 8 GB RAM (for 3-5 parallel)
- Quad-core CPU

**Optimal**:
- 16 GB RAM (for 10 parallel)
- 8-core CPU

### 3. Network Considerations

For remote browser setups:
- Minimum: 10 Mbps
- Recommended: 50 Mbps
- Optimal: 100+ Mbps (for 10 parallel)

## Summary

Parallel execution in Conductor provides:
- ✅ **Faster overall execution** (up to 10x for independent tasks)
- ✅ **Better resource utilization** (max out your CPU/network)
- ✅ **Flexible configuration** (1-10 concurrent tasks)
- ✅ **Smart dependency handling** (automatic sequencing)
- ✅ **Real-time visibility** (TUI shows all running tasks)

**Recommended Settings**:
- **Development**: 2-3 parallel tasks
- **Production**: 3-5 parallel tasks
- **Heavy workloads**: 5-10 parallel tasks (with good hardware)

Start with:
```bash
conductor run tasks.yaml --parallel 3
```

And adjust based on your needs!

---

**Need help?** Check the troubleshooting section or review logs with `--debug` flag.
