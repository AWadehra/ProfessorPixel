# Contract Negotiator — Improvement Action Items

> Generated 2026-03-17 from a full 4-team audit (agents, performance, frontend, security)

---

## CRITICAL — Fix Before Demo/Deploy

### C1. Template Variable Dict-Repr Injection
**Files:** `buyer_lawyer.py`, `seller_lawyer.py`, `mediator.py`, `redliner.py`, `debate_tracker.py`
**Issue:** When `output_schema` produces structured JSON, ADK stores the result as a Python dict. Template variables like `{clauses}`, `{buyer_analysis}` call `str()` on these dicts, injecting Python repr (single quotes, `True`/`False`, `None`) instead of valid JSON. Every downstream agent receives mangled data.
**Fix:** Switch from string templates to `InstructionProvider` callables that serialize state with `json.dumps()`:
```python
import json
def buyer_instruction(ctx):
    clauses = ctx.state.get("clauses", {})
    return f"...Contract clauses: {json.dumps(clauses, indent=2)}"
```
Apply to all 6 agents that read state via templates.

### C2. XSS in Heatmap and Redline Rendering
**Files:** `app.js` lines 613–638 (heatmap), lines 492–507 (redline)
**Issue:** `clause.title`, `clause.text`, `clause.original_text`, `clause.revised_text`, `bRisk.concern`, `sRisk.concern` are injected into `innerHTML` without escaping. A contract containing `<script>` tags or event handler attributes in its text could execute in the browser.
**Fix:** Add an `esc()` helper that replaces `<>&"'` with HTML entities. Apply to every AI-generated string before DOM insertion.

### C3. Hardcoded Credential Fallbacks in All Tool Files
**Files:** `dlp_tools.py:14`, `translate_tools.py:14`, `firestore_tools.py:15`, `sheets_tools.py:15`, `document_tools.py:17-20`
**Issue:** All use `os.environ.get("KEY", "hardcoded-project-id")`. If `.env` is missing at runtime, code silently uses committed secrets.
**Fix:** Replace with `os.environ["KEY"]` (raises `KeyError` on startup if missing). Remove all hardcoded fallback values.

### C4. Rate Limiting Silently Broken
**File:** `server.py` lines 498–500
**Issue:** `limiter.limit(...)` is applied by reassigning function references AFTER FastAPI has registered the routes. This does not actually attach rate limits. Additionally, `slowapi` import failure silently disables all protection.
**Fix:** Apply `@limiter.limit(...)` as decorators directly on the route functions. Make `slowapi` a hard import (crash on startup if missing).

### C5. Missing Dependencies in pyproject.toml
**File:** `pyproject.toml`
**Issue:** Six runtime dependencies are missing: `google-cloud-dlp`, `google-cloud-firestore`, `google-cloud-translate`, `google-api-python-client`, `google-auth`, `google-cloud-logging`. `pip install -e .` in a fresh env will fail at import time.
**Fix:** Add all six to the dependencies list.

---

## HIGH — Fix Before Production

### H1. No Authentication on Session/History Endpoints
**Files:** `server.py` — `/api/session/*/save`, `/api/session/*/export-sheets`, `/api/history`
**Issue:** Anyone who knows a session UUID can save, export, or read any analysis. `/api/history` leaks all past analyses with executive summaries and party names.
**Fix:** Return a signed session token in the SSE `done` event; require it on session-scoped endpoints. Remove or admin-protect `/api/history`.

### H2. No Rate Limits on Expensive New Endpoints
**Files:** `server.py` — `/api/detect-language`, `/api/scan-pii`, `/api/session/*/export-sheets`
**Issue:** These endpoints make GCP API calls with no rate limiting. An attacker can run up Cloud Translation, DLP, and Sheets API costs.
**Fix:** Apply rate limits: detect-language `20/minute`, scan-pii `10/minute`, export-sheets `3/minute`.

### H3. `#redline` Panel Outside `#v-analysis` in HTML
**File:** `index.html` lines 143–151
**Issue:** The `<div id="redline">` is placed after the closing `</div>` of `#v-analysis`. It renders outside the view container, is never hidden by `showView()`, and scrollIntoView targets the wrong position.
**Fix:** Move `<div id="redline">...</div>` inside `#v-analysis`, before its closing `</div>`.

### H4. SSE Retry Doubles Agent Content
**File:** `app.js` — `handleSSEError()` and `run(true)`
**Issue:** On SSE reconnection, `T[author]` still contains partial content from the failed attempt. The retry appends a second full stream on top, causing doubled buyer/seller text.
**Fix:** Clear `T` before calling `run(true)`: `Object.keys(T).forEach(k => delete T[k])` in `handleSSEError`.

