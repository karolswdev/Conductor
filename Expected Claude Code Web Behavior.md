# Expected Claude Code Web Behavior

**Status:** ✅ **VERIFIED** - Actual behavior documented through testing

**Last Updated:** November 12, 2024

---

## Overview

This document contains the **verified behavior** of Claude Code's web interface at `claude.ai/code`, discovered through hands-on testing with Playwright MCP tools. The implementation team should use this as the definitive guide for updating the Conductor automation.

## Critical Implementation Notes

⚠️ **IMPORTANT**:
- Tasks can run for **tens of minutes** - respect timeout parameters in task definitions
- The Playwright MCP tools work with **accessibility snapshots**, NOT CSS selectors
- Element references (refs) are **dynamic** and change between page loads
- Claude Code is in "Research preview" - UI may change

---

## Verified Behavior

### Phase 1: Initial Page Load ✅

**URL:** `https://claude.ai/code`

**Verified Elements:**
1. **Message Input**
   - Type: `textbox`
   - Name/Placeholder: `"Find a small todo in the codebase and do it"`
   - Dynamic ref (e.g., `e226`, `e1018`, etc.)
   - Located in main content area

2. **Repository Selector**
   - Type: `button`
   - Initial text: `"Select repository"`
   - After selection: Shows full repo path (e.g., `"karolswdev/Conductor"`)
   - Dynamic ref changes each load

3. **Submit Button**
   - Type: `button`
   - Name: `"Submit"`
   - State: **Disabled** when input is empty
   - State: **Enabled** when text is entered
   - Dynamic ref

4. **Model Selector**
   - Type: `button`
   - Default: `"Sonnet 4.5"`
   - Located next to submit button

### Phase 2: Repository Selection ✅

**Interaction Flow:**
1. Click button with text `"Select repository"`
2. Dropdown menu opens with `menu` role
3. Repository list contains:
   - Type: `menuitem` elements
   - Format: `"repository-name owner"`
   - Example: `"Conductor karolswdev"`
4. Click desired repository menuitem
5. Button updates to show selected repository

**Implementation Code:**
```python
# Step 1: Take snapshot
snapshot = await browser.client.call_tool("browser_snapshot", {})

# Step 2: Find and click repository selector button
# Look for button with "Select repository" or current repo name

# Step 3: Wait for dropdown
await asyncio.sleep(1.0)

# Step 4: Take new snapshot for dropdown items
snapshot = await browser.client.call_tool("browser_snapshot", {})

# Step 5: Find and click repository in list
# Format: "Conductor karolswdev" for karolswdev/Conductor
```

### Phase 3: Session Creation ✅

**Verified Process:**
1. Enter text in message input
2. Submit button becomes enabled
3. Click Submit button
4. URL changes immediately to session URL

**URL Pattern:**
- Format: `https://claude.ai/code/session_<alphanumeric_id>`
- Example: `https://claude.ai/code/session_011CV4beKrFjCAcPw3r7tC3u`
- Session ID: 28 character alphanumeric string

**Notifications:**
- A notification dialog may appear asking to enable notifications
- Has "Not Now", "Enable", and "Don't ask me again" buttons
- Can be dismissed with "Not Now"

### Phase 4: Task Execution ✅

**Processing Indicators (in order):**
1. `"Fetch..▌"`
2. `"Loading..."`
3. `"Combobulating..."`
4. `"Deciphering..."`
5. `"Thinking..."`
6. Various command executions visible

**During Execution:**
- Shows TODO list with task progress
- Displays commands being run (Bash, Read, etc.)
- Branch name appears: `claude/<description>-<session_id>`
- "Create PR" button visible but **disabled**
- Can take **tens of minutes** for complex tasks

**Important Timing Considerations:**
```python
# Respect task-specific timeouts
timeout = task.timeout or 600  # Default 10 minutes
check_interval = 10.0  # Check every 10 seconds

# Long-running tasks may show:
# - Multiple processing states
# - Extensive command output
# - Progress through TODO items
```

### Phase 5: Completion Detection ✅

**Completion Indicators:**
1. **"Create PR" button becomes enabled** (primary indicator)
2. Branch name fully visible
3. Processing animations stop
4. Final message appears in chat

