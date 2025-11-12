# Expected Claude Code Web Behavior

**Status:** 🔍 **DISCOVERY PHASE** - Agent needs to work with HITL to map actual behavior

---

## Welcome, Agent! 👋

You're about to help implement browser automation for **Conductor**, a task orchestration system for Claude Code on the web. This document will get you up to speed and explain what needs to be discovered.

## What is Conductor?

Conductor is an automation system that:
- Manages multiple GitHub issues/tasks in parallel
- Opens browser tabs for each task
- Submits prompts to Claude Code web interface
- Monitors task completion
- Tracks session IDs and git branch names
- Provides TUI dashboard for progress tracking

**Think of it as:** A conductor orchestrating multiple Claude Code sessions simultaneously, each working on different GitHub issues.

## Project Structure

```
Conductor/
├── src/conductor/
│   ├── mcp/                  # MCP client and browser controller
│   ├── browser/              # Authentication and session management
│   ├── orchestrator*.py      # Task execution engines (3 variants)
│   └── tasks/                # Task models and validation
├── todo/                     # 📌 LOOK HERE for example task files
└── docs/                     # Documentation
```

### Key Files You Should Read

1. **`todo/*.yaml`** - Example task definitions to understand what we're automating
2. **`src/conductor/orchestrator.py`** - Main task execution logic (lines 171-379)
3. **`src/conductor/mcp/browser.py`** - Browser control methods (currently uses guessed selectors!)
4. **`README.md`** - Overall project documentation

## The Problem: We're Guessing! 🤷

The current implementation **makes assumptions** about the Claude Code web UI:

```python
# ⚠️ THESE ARE GUESSES - NOT VERIFIED!
await browser.click("[data-testid='new-session-button']")  # Does this exist?
await browser.fill("textarea[placeholder*='message']", prompt)  # Is this right?
await browser.click("button[type='submit']")  # How do we actually submit?
```

**Your mission:** Work with the human to discover the ACTUAL behavior and update the code accordingly.

---

## What Needs to Be Discovered

### Phase 1: Initial Page Load
**URL:** `https://claude.ai/code`

**Questions to answer:**
1. What does the page look like when you first land?
2. Are you immediately in a session, or do you need to create one?
3. What elements are visible? (Take screenshots, inspect DOM)
4. Is there a repository selector visible?

**Action:** Have the human navigate to `claude.ai/code` in the browser (via `conductor doctor` or manually) and describe what they see.

### Phase 2: Repository Selection
**Expected behavior (UNVERIFIED):**
- There should be a dropdown or selector to choose which GitHub repository to work with
- Tasks specify a repository like `"repository": "karolswdev/Conductor"`

**Questions to answer:**
1. Where is the repository selector located?
2. What HTML element is it? (select, div with role="combobox", custom component?)
3. How do you click and select a repository?
4. What selectors can we use to target it?
   - CSS selector? (e.g., `select[name="repository"]`)
   - data-testid? (e.g., `[data-testid="repo-selector"]`)
   - ARIA label? (e.g., `[aria-label="Select repository"]`)

**Discovery steps:**
```python
# Use browser snapshot to see page structure
snapshot = await browser.client.call_tool("browser_snapshot", {})

# Or have human inspect element in browser DevTools
# Then update BrowserController with correct selectors
```

### Phase 3: Creating a New Session
**Current assumption:** Click a "new session" button

**Questions to answer:**
1. How do you start a new session?
   - Is there a button? What does it say? ("New Session", "Start Chat", "+", etc.)
   - Do sessions auto-create when you type?
   - Is there a different flow for authenticated vs unauthenticated users?

2. What happens after clicking?
   - Does URL change? (e.g., `/code/<session-id>`)
   - Does a new panel/modal appear?
   - How long does it take to initialize?

3. Session ID extraction:
   - Where is the session ID visible?
   - Is it in the URL? (Current assumption: `https://claude.ai/code/<session-id>`)
   - Is it in a DOM element we can query?

