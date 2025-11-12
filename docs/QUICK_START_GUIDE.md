# 🚀 Conductor Quick Start Guide

## Welcome to Conductor!

This guide will get you orchestrating Claude Code sessions in minutes.

---

## 📋 Table of Contents
1. [Initial Setup](#initial-setup)
2. [Configuring MCP Server](#configuring-mcp-server)
3. [Creating Task Manifests](#creating-task-manifests)
4. [Parallel Execution](#parallel-execution)
5. [Running Your First Session](#running-your-first-session)
6. [Pro Tips](#pro-tips)

---

## 🎯 Initial Setup

### 1. Install Conductor
```bash
# Clone the repository
git clone https://github.com/karolswdev/Conductor.git
cd Conductor

# Create Python 3.11+ environment
python3.12 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install Conductor
pip install -e ".[dev]"

# Initialize configuration
conductor init
```

### 2. Start Your MCP Server
```bash
# In a separate terminal, start the Playwright MCP server
npx @anthropic/playwright-mcp

# Or for a specific port/host:
npx @anthropic/playwright-mcp --port 8931 --host 0.0.0.0
```

---

## 🔧 Configuring MCP Server

### Default Configuration
After running `conductor init`, you'll have `~/.conductor/config.yaml`:

```yaml
# ~/.conductor/config.yaml
mcp:
  server_url: stdio://playwright-mcp  # Default stdio connection
  timeout: 30.0
  max_retries: 3
```

### Custom MCP Server Configurations

#### 1. **Local MCP on Different Port**
```yaml
mcp:
  server_url: "http://localhost:8931/sse"
  timeout: 30.0
  max_retries: 3
```

#### 2. **Remote MCP Server (Different Machine)**
```yaml
# For controlling browser on another computer
mcp:
  server_url: "http://192.168.1.100:8931/sse"  # IP of remote machine
  timeout: 60.0  # Increase timeout for network latency
  max_retries: 5
```

#### 3. **WebSocket MCP Connection**
```yaml
mcp:
  server_url: "ws://localhost:8932/mcp"
  timeout: 30.0
  max_retries: 3
```

#### 4. **Multiple Configuration Files**
Create different configs for different scenarios:

```bash
# Create configs directory
mkdir -p ~/.conductor/configs/

# Local development
cat > ~/.conductor/configs/local.yaml << EOF
mcp:
  server_url: stdio://playwright-mcp
  timeout: 30.0
EOF

# Remote Windows PC
cat > ~/.conductor/configs/remote-windows.yaml << EOF
mcp:
  server_url: "http://192.168.1.50:8931/sse"
  timeout: 60.0
auth:
  timeout: 180  # More time for remote login
EOF

# Use specific config
conductor run tasks.yaml --config ~/.conductor/configs/remote-windows.yaml
```

---

## 📝 Creating Task Manifests

### Basic Task Structure

```yaml
# tasks.yaml
tasks:
  - id: "UNIQUE-ID"           # Required: Unique identifier
    name: "Short Name"         # Required: Display name (max 20 chars)
    prompt: "Full prompt"      # Required: What Claude should do
    expected_deliverable: ""   # Required: What you expect
    priority: high|medium|low  # Optional: Task priority
    repository: "user/repo"    # Optional: Target repository
```

### Complete Task Manifest Example

```yaml
# my-project-tasks.yaml

# Global configuration (optional)
config:
  default_repository: "karolswdev/my-project"
  default_pr_strategy: "normal"  # aggressive|normal|patient|manual
  default_auto_pr_timeout: 3600  # 1 hour

# Task definitions
tasks:
  # Simple task
  - id: "SETUP-001"
    name: "Project Setup"
    prompt: "Create a Python project structure with src/, tests/, and docs/ folders, plus a README.md"
    expected_deliverable: "Basic project structure with folders and README"
    priority: high

  # Task with dependencies
  - id: "API-001"
    name: "Create REST API"
    prompt: |
      Build a FastAPI REST API with:
      - User authentication endpoints
      - CRUD operations for a 'Task' model
      - Input validation with Pydantic
      - Proper error handling
    expected_deliverable: "Working FastAPI application with all endpoints"
    priority: high
    dependencies: ["SETUP-001"]  # Runs after SETUP-001

  # Task with custom retry policy
  - id: "TEST-001"
    name: "Add Tests"
    prompt: "Write comprehensive pytest tests for the API with >90% coverage"
    expected_deliverable: "test_api.py with full test coverage"
    priority: medium
    retry_policy:
      max_attempts: 5        # Try harder for tests
      backoff_factor: 1.5
      initial_delay: 10000   # 10 seconds
    dependencies: ["API-001"]

  # Task with aggressive PR strategy
  - id: "DOC-001"
    name: "API Documentation"
    prompt: "Generate OpenAPI documentation and a docs/API.md guide"
    expected_deliverable: "Complete API documentation"
    priority: low
    pr_strategy: "aggressive"     # Create PR after 30 minutes
    auto_pr_timeout: 1800         # 30 minutes
    dependencies: ["API-001"]

  # Parallel tasks (same dependencies = can run in parallel)
  - id: "DEPLOY-001"
    name: "Add Dockerfile"
    prompt: "Create a production-ready Dockerfile for the API"
    expected_deliverable: "Dockerfile with multi-stage build"
    priority: medium
    dependencies: ["TEST-001", "DOC-001"]

  - id: "CI-001"
    name: "Setup CI/CD"
    prompt: "Create GitHub Actions workflow for testing and deployment"
    expected_deliverable: ".github/workflows/ci.yml"
    priority: medium
    dependencies: ["TEST-001", "DOC-001"]  # Same deps as DEPLOY-001
```

### Task Dependency Patterns

```yaml
# Sequential execution
tasks:
  - id: "A"
    name: "First"
    prompt: "Do A"
    expected_deliverable: "A done"

  - id: "B"
    name: "Second"
    prompt: "Do B"
    expected_deliverable: "B done"
    dependencies: ["A"]  # B runs after A

  - id: "C"
    name: "Third"
    prompt: "Do C"
    expected_deliverable: "C done"
    dependencies: ["B"]  # C runs after B

# Parallel execution (diamond pattern)
tasks:
  - id: "BASE"
    name: "Setup"
    prompt: "Initial setup"
    expected_deliverable: "Setup complete"

  - id: "PARALLEL-1"
    name: "Frontend"
    prompt: "Build frontend"
    expected_deliverable: "Frontend built"
    dependencies: ["BASE"]

  - id: "PARALLEL-2"
    name: "Backend"
    prompt: "Build backend"
    expected_deliverable: "Backend built"
    dependencies: ["BASE"]  # Same dependency = can run in parallel

  - id: "INTEGRATE"
    name: "Integration"
    prompt: "Integrate frontend and backend"
    expected_deliverable: "Full app working"
    dependencies: ["PARALLEL-1", "PARALLEL-2"]  # Waits for both
```

---

## 🚀 Parallel Execution

### Current Status: Sequential (v0.1.0)
**Important**: The current implementation (v0.1.0) processes tasks **sequentially** based on dependencies. However, the architecture is designed for parallel execution.

### How Dependencies Work Now
```yaml
tasks:
  - id: "TASK-1"
    name: "First Task"
    prompt: "Do something"
    expected_deliverable: "Done"

  - id: "TASK-2A"
    name: "Parallel A"
    prompt: "Can run with 2B"
    expected_deliverable: "Done"
    dependencies: ["TASK-1"]

  - id: "TASK-2B"
    name: "Parallel B"
    prompt: "Can run with 2A"
    expected_deliverable: "Done"
    dependencies: ["TASK-1"]  # Same deps = parallel ready
```

### Enabling Parallel Execution (Roadmap)

The architecture supports parallel execution through:
1. **Multiple browser tabs** - Already implemented in browser controller
2. **Task queue management** - DAG resolution identifies parallel tasks
3. **MCP session handling** - Supports multiple sessions

To enable parallel execution in future versions:

```yaml
# Future: config for parallel execution
execution:
  max_parallel_tasks: 2  # Run up to 2 tasks simultaneously
  parallel_strategy: "aggressive"  # or "conservative"

tasks:
  - id: "PARALLEL-1"
    name: "Task 1"
    prompt: "First parallel task"
    expected_deliverable: "Done"
    allow_parallel: true  # Explicitly allow

  - id: "PARALLEL-2"
    name: "Task 2"
    prompt: "Second parallel task"
    expected_deliverable: "Done"
    allow_parallel: true
```

### Workaround for Parallel-like Behavior

Until true parallel execution is implemented, you can:

1. **Run multiple Conductor instances** with different task files:
```bash
# Terminal 1
conductor run frontend-tasks.yaml --config frontend.yaml

# Terminal 2
conductor run backend-tasks.yaml --config backend.yaml
```

2. **Use task groups** to batch related work:
```yaml
# Group related tasks that Claude can handle together
tasks:
  - id: "MULTI-001"
    name: "Multiple Files"
    prompt: |
      Create these three files simultaneously:
      1. models.py with User and Task models
      2. views.py with CRUD endpoints
      3. tests.py with unit tests
    expected_deliverable: "Three working Python files"
```

---

## 🎮 Running Your First Session

### 1. Basic Run
```bash
# Activate environment
source venv/bin/activate

# Run with default settings
conductor run my-tasks.yaml
```

### 2. With Custom Theme
```bash
# Available themes: default, cyberpunk, minimal, solarized-dark, dracula
conductor run my-tasks.yaml --theme cyberpunk
```

### 3. With Custom Repository
```bash
conductor run my-tasks.yaml --repo karolswdev/specific-project
```

### 4. Debug Mode
```bash
conductor run my-tasks.yaml --debug
```

### 5. Without TUI (Simple Mode)
```bash
conductor run my-tasks.yaml --no-tui
```

### 6. Authentication Flow
When you run Conductor:
1. Browser opens automatically
2. You have 120 seconds to log into Claude Code
3. Press Enter in terminal when ready
4. Conductor takes over and processes tasks

---

## 💡 Pro Tips

### 1. Task Design Best Practices
- **Keep prompts specific**: Clear instructions = better results
- **Set realistic deliverables**: Be explicit about what you expect
- **Use dependencies wisely**: Only add dependencies when truly needed
- **Leverage retry policies**: Critical tasks should have more attempts

### 2. PR Strategy Selection
- **aggressive** (30m): For quick iterations and testing
- **normal** (60m): Balanced approach for most tasks
- **patient** (120m): For complex tasks needing more time
- **manual**: Never auto-create, wait for human

### 3. Session Management
```bash
# Check branch names created
cat ~/.conductor/branches.log

# View session history
ls ~/.conductor/sessions/

# Resume a failed session (future feature)
conductor resume <session-id>
```

### 4. Testing Your Setup
```yaml
# test-connection.yaml
tasks:
  - id: "TEST"
    name: "Connection Test"
    prompt: "Create a file called test.txt with 'Conductor works!' inside"
    expected_deliverable: "test.txt file created"
    priority: high
    retry_policy:
      max_attempts: 1  # Quick test
```

Run: `conductor run test-connection.yaml --no-tui --debug`

### 5. Monitoring Progress

The TUI shows:
- **Task Queue**: All tasks with status indicators
- **Current Execution**: Live progress with percentage
- **Metrics**: Success/failure rates, timing
- **Browser Preview**: ASCII art of current page

Keyboard shortcuts:
- `↑/↓` or `j/k`: Navigate
- `p`: Peek at browser
- `c`: Create PR manually
- `s`: Skip current task
- `r`: Retry failed task
- `?`: Help
- `q`: Quit

---

## 🚨 Common Issues

### MCP Connection Failed
```yaml
# Check server is running
ps aux | grep playwright-mcp

# Test with curl
curl http://localhost:8931/health

# Update config with correct URL
mcp:
  server_url: "http://localhost:8931/sse"
```

### Tasks Not Running in Expected Order
- Check dependencies are correctly specified
- Verify no circular dependencies
- Use `--debug` to see task resolution

### Browser Not Opening
```yaml
# Ensure headless is false
auth:
  headless: false  # Must be false to see browser
```

---

## 📚 Advanced Configuration

### Full Configuration Reference
```yaml
# ~/.conductor/config.yaml

# Authentication settings
auth:
  timeout: 120          # Seconds to wait for manual login
  headless: false       # Show browser window
  check_interval: 2.0   # How often to check if logged in

# MCP server settings
mcp:
  server_url: "stdio://playwright-mcp"  # or http://host:port
  timeout: 30.0         # Request timeout
  max_retries: 3        # Connection retry attempts

# Retry logic settings
retry:
  initial_delay: 5.0    # Seconds before first retry
  backoff_factor: 2.0   # Multiply delay by this each retry
  max_delay: 300.0      # Maximum delay (5 minutes)
  jitter: 0.2           # ±20% randomization
  max_attempts: 3       # Default max attempts

# UI settings
ui:
  theme: "cyberpunk"    # UI theme
  refresh_rate: 10      # FPS for TUI updates
  show_splash: true     # Show ASCII art on start
  splash_duration: 2.0  # Seconds to show splash

# Default repository (optional)
default_repository: "karolswdev/my-project"

# Session settings (future)
session:
  persist: true         # Save session state
  auto_resume: false    # Resume on failure
  branch_prefix: "claude/"  # Git branch prefix
```

---

## 🎯 Ready to Orchestrate!

You now have everything you need to:
1. ✅ Configure Conductor for any MCP server
2. ✅ Create sophisticated task manifests with dependencies
3. ✅ Understand the parallel execution roadmap
4. ✅ Run and monitor your Claude Code automation

Start with simple tasks, then build up to complex workflows. Conductor will handle the orchestration while you focus on what to build!

**Happy Orchestrating!** 🎭🚀

---

*Questions? Issues? Visit: https://github.com/karolswdev/Conductor*