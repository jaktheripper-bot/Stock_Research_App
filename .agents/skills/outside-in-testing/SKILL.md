---
name: outside-in-testing
description: Guidance, testing recipes, and automated verification workflows for outside-in (UI-to-code) contract testing across templates, client scripts, modals, and endpoints.
---

# Outside-In Testing Protocol (UI-to-Code Contracts)

## Overview & Core Philosophy

Testing purely **inside-out** (validating backend analytical functions and asserting HTTP 200) creates a false sense of security. A feature can achieve 100% test pass rates while failing 100% of user interactions due to:
- DOM containment clipping (`overflow: hidden` containers trapping `position: fixed` modals).
- JavaScript runtime `TypeError: Cannot set property of null` when script IDs don't match DOM element IDs.
- Action buttons whose `onclick` attributes call undefined functions or rely on suppressed browser `alert()`.
- Unregistered or mismatched API routes targeted by client-side `fetch()` calls.
- Modals displaying raw user echoes with zero domain intelligence or analytical depth.
- Raw Jinja expressions (`{{ firm.uin }}`) leaking unrendered into HTML attributes.

The **Outside-In Testing Protocol** mandates testing from the **user's sensory experience down to the code**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      OUTSIDE-IN TEST CONTRACT                          │
│                                                                        │
│  1. USER AFFORDANCE & TRIGGER                                          │
│     Can the user see a tactile, non-disabled button with valid labels? │
│     Is the onclick attribute wired to a defined JS handler?            │
│                            │                                           │
│                            ▼                                           │
│  2. INTERACTION & PROGRESS STATE                                       │
│     Does the button immediately show active feedback ("Analyzing...")? │
│     Does it restore gracefully upon completion or failure?             │
│                            │                                           │
│                            ▼                                           │
│  3. DOM ELEMENT BINDING INTEGRITY (Zero Null Errors)                   │
│     Does EVERY document.getElementById('X') queried in JS exist in     │
│     the rendered HTML DOM?                                             │
│                            │                                           │
│                            ▼                                           │
│  4. CLIENT-TO-SERVER ROUTE CONTRACT                                    │
│     Does the fetch() target correspond to an active registered route?   │
│                            │                                           │
│                            ▼                                           │
│  5. VIEWPORT CENTERING & MODAL ARCHITECTURE                            │
│     Does the modal use .modal-backdrop and .modal-dialog at root level?│
│     Is it dismissible via close button, backdrop click, and ESC key?   │
│                            │                                           │
│                            ▼                                           │
│  6. ANALYTICAL DEPTH & VALUE COVENANT                                  │
│     Does the rendered view supply substantive intelligence (ratios,    │
│     benchmarks, moat scores, supply chain links) rather than raw echoes?│
│                            │                                           │
│                            ▼                                           │
│  7. TEMPLATE HYGIENE                                                   │
│     Zero unrendered Jinja tags ('{{' or '{%') in HTML attributes.      │
│└───────────────────────────────────────────────────────────────────────┘
```

---

## The 7 Verification Pillars

### 1. Trigger Affordance & JS Wiring
Every interactive trigger (button, link, tab) must have:
- A tactile CSS class (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-sm`).
- A non-empty, human-readable label.
- A functional handler: if using `onclick="myFunction(arg)"`, `myFunction` MUST be defined in the loaded `<script>` blocks or imported bundles.

### 2. Interaction & Progress State
Asynchronous operations (AI analysis, DCF recalculations, data enrichment, support ticket dispatch):
- Must immediately show feedback: disable the triggering button or show a loading spinner / `"Analyzing..."` text.
- Must handle network failures gracefully with on-screen error banners (never raw unhandled Promise rejections or native `alert()`).
- Must re-enable the trigger upon completion or failure.

### 3. DOM Element Binding Contracts (Zero Null References)
Every element queried by JavaScript via `document.getElementById('targetId')` or `document.querySelector('#targetId')` MUST be present in the rendered HTML:
```python
# Outside-in test recipe:
import re
from bs4 import BeautifulSoup

def assert_js_dom_bindings(html_content: str):
    soup = BeautifulSoup(html_content, 'html.parser')
    scripts = soup.find_all('script')
    
    for script in scripts:
        if not script.string:
            continue
        # Extract all document.getElementById calls
        target_ids = re.findall(r"document\.getElementById\(['\"]([a-zA-Z0-9_\-]+)['\"]\)", script.string)
        for target_id in target_ids:
            element = soup.find(id=target_id)
            assert element is not None, f"JavaScript references ID '{target_id}', but it is missing in the DOM!"
```

### 4. Client-to-Server Route Contracts
Client-side AJAX requests via `fetch('/api/...')` must target registered server endpoints with matching HTTP methods:
```python
def assert_fetch_routes_registered(html_content: str, app):
    soup = BeautifulSoup(html_content, 'html.parser')
    scripts = soup.find_all('script')
    registered_paths = {route.path for route in app.routes}
    
    for script in scripts:
        if not script.string:
            continue
        fetch_targets = re.findall(r"fetch\(['\"](\/[a-zA-Z0-9_\-\/]+)['\"]", script.string)
        for target in fetch_targets:
            # Check direct match or parameterized route pattern
            matched = any(target == p or p.startswith(target.split('?')[0]) for p in registered_paths)
            assert matched, f"Client script calls fetch('{target}'), but no such route is registered on FastAPI app!"
```

