# 🏥 Doctor Mode - Diagnostic Guide

## Overview

The `conductor doctor` command runs comprehensive diagnostic checks to verify that Conductor is properly configured and can connect to MCP and control the browser.

## When to Use Doctor Mode

Run doctor mode when:
- 🆕 Setting up Conductor for the first time
- 🐛 Experiencing connection or browser issues
- 🔧 After changing configuration
- 🧪 Testing a new MCP server setup
- 📡 Verifying remote browser configuration

## Usage

### Basic Usage

```bash
conductor doctor
```

This will:
1. ✓ Check MCP server connectivity
2. ✓ Launch a browser window
3. ✓ Navigate to google.com
4. ✓ Ask you to confirm the browser is visible

### Headless Mode

If you want to run diagnostics without visual confirmation:

```bash
conductor doctor --headless
```

This skips the user visibility check and runs the browser in headless mode.

### Debug Mode

For detailed diagnostic output:

```bash
conductor doctor --debug
```

## Diagnostic Checks

### 1. MCP Connection Check

**What it checks:**
- Can connect to the MCP server at configured URL
- Server responds to connection requests
- Connection is stable

**Possible results:**
- ✓ **PASS**: Successfully connected to MCP server
- ✗ **FAIL**: Cannot connect to MCP server

**If it fails:**
```bash
# Ensure MCP server is running
npx @anthropic/playwright-mcp

# Or if using custom port/host:
npx @anthropic/playwright-mcp --port 8931 --host 0.0.0.0
```

### 2. Browser Launch Check

**What it checks:**
- Can launch a browser instance via MCP
- Browser responds to control commands
- Browser is in correct mode (headed/headless)

**Possible results:**
- ✓ **PASS**: Browser launched successfully
- ✗ **FAIL**: Browser failed to launch
- ⊘ **SKIP**: Skipped due to MCP connection failure

**If it fails:**
```bash
# Install browser dependencies
playwright install chromium

# Or if using a different browser:
playwright install msedge
```

### 3. Navigation Test

**What it checks:**
- Can navigate to a test URL (google.com)
- Page loads successfully
- Current URL can be retrieved

**Possible results:**
- ✓ **PASS**: Successfully navigated to test URL
- ✗ **FAIL**: Navigation failed
- ⊘ **SKIP**: Skipped due to browser launch failure

**If it fails:**
- Check network connectivity
- Verify firewall settings
- Check if using proxy settings

### 4. User Visibility Check

**What it checks:**
- User can see the browser window
- Browser is on correct display
- Window is not minimized or hidden

**Possible results:**
- ✓ **PASS**: User confirmed browser is visible
- ✗ **FAIL**: User cannot see browser
- ⊘ **SKIP**: Skipped in headless mode
- ! **WARN**: Could not get user confirmation

**If it fails:**
- Check if browser is on different monitor
- Look for minimized windows
- Verify display settings
- Try running without headless flag

## Example Output

### Successful Run

```
🏥 Conductor Doctor - Running Diagnostics

→ Checking MCP connection...
  ✓ MCP connection successful

→ Checking browser launch...
  ✓ Browser launched (headed mode)

→ Checking navigation (google.com)...
  ✓ Navigation successful

→ Checking user visibility...

Please check your screen:
  • Can you see a browser window?
  • Is it showing Google's homepage?
  • Can you interact with it?

Can you see the browser window with Google? [y/n]: y
  ✓ User confirmed visibility

→ Cleaning up...
  ✓ Browser closed
  ✓ MCP disconnected

======================================================================

📊 Diagnostic Results

┌────────────────────┬────────────┬─────────────────────────────────────┐
│ Check              │ Status     │ Message                             │
├────────────────────┼────────────┼─────────────────────────────────────┤
│ MCP Connection     │ ✓ PASS     │ Successfully connected to MCP       │
│ Browser Launch     │ ✓ PASS     │ Browser launched successfully       │
│ Navigation Test    │ ✓ PASS     │ Successfully navigated to URL       │
│ User Visibility    │ ✓ PASS     │ User confirmed browser is visible   │
└────────────────────┴────────────┴─────────────────────────────────────┘

Summary:
  Passed: 4
  Failed: 0
  Warnings: 0
  Skipped: 0

✓ All checks passed! Conductor is healthy.
```

