# Create PR Button Element Discovery
## Claude Code Interface Analysis

Based on observations from Claude Code sessions, here's what we know about the Create PR button:

## Button Location
The "Create PR" button appears in the session interface after a task has been completed. It's located in the branch management section of the UI.

## Visual Characteristics
- **Text**: "Create PR"
- **State**: Initially disabled, becomes enabled when changes are ready
- **Position**: Right side of the branch information panel
- **Icon**: Usually accompanied by a git/PR icon

## DOM Structure (Observed)
From our earlier snapshot, the button appeared as:
```
button "Create PR" [disabled]:
  text: Create PR
  generic:
    img
```

When enabled, the structure changes to:
```
button "Create PR" [ref=eXXXX] [cursor=pointer]:
  text: Create PR
  generic:
    img
```

## MCP Element Selection Strategy

### Primary Strategy: Role + Name
```javascript
await page.getByRole('button', { name: 'Create PR' })
```

### Fallback Strategy: Text Content
```javascript
await page.getByText('Create PR')
```

### Alternative Strategy: CSS Selector
```javascript
// Look for button containing "Create PR" text
await page.locator('button:has-text("Create PR")')
```

## Detection Logic for Automation

### 1. Check if PR button exists and is enabled
```python
async def is_pr_button_ready(mcp_client):
    """Check if Create PR button is available and enabled"""
    snapshot = await mcp_client.call_tool("browser_snapshot", {})

    # Parse snapshot for button state
    # Look for: button "Create PR" without [disabled] attribute
    button_pattern = r'button "Create PR"(?!\s*\[disabled\])'

    return bool(re.search(button_pattern, snapshot))
```

### 2. Wait for button to become enabled
```python
async def wait_for_pr_button(mcp_client, timeout=300):
    """Wait for Create PR button to become clickable"""
    start_time = time.time()

    while time.time() - start_time < timeout:
        if await is_pr_button_ready(mcp_client):
            return True
        await asyncio.sleep(5)  # Check every 5 seconds

    return False
```

### 3. Click the button
```python
async def click_create_pr(mcp_client):
    """Click the Create PR button"""
    # Try primary strategy
    try:
        await mcp_client.call_tool("browser_click", {
            "element": "Create PR button",
            "ref": await find_pr_button_ref(mcp_client)
        })
        return True
    except:
        # Fallback to text-based click
        await mcp_client.call_tool("browser_click", {
            "element": "Create PR button",
            "text": "Create PR"
        })
        return True
```

## Branch Information Panel
Adjacent to the Create PR button, we typically see:
- Branch name: `claude/[task-description]-[session-id]`
- Commit statistics: Lines added/removed
- Session ID reference

## HITL Discovery Process

When the element can't be found automatically:

1. **Capture Screenshot**: Take browser screenshot
2. **Display in TUI**: Show ASCII art version
3. **User Guidance**: Ask user to identify button position
4. **Record Selector**: Store the successful selector for future use
5. **Retry Logic**: Use stored selector on next attempt

## Session States Where Button Appears

The "Create PR" button typically appears when:
1. ✅ Task execution is complete
2. ✅ Changes have been committed to the branch
3. ✅ No errors in the execution
4. ✅ Branch has diverged from main/master

## Known Variations

Different button states we might encounter:
- **Disabled**: `button "Create PR" [disabled]`
- **Enabled**: `button "Create PR" [cursor=pointer]`
- **Loading**: Button might show loading spinner
- **Success**: After PR creation, might change to "Open PR" or show PR number

## Robust Detection Algorithm

```python
class PRButtonDetector:
    def __init__(self):
        self.known_refs = []  # Store successful refs
        self.selectors = [
            {"role": "button", "name": "Create PR"},
            {"text": "Create PR"},
            {"selector": 'button:has-text("Create PR")'},
        ]

    async def find_button(self, mcp_client):
        """Find Create PR button using multiple strategies"""
        # Try known refs first
        for ref in self.known_refs:
            if await self.check_ref_exists(mcp_client, ref):
                return ref

        # Try detection strategies
        snapshot = await mcp_client.call_tool("browser_snapshot", {})

        # Parse snapshot for button ref
        match = re.search(r'button "Create PR".*?\[ref=(e\d+)\]', snapshot)
        if match:
            ref = match.group(1)
            self.known_refs.append(ref)
            return ref

        # Fallback to HITL
        return await self.hitl_discovery(mcp_client)
```

## Testing the Button

To verify the button detection works:
1. Navigate to a completed Claude Code session
2. Run the detection algorithm
3. Verify button click triggers PR creation flow
4. Monitor for the PR URL in the response

## Notes for Implementation

- The button ref changes between sessions (dynamic IDs)
- Button might not appear immediately after task completion
- Some delay (5-10s) might be needed for button to become active
- Consider implementing a "manual mode" where user can trigger PR creation

---

**Last Updated**: November 2024
**Status**: Based on observed behavior, needs live testing for confirmation