### 5. Viewport Centering & CSS Architecture
- Modals must be placed directly under `<body>` or at root container level, outside of scrollable tables, cards, or `overflow: hidden` wrappers.
- **Inert Ancestor Lockout Prevention:** Never set `mainEl.inert = true` or `aria-hidden="true"` on `<main>` if the modal/drawer (`#copilotModalBackdrop`, etc.) is rendered inside `{% block content %}` (`<main>`). Always hoist modals to `document.body` (`if (modal.parentElement !== document.body) document.body.appendChild(modal)`) and guard with `if (mainEl && !mainEl.contains(modal)) mainEl.inert = true`.
- **Mobile Virtual Keyboard Contract:** Modal inputs and textareas must have `font-size: 16px` (`1rem`) and call `input.focus({ preventScroll: true })` synchronously inside the click handler tick (mobile browsers ignore asynchronous `setTimeout` focus calls for opening the virtual keyboard).
- Modals must implement standard `.modal-backdrop` and `.modal-dialog` structure:
  - `position: fixed; top: 0; left: 0; width: 100%; height: 100%`.
  - `display: flex; align-items: center; justify-content: center; z-index: 1000`.
- Must support 3 dismissal mechanisms:
  1. Close button (`.modal-close` or `&times;`).
  2. Clicking outside the dialog on the backdrop.
  3. Pressing the `Escape` key (`window.addEventListener('keydown', ...)`).

### 6. Substantive Analytical Depth (Value Covenant)
Never deliver empty cards or raw user echoes. Deep-dive modals and analytical pages must compute and display:
- Financial health metrics (Altman Z-Score, ICR, Working Capital / Turnover).
- Operational ratios (Cash Conversion Cycle, Receivables Days).
- Peer benchmarking & sector percentiles.
- Supply chain & vendor linkage analysis.
- Clear qualitative insights and risk indicators.

### 7. Template Attribute & Rendering Hygiene
Rendered HTML pages must be checked for leaked template tags:
```python
def assert_template_hygiene(html_content: str):
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup.find_all(True):
        for attr_name, attr_val in tag.attrs.items():
            val_str = str(attr_val)
            assert "{{" not in val_str, f"Unrendered Jinja tag '{{{{' in <{tag.name} {attr_name}=\"{val_str}\">"
            assert "{%" not in val_str, f"Unrendered Jinja tag '{{%' in <{tag.name} {attr_name}=\"{val_str}\">"
```

### 8. Dynamic Cadence & Time-Series Rotation Contracts (Zero Static Facades)
Never test scheduled pipelines or time-series features solely with static fixtures or by checking that routes return HTTP 200:
1. **Unmocked Ingestion Testing:**
   Directly invoke scheduled worker functions (`run_daily_msme_cohort(15)`, `curate_morning_discovery_cohort()`) and assert that database records actually advance:
   ```python
   def test_daily_cadence_advancement(self):
       initial_count = get_active_msme_firms_count()
       added = run_daily_msme_cohort(count=15)
       self.assertEqual(added, 15)
       self.assertEqual(get_active_msme_firms_count(), initial_count + 15)
   ```
2. **Rotation Validation Across Consecutive Editions:**
   Assert that consecutive editions or scheduled runs do NOT merely duplicate 100% of previous items:
   ```python
   def test_consecutive_edition_rotation(self):
       edition_1 = [x["ticker"] for x in get_active_discovery_reel("2026-10-15")]
       edition_2 = [x["ticker"] for x in get_active_discovery_reel("2026-10-16")]
       intersection = set(edition_1).intersection(set(edition_2))
       # At least 25% of the reel must be fresh/rotated
       self.assertLess(len(intersection), len(edition_1), "Discovery reel has zero rotation across consecutive editions!")
   ```
3. **Data Provenance & Freshness Assertion:**
   Assert that every rendered table, card, or directory includes a visible date stamp or provenance tag showing when the record was published or ingested.

### 9. Real-Browser Pointer Hit-Testing (No `page.evaluate()` Bypasses)
Never validate interactive drawers, modals, or buttons in Playwright/Chrome by calling `page.evaluate("openCopilot()")` or `page.evaluate("closeCopilot()")`. Direct JS calls bypass browser hit-testing and miss `[inert]` self-lockouts, `pointer-events: none`, and overlapping z-index traps.
Always execute real pointer clicks and verify focus + non-inert state:
```python
page.locator("#forensicDeskFloatingDock").click(timeout=5000)
page.locator("#copilotInput").click(timeout=5000)
page.keyboard.type("Test query")
state = page.evaluate("""() => {
    const bd = document.getElementById('copilotModalBackdrop');
    const inp = document.getElementById('copilotInput');
    return {
        portaledToBody: !!(bd && bd.parentElement === document.body),
        notInert: !!(bd && !bd.closest('[inert]')),
        inputFocused: document.activeElement === inp,
    };
}""")
assert state["portaledToBody"] and state["notInert"] and state["inputFocused"]
page.locator("#copilotCloseBtn").click(timeout=5000)
```

---

## When to Run Outside-In Tests

1. **Before Committing Any UI, Modal, or Template Change:**
   Always run test suite including outside-in contract assertions.
2. **When Adding New Modals or Actions:**
   Ensure `onclick`, DOM IDs, modal backdrop, and analytical payload pass the contract.
3. **When Modifying Any Scheduled Job or Ingestion Engine:**
   Ensure time-series rotation and unmocked database incrementation pass Pillar 8.
4. **During Headless / Browser Subagent Verification:**
   Verify visual centering, real pointer click events, mobile keyboard focus, progress spinner, and modal dismissal via real pointer hit-testing before declaring completion.