### Failed Run

```
🏥 Conductor Doctor - Running Diagnostics

→ Checking MCP connection...
  ✗ MCP connection failed: Failed to connect after 3 attempts: Connection refused

→ Checking browser launch...
  ⊘ Browser launch skipped

→ Checking navigation (google.com)...
  ⊘ Navigation test skipped

→ Checking user visibility...
  ⊘ Visibility check skipped

→ Cleaning up...
  ✓ MCP disconnected

======================================================================

📊 Diagnostic Results

┌────────────────────┬────────────┬─────────────────────────────────────┐
│ Check              │ Status     │ Message                             │
├────────────────────┼────────────┼─────────────────────────────────────┤
│ MCP Connection     │ ✗ FAIL     │ Failed to connect to MCP server     │
│ Browser Launch     │ ⊘ SKIP     │ Skipped (MCP not connected)         │
│ Navigation Test    │ ⊘ SKIP     │ Skipped (browser not launched)      │
│ User Visibility    │ ⊘ SKIP     │ Skipped (browser not launched)      │
└────────────────────┴────────────┴─────────────────────────────────────┘

Summary:
  Passed: 0
  Failed: 1
  Warnings: 0
  Skipped: 3

✗ Some checks failed. Please review above.

Troubleshooting tips:
  • Ensure MCP server is running: npx @anthropic/playwright-mcp
  • Check firewall settings if using remote MCP
  • Verify browser installation: playwright install chromium
  • Check config at ~/.conductor/config.yaml
```

## Configuration

Doctor mode uses your existing Conductor configuration at `~/.conductor/config.yaml`.

You can override configuration with options:

```bash
# Use custom config file
conductor doctor --config /path/to/config.yaml

# Enable debug output
conductor doctor --debug

# Run in headless mode
conductor doctor --headless
```

## Common Issues

### Issue: "Module not found" errors

**Solution:**
```bash
# Reinstall dependencies
pip install -e ".[dev]"
```

### Issue: Browser opens but on wrong display

**Solution:**
- Manually move browser window to primary display
- Update display configuration in your OS
- Use headless mode if display doesn't matter

### Issue: MCP connection timeout

**Solution:**
```bash
# Increase timeout in config
mcp:
  timeout: 60.0  # Increase from default 30s
  max_retries: 5
```

### Issue: Remote browser not responding

**Solution:**
1. Verify remote server is running:
   ```bash
   # On remote machine
   npx @playwright/mcp@latest --port 8931 --host 0.0.0.0
   ```

2. Check network connectivity:
   ```bash
   ping <remote-ip>
   telnet <remote-ip> 8931
   ```

3. Update config with correct remote URL:
   ```yaml
   mcp:
     server_url: "http://<remote-ip>:8931"
   ```

## Integration with E2E Testing

Doctor mode is particularly useful when setting up end-to-end testing:

```bash
# 1. Setup your test environment
conductor init

# 2. Verify everything works
conductor doctor

# 3. If doctor passes, your e2e tests should work
conductor run e2e-tests.yaml
```

## Next Steps

After running `conductor doctor` successfully:

1. ✓ Create your task file (`tasks.yaml`)
2. ✓ Run your first automation: `conductor run tasks.yaml`
3. ✓ Review the [Quick Start Guide](QUICK_START_GUIDE.md)
4. ✓ Explore [Parallel Execution](PARALLEL_EXECUTION.md)

## Feedback

If doctor mode identifies issues that aren't covered here, please:
- Open an issue: https://github.com/karolswdev/Conductor/issues
- Include the full doctor output with `--debug` flag
- Share your configuration (with sensitive data removed)
