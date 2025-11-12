# Remote Browser Setup Guide

## Overview

This guide explains how to run Conductor on one machine (e.g., Mac) while controlling a browser on another machine (e.g., Windows PC). This is useful for:

- Using Windows-specific browsers (Edge, IE)
- Separating browser resources from orchestration
- Remote development setups
- Testing on different platforms

## Architecture

```
┌─────────────────┐         Network          ┌──────────────────┐
│   Mac (Client)  │◄─────────────────────────►│ Windows (Server) │
│                 │                           │                  │
│   Conductor     │    MCP Protocol (HTTP)    │  Playwright MCP  │
│   Orchestrator  │    Port 8931              │  Browser: Edge   │
└─────────────────┘                           └──────────────────┘
```

## Setup Instructions

### Step 1: Windows PC (Browser Server)

On your Windows PC, start the Playwright MCP server with remote access enabled:

```bash
npx @playwright/mcp@latest \
  --port 8931 \
  --host 0.0.0.0 \
  --allowed-hosts * \
  --browser msedge
```

**Parameter Explanation:**
- `--port 8931` - Server listens on port 8931
- `--host 0.0.0.0` - Accepts connections from any network interface (not just localhost)
- `--allowed-hosts *` - Allows connections from any host (see security notes below)
- `--browser msedge` - Uses Microsoft Edge browser

**Important**: Make sure port 8931 is open in Windows Firewall:

1. Open Windows Defender Firewall
2. Click "Advanced settings"
3. Click "Inbound Rules" → "New Rule"
4. Select "Port" → Next
5. Select "TCP" and enter port `8931`
6. Allow the connection
7. Name it "Playwright MCP Server"

### Step 2: Get Windows PC IP Address

On Windows, find your local IP address:

```cmd
ipconfig
```

Look for "IPv4 Address" under your active network adapter (usually something like `192.168.1.100`).

### Step 3: Mac (Conductor Client)

#### Option A: Using Configuration File

Create or edit `~/.conductor/config.yaml`:

```yaml
# MCP server configuration for remote Windows browser
mcp:
  server_url: "http://192.168.1.100:8931/sse"  # Replace with your Windows PC IP
  timeout: 30.0
  max_retries: 3

# Authentication settings
auth:
  timeout: 120
  check_interval: 2.0
  headless: false  # Set to true if you don't need to see the browser

# Other settings...
retry:
  max_attempts: 3
  initial_delay: 5.0
  backoff_factor: 2.0
  max_delay: 300.0
  jitter: 0.2

ui:
  theme: "default"
  refresh_rate: 10
  show_splash: true
  splash_duration: 2.0

# Optional: Set default repository
default_repository: "yourusername/your-repo"
```

#### Option B: Using Configuration Wizard

Run the interactive wizard:

```bash
conductor init --wizard
```

When prompted for "MCP server URL", enter:
```
http://192.168.1.100:8931
```