**Branch Name Format:**
- Pattern: `claude/<task-description>-<session_id>`
- Example: `claude/test-conductor-automation-011CV4beKrFjCAcPw3r7tC3u`
- Visible in UI during and after execution

**Recommended Detection Logic:**
```python
async def is_task_complete(browser):
    snapshot = await browser.client.call_tool("browser_snapshot", {})

    # Look for Create PR button that's NOT disabled
    # In snapshot, disabled buttons have [disabled] attribute

    # Also check for branch name presence
    # Format: claude/*

    return has_enabled_create_pr_button(snapshot)
```

### Phase 6: Multi-Tab Behavior ✅

**Verified Capabilities:**
- Multiple tabs work independently
- Each tab maintains its own session
- Tab indices remain stable during execution
- Sessions persist when switching tabs

**Tab Management:**
```python
# Create new tab
await browser.client.call_tool("browser_tabs", {"action": "new"})

# List tabs
await browser.client.call_tool("browser_tabs", {"action": "list"})

# Switch to tab
await browser.client.call_tool("browser_tabs", {"action": "select", "index": tab_index})
```

---

## Implementation Fixes Required

### Fix 1: Browser Controller (src/conductor/mcp/browser.py)

The current implementation incorrectly passes selectors as refs. Here's the correct approach:

```python
class BrowserController:
    async def click(self, element_description: str) -> None:
        """Click an element using accessibility snapshot."""
        # Get snapshot first
        result = await self.client.call_tool("browser_snapshot", {})

        # Parse snapshot to find element
        element_ref = self._find_element_in_snapshot(result, element_description)

        if not element_ref:
            raise MCPError(f"Element not found: {element_description}")

        # Click with proper parameters
        await self.client.call_tool(
            "browser_click",
            {
                "element": element_description,  # Human-readable description
                "ref": element_ref,              # Actual ref from snapshot
            },
        )

    async def fill(self, element_description: str, text: str) -> None:
        """Fill text in an element."""
        result = await self.client.call_tool("browser_snapshot", {})
        element_ref = self._find_element_in_snapshot(result, element_description)

        if not element_ref:
            raise MCPError(f"Element not found: {element_description}")

        await self.client.call_tool(
            "browser_type",
            {
                "element": element_description,
                "ref": element_ref,
                "text": text,
                "submit": False,  # Don't auto-submit
            },
        )

    def _find_element_in_snapshot(self, snapshot, description):
        """Parse accessibility snapshot to find element ref."""
        # This needs to parse the YAML-like structure
        # and find elements matching the description
        # Return the ref value (e.g., "e226")
        pass
```

### Fix 2: Task Execution (src/conductor/orchestrator.py, lines 171-379)

Replace guessed selectors with proper snapshot-based interactions:

```python
async def _execute_task(self, task: Task) -> None:
    """Execute a single task in its own browser tab."""
    task.start()
    tab_index = None

    try:
        # Create and switch to new tab
        tab_index = await self.browser.create_tab()
        await self.browser.switch_tab(tab_index)

        # Navigate to Claude Code
        await self.browser.navigate("https://claude.ai/code")
        await asyncio.sleep(3.0)

        # Select repository
        await self._select_repository(task.repository)

        # Submit prompt
        await self._submit_prompt(task.prompt)

        # Wait for session URL
        await asyncio.sleep(3.0)
        current_url = await self.browser.get_current_url()
        session_id = self._extract_session_id_from_url(current_url)

        # Monitor for completion (respect task timeout)
        timeout = task.timeout or 600  # Default 10 minutes
        await self._wait_for_task_completion(task, tab_index, timeout)

        # Extract branch name
        branch_name = await self._extract_branch_name()

        # Record session
        self.session_manager.add_session(
            session_id=session_id,
            task_id=task.id,
            branch_name=branch_name,
            url=current_url,
        )

        task.complete(session_id=session_id, branch_name=branch_name)

    except Exception as e:
        logger.error(f"Task {task.id} failed: {e}")
        task.fail(str(e))
        raise

async def _select_repository(self, repository: str) -> None:
    """Select repository from dropdown."""
    # Take snapshot
    snapshot = await self.browser.client.call_tool("browser_snapshot", {})

    # Click repository selector button
    # Look for "Select repository" or current repo name
    await self.browser.click("Repository selector button")
    await asyncio.sleep(2.0)

    # Select from dropdown
    repo_name = repository.split('/')[-1]
    owner = repository.split('/')[0]
    # Look for menuitem with format "reponame owner"
    await self.browser.click(f"{repo_name} {owner} repository option")
    await asyncio.sleep(1.0)

async def _submit_prompt(self, prompt: str) -> None:
    """Fill and submit the prompt."""
    # Fill the message input
    await self.browser.fill("Message input textbox", prompt)
    await asyncio.sleep(1.0)

    # Click submit (now enabled)
    await self.browser.click("Submit button")

async def _wait_for_task_completion(self, task: Task, tab_index: int, timeout: int) -> None:
    """Wait for task completion with proper timeout handling."""
    start_time = time.time()
    check_interval = 10.0  # Check every 10 seconds

    logger.info(f"Waiting up to {timeout}s for task {task.id} to complete")

    while time.time() - start_time < timeout:
        try:
            await self.browser.switch_tab(tab_index)

            # Take snapshot
            snapshot = await self.browser.client.call_tool("browser_snapshot", {})

            # Check for enabled "Create PR" button (primary completion indicator)
            if self._is_create_pr_button_enabled(snapshot):
                logger.info(f"Task {task.id} completed - Create PR button enabled")
                return

            # Log progress
            elapsed = int(time.time() - start_time)
            logger.debug(f"Task {task.id} still running ({elapsed}s elapsed)")

            await asyncio.sleep(check_interval)

        except Exception as e:
            logger.debug(f"Error checking completion: {e}")
            await asyncio.sleep(check_interval)

    logger.warning(f"Task {task.id} timed out after {timeout}s")
    logger.info("Task may still be running - check browser tab manually")

def _is_create_pr_button_enabled(self, snapshot) -> bool:
    """Check if Create PR button is enabled in snapshot."""
    # Parse snapshot for button with text "Create PR"
    # Check it doesn't have [disabled] attribute
    # Return True if enabled
    pass

async def _extract_branch_name(self) -> Optional[str]:
    """Extract branch name from current page."""
    snapshot = await self.browser.client.call_tool("browser_snapshot", {})
    # Look for pattern: claude/<description>-<session_id>
    # Return the full branch name
    pass
```

### Fix 3: Parallel Execution (src/conductor/orchestrator_parallel.py)

Same fixes as above, but ensure:
- Proper tab isolation for parallel tasks
- Respect individual task timeouts
- Handle long-running tasks appropriately

### Fix 4: TUI Updates (src/conductor/orchestrator_tui.py)

Update status messages to reflect actual states:
- "Fetch..▌" → Starting
- "Loading..." → Loading
- "Combobulating..." → Processing
- "Thinking..." → Analyzing
- "Create PR" enabled → Complete

---

## Testing Checklist

- [ ] Single task execution with 5-minute timeout
- [ ] Long-running task with 30+ minute timeout
- [ ] Repository selection for different repos
- [ ] Multi-tab parallel execution (3+ tasks)
- [ ] Notification dialog handling
- [ ] Session ID extraction from URL
- [ ] Branch name extraction
- [ ] Completion detection accuracy
- [ ] Error handling for timeouts
- [ ] Tab switching during execution

---

## Notes for Implementation Team

1. **Snapshot Parsing**: You'll need robust YAML parsing for the accessibility snapshots
2. **Dynamic Refs**: Never hardcode refs - always get fresh from snapshots
3. **Timing**: Add configurable delays between actions for stability
4. **Logging**: Add detailed logging for debugging long-running tasks
5. **Error Recovery**: Handle transient failures with retries
6. **UI Changes**: Claude Code is in preview - add flexibility for UI updates

---

## Support

For questions about this document or the implementation:
- Check the example test script in `/test_mcp_connection.py`
- Review Playwright MCP documentation
- Test with `conductor doctor` mode for debugging

**Remember**: The key difference is that Playwright MCP uses accessibility snapshots, not DOM selectors!