### H5. `ttsCache` and `audioQueue` Used Before Declaration
**File:** `app.js` lines 201 vs 751–753
**Issue:** `ttsCache = {}; audioQueue = []` in `run()` references variables declared with `let` at line 751. `let` is not hoisted, causing `ReferenceError` on first call.
**Fix:** Move `let ttsCache = {}`, `let audioQueue = []`, `let ttsPlaying = false` to the top of the file (near line 25).

### H6. Mediator Uses Non-Optional `{debate_history}`
**File:** `mediator.py` line 35
**Issue:** `{debate_history}` without `?` suffix raises `KeyError` if debate loop never stored history (e.g., immediate escalation failure).
**Fix:** Change to `{debate_history?}`.

### H7. `debate_round` Off-By-One in Debate Prompts
**File:** `debate_tracker.py` — DebateTracker runs after rebuttals
**Issue:** `debate_round` is incremented by DebateTracker, which runs AFTER the rebuttal agents. Round 1 rebuttals see no `debate_round`; Round 2 rebuttals see `debate_round=1`.
**Fix:** Either initialize `debate_round=1` in session state before the loop starts, or make DebateTracker the first sub_agent (and restructure so it runs before rebuttals each iteration).

### H8. .gitignore Missing Patterns
**File:** `.gitignore`
**Issue:** Missing patterns for `.env.*`, `*.env.*`, `service-account*.json`, `*-key.json`, `credentials.json`, `.claude/`.
**Fix:** Add all listed patterns.

---

## MEDIUM — Fix Soon

### M1. Heatmap/Redline Not Keyboard-Accessible
**File:** `app.js` — `renderHeatmap()`, `showRedline()`
**Issue:** `hm-clause` and `rl-clause-head` use inline `onclick` with no `tabindex`, `role`, or `aria-expanded`. Keyboard users cannot interact with these features.
**Fix:** Add `tabindex="0"` and `role="button"` to generated elements. Extend the `keydown` delegation to handle `.hm-clause-head` and `.rl-clause-head`.

### M2. Client Disconnection Doesn't Cancel Pipeline
**File:** `server.py` — `event_generator()`
**Issue:** When a client disconnects mid-stream, `runner.run_async()` continues consuming Gemini API tokens until completion.
**Fix:** Handle `asyncio.CancelledError` in `event_generator()` and cancel/break the pipeline.

### M3. `ttsPlaying` Never Reset After Manual Mic Click
**File:** `app.js` — manual mic handler (line 815)
**Issue:** After manual playback, `ttsPlaying` stays `true`. Future auto-TTS silently never plays.
**Fix:** Set `ttsPlaying = false` in the manual playback `onended` callback.

### M4. PII Banner Not Removed on New Analysis
**File:** `app.js` — `run()` reset block (lines 186–202)
**Issue:** If first contract has PII but second doesn't, the old PII banner persists.
**Fix:** Add `$('#pii-banner')?.remove()` and `$('#translate-banner')?.remove()` to the reset block.

### M5. Translation Detection Doesn't Fire for Uploaded Files
**File:** `app.js` — `upload()` success handler
**Issue:** Non-English PDFs uploaded via Document AI bypass translation detection.
**Fix:** Call `detectAndOfferTranslation(r.text)` after setting `el.inp.value`.

### M6. `URL.createObjectURL` Memory Leak in TTS
**File:** `app.js` lines 784, 815
**Issue:** Blob URLs created for audio playback are never revoked. Each analysis session leaks 5+ Blob URLs.
**Fix:** Call `URL.revokeObjectURL(objectUrl)` in `audio.onended`.

### M7. Print CSS Incomplete for New Features
**File:** `print.css`
**Issue:** Missing rules for `.redline-panel` (clips content at 60vh), `#export-sheets` button (visible in print), `.pii-banner` and `.translate-banner` (visible in print), `.hm-detail-inner` (overflow hidden clips content).
**Fix:**
```css
.redline-panel { break-inside:avoid; }
.redline-panel.closed { display:block !important; }
.rl-body { max-height:none !important; overflow:visible !important; }
.rl-detail { display:block !important; grid-template-rows:1fr !important; }
#export-sheets,.pii-banner,.translate-banner { display:none !important; }
.hm-detail-inner { overflow:visible !important; }
```

### M8. DLP Truncation Logic Inconsistent
**File:** `dlp_tools.py` lines 44–46
**Issue:** Checks byte length > 500KB but truncates to 100K characters (which may still exceed 500KB for multi-byte text).
**Fix:** Truncate to `500_000 // 4` characters (~125K) to ensure bytes stay under limit for any encoding.