(Replace `192.168.1.100` with your Windows PC's IP address)

#### Option C: Command Line Override

You can also override the MCP server URL at runtime (though this requires code modification):

Edit `~/.conductor/config.yaml` temporarily or pass via environment variable:

```bash
# Set environment variable
export CONDUCTOR_MCP_URL="http://192.168.1.100:8931"

# Run Conductor
conductor run tasks.yaml
```

### Step 4: Test Connection

Create a simple test task file `test-connection.yaml`:

```yaml
tasks:
  - id: "TEST-001"
    name: "Connection Test"
    prompt: "Please confirm the browser is connected by typing 'Connected' in response."
    expected_deliverable: "Confirmation that browser is working"
```

Run it:

```bash
conductor run test-connection.yaml
```

If everything is configured correctly:
1. Conductor on Mac will connect to Windows PC
2. Edge browser will open on Windows
3. You'll see the Claude Code interface
4. Log in manually when prompted
5. Task will be submitted

## Network Configuration Examples

### Same Local Network

If both machines are on the same local network (e.g., home WiFi):

```yaml
mcp:
  server_url: "http://192.168.1.100:8931/sse"  # Local IP
```

### Different Networks (VPN/Tailscale)

If using VPN or Tailscale:

```yaml
mcp:
  server_url: "http://100.64.1.5:8931/sse"  # Tailscale IP
```

### Port Forwarding

If exposing over the internet (not recommended without security):

```yaml
mcp:
  server_url: "http://your-public-ip:8931/sse"
```

## Security Considerations

⚠️ **Important Security Notes:**

### Current Setup (Development)
Your current command uses `--allowed-hosts *` which accepts connections from **any** host. This is:
- ✅ **Good for**: Local development, testing
- ❌ **Bad for**: Production, public networks, internet exposure

### Recommended Production Setup

For production or when connected to untrusted networks:

```bash
# Windows PC - Restrict to specific client
npx @playwright/mcp@latest \
  --port 8931 \
  --host 0.0.0.0 \
  --allowed-hosts "192.168.1.50"  # Mac's IP address only
  --browser msedge
```

Or use localhost tunneling with SSH:

```bash
# On Mac, create SSH tunnel to Windows
ssh -L 8931:localhost:8931 user@windows-pc

# Windows runs MCP server on localhost only
npx @playwright/mcp@latest \
  --port 8931 \
  --host 127.0.0.1  # Localhost only
  --browser msedge

# Mac config uses localhost
# mcp:
#   server_url: "http://localhost:8931/sse"
```

### Firewall Rules

**Windows Firewall** should restrict:
- Only allow connections from trusted IP addresses
- Only on port 8931
- Only for the Playwright MCP process

**Mac Firewall**: No special rules needed (client only)

## Troubleshooting

### Connection Refused

**Error**: `Failed to connect to MCP server`

**Solutions**:
1. Verify Windows MCP server is running:
   ```cmd
   netstat -an | findstr 8931
   ```
   Should show: `0.0.0.0:8931` or `[::]:8931`

2. Check Windows Firewall allows port 8931

3. Verify Mac can reach Windows:
   ```bash
   ping 192.168.1.100
   telnet 192.168.1.100 8931
   ```

4. Try with `curl`:
   ```bash
   curl http://192.168.1.100:8931
   ```

### Timeout Errors

**Error**: `Connection timeout`

**Solutions**:
1. Increase timeout in config:
   ```yaml
   mcp:
     timeout: 60.0  # Increase from 30
   ```

2. Check network latency:
   ```bash
   ping -c 10 192.168.1.100
   ```

3. Ensure both machines are on same network segment (no VLANs blocking)

### Browser Not Opening

**Error**: Browser doesn't appear on Windows

**Solutions**:
1. Verify Edge is installed on Windows
2. Check MCP server logs on Windows for errors
3. Try a different browser:
   ```bash
   npx @playwright/mcp@latest --browser chromium ...
   ```

### "Allowed Hosts" Error

**Error**: `Host not allowed`

**Solutions**:
1. Check `--allowed-hosts` includes your Mac's IP
2. Use `*` for testing (security risk)
3. Add specific IP addresses:
   ```bash
   --allowed-hosts "192.168.1.50,192.168.1.51"
   ```

## Performance Optimization

### Reduce Network Latency

1. **Use Wired Connection**: Ethernet instead of WiFi
2. **Same Subnet**: Keep both machines on same network segment
3. **Increase Timeouts**: For slower networks:
   ```yaml
   mcp:
     timeout: 60.0
   auth:
     timeout: 180
     check_interval: 3.0
   ```

### Bandwidth Considerations

Screenshots and browser state transfer can use bandwidth:

1. **Reduce screenshot frequency** in browser peek:
   ```python
   # If using auto-update
   update_interval: 15.0  # Instead of 10.0
   ```

2. **Lower screenshot resolution** (future feature)

## Advanced Configuration

### Using ngrok for Remote Access

If you need to access from outside your local network:

**Windows PC:**
```bash
# Install ngrok
ngrok http 8931

# Note the forwarding URL: https://abc123.ngrok.io
```

**Mac config.yaml:**
```yaml
mcp:
  server_url: "https://abc123.ngrok.io"
```

### Docker Setup (Alternative)

Run MCP server in Docker on Windows:

```dockerfile
# Dockerfile
FROM mcr.microsoft.com/playwright:latest
RUN npm install -g @playwright/mcp
EXPOSE 8931
CMD ["npx", "@playwright/mcp@latest", "--port", "8931", "--host", "0.0.0.0"]
```

```bash
docker build -t playwright-mcp .
docker run -p 8931:8931 playwright-mcp
```

## Example Complete Workflow

### 1. Start Windows MCP Server

```cmd
cd C:\Users\YourName\playwright-mcp
npx @playwright/mcp@latest --port 8931 --host 0.0.0.0 --allowed-hosts * --browser msedge
```

Output should show:
```
Playwright MCP Server running on http://0.0.0.0:8931
Browser: msedge
Allowed hosts: *
```

### 2. Configure Mac Conductor

```bash
# Create config if needed
conductor init --wizard

# Or manually edit
vim ~/.conductor/config.yaml
```

Set server URL to Windows PC IP:
```yaml
mcp:
  server_url: "http://192.168.1.100:8931/sse"
```

### 3. Run Your Tasks

```bash
# On Mac
conductor run examples/simple-tasks.yaml
```

**Expected behavior:**
1. Mac: Conductor TUI starts
2. Windows: Edge browser opens
3. Windows: Navigates to claude.ai/code
4. You: Log in manually on Windows browser
5. Mac: Press Enter to confirm ready
6. Windows: Browser executes tasks
7. Mac: TUI shows progress
8. Windows: PRs created, tasks completed
9. Mac: Summary displayed

## Network Diagram

```
Home Network (192.168.1.0/24)
│
├─ Mac (192.168.1.50)
│  └─ Conductor
│     └─ Sends MCP commands →
│
├─ Windows PC (192.168.1.100)
│  └─ Playwright MCP Server :8931
│     └─ Controls Edge Browser
│        └─ claude.ai/code
│
└─ Router (192.168.1.1)
   └─ Firewall Rules
```

## FAQ

**Q: Can I use this setup over the internet?**
A: Technically yes with port forwarding or VPN, but not recommended due to security risks. Use SSH tunneling or VPN (Tailscale) instead.

**Q: Does this work with other browsers?**
A: Yes! Change `--browser` to: `chromium`, `firefox`, `webkit`, `chrome`, `chrome-beta`, `msedge`, `msedge-beta`, `msedge-dev`

**Q: Can multiple Macs connect to one Windows server?**
A: Yes, but each would need to manage its own browser instance. MCP server supports multiple connections.

**Q: What about latency?**
A: Local network: <5ms is ideal. VPN: <50ms acceptable. Over 100ms may cause timeouts.

**Q: Can I reverse it (Windows running Conductor, Mac running browser)?**
A: Yes! Same setup, just swap which machine runs what. Note: Conductor runs best on Unix-like systems.

## Monitoring

### Check MCP Server Status

Windows PowerShell:
```powershell
# Check if server is running
Get-NetTCPConnection -LocalPort 8931

# Monitor traffic
netstat -an 1 | findstr 8931
```

### Check Conductor Connection

Mac Terminal:
```bash
# Test MCP endpoint
curl -v http://192.168.1.100:8931

# Monitor Conductor logs
conductor run tasks.yaml --debug
```

## Summary

Your setup command:
```bash
npx @playwright/mcp@latest --port 8931 --host 0.0.0.0 --allowed-hosts * --browser msedge
```

Conductor config:
```yaml
mcp:
  server_url: "http://192.168.1.100:8931/sse"  # Your Windows PC IP
```

This gives you:
- ✅ Mac running Conductor orchestration
- ✅ Windows running Edge browser
- ✅ Full remote browser control
- ✅ Network-based MCP communication

**Pro Tip**: Create a script to start the MCP server automatically on Windows startup if you use this setup frequently!

---

**Need Help?** Check the troubleshooting section or review MCP server logs for connection issues.
