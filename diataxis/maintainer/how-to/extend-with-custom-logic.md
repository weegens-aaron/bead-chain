# How-to: Extend bead-chain with custom logic

## How to extend bead-chain with custom logic

**When to use this:** You need bead-chain to behave differently — custom selection logic, alternate close conditions, project-specific hooks, etc. This recipe shows how to add new behavior without breaking the core chain.

---

## Architecture: Where extensions live

bead-chain's module structure is deliberately loosely coupled. Most extension points live in:

```
bead_chain/
├── lifecycle.py          ← pick/claim/close logic
├── register_callbacks.py ← hook registration + CLI flags
├── prompt.py             ← goal prompt formatting
└── beads.py              ← bd CLI wrapper
```

**Key design:** Modules communicate via `state.py` (a singleton dataclass) and simple function contracts. No global state, no circular imports, no magic. Easy to test.

---

## Pattern 1: Add a new selection rule (tie-breaker)

**Goal:** After bead-chain's normal waterfall (blocking bugs → epic affinity → global queue), inject your own rule.

**Location:** `lifecycle.py::pick_next_bead()`

**Recipe:**

1. **Read the current logic** (around line 150):
   ```python
   def pick_next_bead():
       # 1. Blocking bug?
       # 2. Epic sibling?
       # 3. Global ready?
   ```

2. **Add your rule after epic affinity, before global fallback:**
   ```python
   # In pick_next_bead(), after epic sibling check:
   
   # YOUR RULE: \"p0 bugs jump the queue\"
   p0_ready = beads.next_ready()  # get the top ready bead
   if p0_ready and p0_ready.get(\"priority\") == 1:
       return p0_ready  # return P0 bugs immediately
   ```

3. **Test it:**
   ```python
   # Create a P1 bug, then a normal task
   bd create --type=bug --priority=1 --title=\"Critical: X broken\"
   bd create --type=task --priority=2 --title=\"Normal task\"
   
   /bead-chain --max=1
   # Should pick the P1 bug, not the task
   ```

---

## Pattern 2: Add a pre-claim validation hook

**Goal:** Before claiming a bead, validate something (e.g., \"only claim if branch is clean\").

**Location:** `register_callbacks.py` + `lifecycle.py`

**Recipe:**

1. **Create a validation function** in `lifecycle.py`:
   ```python
   def validate_git_clean(bead_id: str) -> bool:
       \"\"\"Return True if git working directory is clean.\"\"\"
       result = subprocess.run(
           [\"git\", \"status\", \"--porcelain\"],
           capture_output=True,
           text=True
       )
       return result.stdout.strip() == \"\"
   ```

2. **Call it in `claim_next()`** before `beads.claim()`:
   ```python
   def claim_next(bead: dict) -> None:
       if not validate_git_clean(bead[\"id\"]):
           raise RuntimeError(\"Git has uncommitted changes. Commit first.\")
       beads.claim(bead[\"id\"])
   ```

3. **Test it:**
   ```bash
   echo \"test\" > /tmp/test.txt
   /bead-chain  # Should refuse to claim until git is clean
   ```

---

## Pattern 3: Inject a custom prompt preamble

**Goal:** Add context to every `/goal` invocation (e.g., \"remember, this is a P0 bug\").

**Location:** `prompt.py::format_goal_prompt()`

**Recipe:**

1. **Read the prompt builder** (around line 80):
   ```python
   def format_goal_prompt(bead: dict, ...) -> str:
       # builds the full prompt for /goal
   ```

2. **Add your context:**
   ```python
   # Add before the main bead description:
   
   priority = bead.get(\"priority\", 2)
   if priority == 1:
       custom_preamble = \"\
⚠️ **P1 BUG** — fix this ASAP, others depend on it.\
\"
   else:
       custom_preamble = \"\"
   
   return custom_preamble + original_prompt
   ```

3. **Test it:**
   ```bash
   bd create --type=bug --priority=1 --title=\"Test P1\"
   /bead-chain --max=1
   # You should see the P1 warning in the /goal preamble
   ```

---

## Pattern 4: Add a post-close hook

**Goal:** Run custom logic after a bead closes (e.g., \"post a Slack message\").

**Location:** `register_callbacks.py`

**Recipe:**

1. **Create a hook function** anywhere (e.g., `bead_chain/slack_notify.py`):
   ```python
   def notify_close(bead_id: str, title: str) -> None:
       \"\"\"Post to Slack that a bead closed.\"\"\"
       url = os.getenv(\"SLACK_WEBHOOK\")
       if not url:
           return  # Skip if not configured
       
       payload = {\"text\": f\"✓ Bead closed: {title} ({bead_id})\"}
       requests.post(url, json=payload)
   ```

2. **Register it in wiggum's lifecycle**:
   - Wire your hook into the `/goal` completion handler (this is outside bead-chain's scope, but the pattern applies)
   - bead-chain calls `beads.close()` after the LLM judges pass; you hook that point

3. **Test it:**
   ```bash
   export SLACK_WEBHOOK=https://hooks.slack.com/...
   /bead-chain --max=1
   # You should see a Slack message when the bead closes
   ```

---

## Testing your extensions

Add a unit test for your new logic:

```python
# In tests/test_custom_rule.py

def test_my_new_selection_rule():
    \"\"\"Verify my custom tie-breaker works.\"\"\"
    # Create test beads with fixtures
    # Call the modified pick_next_bead()
    # Assert it picks the right one
```

Run the test suite before committing:
```bash
python -m pytest tests/ -v
```

---

## Done — verify

Your extension is solid when:
- ✓ All existing tests still pass (`pytest tests/`)
- ✓ Your new logic is tested (add a test file)
- ✓ bead-chain behavior matches your expectation (`/bead-chain --max=1`)
- ✓ No silent failures or crashes (check error handling)

---

## Related

- **Understand the architecture first?** Read [../reference/architecture.md](../reference/architecture.md).
- **See the config options?** Check [../reference/config-env-flags.md](../reference/config-env-flags.md).
- **Want to understand the blocker logic?** See [../reference/blocker-gate-logic.md](../reference/blocker-gate-logic.md).
"