### M9. Translate/PII Banner Colors Hardcoded for Dark Theme
**Files:** `style.css` lines 225, 232
**Issue:** `.translate-banner` and `.pii-banner` use hardcoded rgba values instead of CSS custom properties. Colors don't adapt to light theme.
**Fix:** Use `var(--blue-s)` for translate banner, compute from `var(--red)` for PII banner.

### M10. Sheets Export Creates Orphan Sheets on Failure
**File:** `sheets_tools.py`
**Issue:** If `batchUpdate` fails after sheet creation, an empty sheet is left in the service account's Drive with no cleanup.
**Fix:** Wrap in try/except and delete the sheet on `batchUpdate` failure.

---

## LOW — Backlog / Polish

### L1. `discCounter` Not Reset Between Analyses
**File:** `app.js` line 312
**Issue:** Counter grows indefinitely across analyses. Harmless but `aria-controls` IDs become stale.

### L2. FIFO Cache Eviction Instead of LRU
**Files:** `document_tools.py` lines 100–102, `tts_tools.py` lines 71–73
**Issue:** Evicts oldest-inserted entry, not least-recently-used. Frequently accessed items get evicted.

### L3. `RedlinedContract.total_changes` Redundant
**File:** `schemas.py` lines 103–104
**Issue:** AI-generated count may not match actual count of `changed=True` clauses. Frontend/server should compute from data.

### L4. Redundant `prefetchTTS()` Calls
**File:** `app.js` lines 341, 346, etc.
**Issue:** `prefetchTTS(a)` is called explicitly then again inside `qTTS(a)`. The first call is dead code.

### L5. TTS Cache Key Collision (500 vs 4000 chars)
**File:** `app.js` lines 762 vs 809
**Issue:** Auto-play caches 500-char TTS; manual mic reuses the cached 500-char version instead of fetching 4000-char version.
**Fix:** Don't use `ttsCache` fallback for manual clicks — always fetch full text.

### L6. 5 Separate ThreadPoolExecutors
**Files:** All tool files
**Issue:** 12 idle OS threads across 5 executors. A single shared executor with 6–8 workers would be cleaner.

### L7. Schema Fields Lack `Literal` Type Constraints
**File:** `schemas.py`
**Issue:** `risk_level`, `priority`, `category`, `contract_type` accept any string. Use `Literal["high","medium","low"]` etc. to enforce at the Pydantic layer.

### L8. Upload Endpoint Lacks MIME Magic Byte Validation
**File:** `server.py` — `/api/upload`
**Issue:** Only checks file extension, not actual content. A renamed `.exe` passes the check.
**Fix:** Check first bytes: `%PDF-` for PDFs, `\x89PNG` for PNG, `\xFF\xD8\xFF` for JPEG.

### L9. Retry Timeout Not Cleared on "New" Button
**File:** `app.js` — `$('#again')` handler
**Issue:** If user clicks "New" during a retry backoff, the pending `setTimeout` still fires and starts a new analysis.
**Fix:** Store timeout ID and `clearTimeout` in the New handler.

### L10. Warm Up GCP Clients at Startup
**File:** `server.py` — `lifespan`
**Issue:** First call to sheets, DLP, and translate endpoints incurs 100–300ms auth/discovery latency.
**Fix:** Eagerly initialize clients in background tasks during the lifespan startup phase.

---

## OPTIMIZATION — Latency Wins

### O1. Reduce Debate Rounds from 3 to 2 (saves 12–25s)
**File:** `debate_tracker.py` line 5
The third debate round adds marginal information. Cutting to 2 rounds removes 2 sequential LLM calls.

### O2. Add Convergence Detection to DebateTracker (saves 6–14s conditionally)
**File:** `debate_tracker.py` — `_run_async_impl`
If both sides make 3+ concessions in a round, escalate early — the debate has converged.

### O3. Reduce Context Passed to Redliner (saves 1–3s)
**File:** `redliner.py`
Pass only `final_report.risk_items` and `final_report.recommendation` instead of the full report object.

### O4. Handle Client Disconnect to Stop Burning Tokens (saves $$$)
**File:** `server.py` — `event_generator()`
Catch `asyncio.CancelledError` to break out of the pipeline when client disconnects.

---

## FEATURE GAPS — Nice to Have

- **Retry timeout management**: Store `setTimeout` ID for SSE retries, clear on navigation
- **Go button disable during analysis**: Prevent double-submit by disabling button until `allDone()` or error
- **Sheets export deduplication**: Track created sheet IDs to update existing sheets instead of creating new ones
- **Firestore document size check**: Validate document size before write (1MB Firestore limit)
- **`target` language validation** in `translate_tools.py`: Allowlist BCP-47 codes before passing to API