**Discovery steps:**
```python
# Before clicking
url_before = await browser.get_current_url()
print(f"URL before: {url_before}")

# Try to find and click new session button
# (Human should describe what they see)
await browser.click("???")  # What selector?

# After clicking
await asyncio.sleep(2)
url_after = await browser.get_current_url()
print(f"URL after: {url_after}")
```

### Phase 4: Submitting a Task Prompt
**Current assumption:** Fill a textarea and click submit

**Questions to answer:**
1. Where do you type the prompt?
   - Is it a textarea, contenteditable div, or something else?
   - What selectors work? (placeholder text, aria-labels, classes)
   - Example: `textarea[placeholder="Message Claude"]` or `[role="textbox"]`

2. How do you submit?
   - Is there a submit button?
   - Do you use Cmd/Ctrl+Enter?
   - Does it auto-submit on some trigger?

3. What happens after submission?
   - Does the input clear?
   - Does a loading indicator appear?
   - How do you know Claude received the prompt?

**Discovery steps:**
```python
# Find the input element
page_snapshot = await browser.get_text("body")
print("Looking for input element...")

# Try different selectors
selectors_to_try = [
    "textarea",
    "[contenteditable='true']",
    "[role='textbox']",
    "textarea[placeholder*='message']",
    "textarea[placeholder*='Message']",
]

for selector in selectors_to_try:
    try:
        # Human should verify if this selector works
        await browser.fill(selector, "Test prompt")
        print(f"✓ Found input with selector: {selector}")
        break
    except Exception as e:
        print(f"✗ Failed: {selector}")
```

### Phase 5: Monitoring Execution
**Current assumption:** Poll page text for keywords like "completed", "done", "push"

**Questions to answer:**
1. How do you know Claude is working?
   - Progress indicators?
   - Status messages?
   - Specific DOM elements that change?

2. How do you know Claude is done?
   - Does it show a "Task completed" message?
   - Does it display git push information?
   - Are there specific phrases we can reliably detect?

3. Branch name extraction:
   - Where does Claude display the branch name?
   - Format: `claude/<branch-name>` or something else?
   - Is it in the UI, or do we need to parse it from messages?

4. Error detection:
   - How do you know if Claude hit an error?
   - What error messages appear?
   - Should we retry or mark task as failed?

**Discovery steps:**
```python
# Monitor page changes over time
check_interval = 5.0  # seconds

while True:
    snapshot = await browser.get_text("body")

    # Human should tell us what keywords indicate completion
    # Examples: "Committed", "Pushed to branch", "Session complete"

    # Also look for branch names
    # Pattern: claude/<some-name>

    await asyncio.sleep(check_interval)
```

### Phase 6: Multi-Tab Behavior
**Current assumption:** Each task runs in its own tab

**Questions to answer:**
1. Do multiple tabs work independently?
   - Can you have 3 tabs all running different Claude sessions?
   - Do they interfere with each other?

2. Tab switching behavior:
   - How does `browser_tabs` with action "select" work?
   - Do tab indices stay stable?
   - What happens if you switch tabs while Claude is working?

3. Session persistence:
   - If you leave a tab and come back, is the session still active?
   - Can you resume monitoring a task after switching tabs?

---

## How to Work With HITL (Human-In-The-Loop)

### Step 1: Run Doctor Mode
```bash
cd /home/user/Conductor
conductor doctor
```

This will:
- Launch browser
- Navigate to `claude.ai/code`
- Human can inspect the page
- Take screenshots with `browser_take_screenshot`

### Step 2: Interactive Discovery
Use the browser controller to explore:

```python
# In a Python script or REPL
from conductor.mcp.browser import BrowserController
from conductor.mcp.client import MCPClient

# Connect
client = MCPClient("http://localhost:8931/sse")
await client.connect()
browser = BrowserController(client)

# Launch and navigate
await browser.navigate("https://claude.ai/code")

# Ask human: "What do you see? Describe the page elements."
# Then take a snapshot
snapshot = await browser.get_text("body")
print(snapshot)

# Try different interactions based on human feedback
```

### Step 3: Update Code Incrementally
As you discover each element:

