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

---

## When to Run Outside-In Tests

1. **Before Committing Any UI or Template Change:**
   Always run test suite including outside-in contract assertions.
2. **When Adding New Modals or Actions:**
   Ensure `onclick`, DOM IDs, modal backdrop, and analytical payload pass the contract.
3. **During Headless / Browser Subagent Verification:**
   Verify visual centering, click events, progress spinner, and modal appearance via screenshots or DOM inspection before declaring completion.