1. **Update `src/conductor/mcp/browser.py`** with correct selectors
2. **Add helper methods** for specific actions (e.g., `select_repository()`, `submit_prompt()`)
3. **Update orchestrators** (`orchestrator.py`, `orchestrator_parallel.py`, `orchestrator_tui.py`)
4. **Test with a single task** before running multiple
5. **Commit changes** with descriptive messages

### Step 4: Document Findings
Update this file with your discoveries:
- Add actual selectors under each section
- Include screenshots in `docs/screenshots/`
- Note any quirks or timing issues
- Update the orchestrator code comments

---

## Example Task to Test With

Look at **`todo/conductor-tasks.yaml`** for example tasks. Here's a simple one to test:

```yaml
tasks:
  - id: "TEST-001"
    name: "Add README badge"
    prompt: "Add a status badge to the README showing build status"
    repository: "karolswdev/Conductor"
    expected_deliverable: "Updated README.md with badge"
```

**Test plan:**
1. Run Conductor with this single task
2. Observe the browser behavior
3. Note down each step Claude Code takes
4. Update the automation code to match reality

---

## Success Criteria

You'll know you've succeeded when:

✅ Conductor can automatically:
1. Open `claude.ai/code`
2. Select the correct repository from dropdown
3. Create a new session
4. Submit the task prompt
5. Monitor execution progress
6. Detect when Claude finishes
7. Extract session ID and branch name
8. Handle multiple tasks in parallel (different tabs)

✅ Code has **no guessed selectors** - everything is verified
✅ Error handling for common failures (timeouts, wrong repo, etc.)
✅ Logging shows clear progress for debugging

---

## Current Placeholder Code Locations

**Files that need updates:**

1. **`src/conductor/orchestrator.py:171-379`**
   - Lines 207: `click("[data-testid='new-session-button']")` ← Probably wrong
   - Lines 225: `fill("textarea[placeholder*='message']", ...)` ← Probably wrong
   - Lines 230: `click("button[type='submit']")` ← Probably wrong
   - Lines 359-364: Completion detection logic ← Needs real keywords

2. **`src/conductor/orchestrator_parallel.py:333-556`**
   - Same issues as above, duplicated code

3. **`src/conductor/orchestrator_tui.py:235-442`**
   - Same issues as above, duplicated code

**Your job:** Replace the `???` placeholders with actual, verified selectors.

---

## Questions to Ask the Human

Start with these:

1. "I've opened claude.ai/code in the browser. Can you describe what you see on the page?"

2. "Is there a repository selector visible? If so, can you inspect it in DevTools and tell me:
   - The HTML tag (select, div, button, etc.)
   - Any data-testid attributes
   - The ARIA label or role
   - How to programmatically select a repository"

3. "How do you create a new session? Is there a button, and what does it look like?"

4. "Where do you type your prompt? Can you inspect that element and share:
   - The selector that uniquely identifies it
   - Its placeholder text
   - Whether it's a textarea or contenteditable div"

5. "How do you submit the prompt? Button click or keyboard shortcut?"

6. "When Claude is working, what do you see? Are there progress indicators or status messages?"

7. "When Claude finishes, what appears on screen? Any specific text we can search for?"

8. "Where is the git branch name displayed?"

---

## Next Steps

1. **Read the example tasks** in `todo/` directory
2. **Run `conductor doctor`** to launch the browser
3. **Ask the human** the questions above
4. **Take screenshots** at each step for documentation
5. **Update the code** with real selectors and behavior
6. **Test with one task** end-to-end
7. **Commit and document** your findings

---

## Notes & Caveats

- Claude Code UI may change over time (update this doc when it does)
- Timing is important (page loads, session initialization, etc.)
- The Playwright MCP returns **accessibility tree snapshots**, not full DOM
  - Some elements may not be easily accessible
  - You might need to use `browser_evaluate` to run JavaScript
- Authentication happens ONCE at the start (already implemented correctly)
- Repository selection might be per-session or global - TBD

---

**Remember:** The current code is based on **assumptions**. Your job is to replace assumptions with **verified reality** through HITL discovery. Good luck! 🎭
