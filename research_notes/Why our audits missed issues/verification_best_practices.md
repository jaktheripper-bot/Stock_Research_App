# Verification and Audit Best Practices: Why Bugs Escape Test Suites and Audits, and What Closes the Gaps

Scope: established practices mapped to the escape classes seen in a solo-founder FastAPI + Jinja + Postgres (Supabase) + Render cron + email + Razorpay app. Research done 2026-11-13.

Source-verification note: items marked **[fetched]** were read in this session. Items marked **[search-verified]** were confirmed through search-result summaries only. Items marked **[unverified URL, prior knowledge]** are standard references whose content I did not re-check this session. The report writer should treat those as lower confidence or re-check them.

Escape classes used below (from the brief):
- E1: auth fallback trusts unverified token claims
- E2: reflected XSS in one OAuth-callback branch
- E3: CI shell injection via workflow inputs
- E4: admin auth fails open inside an exception handler
- E5: IDOR via body `user_id`, with a test asserting the insecure behaviour
- E6: marketing claim ("released daily at 9:00 AM") contradicted by the schedule, plus a hardcoded timestamp
- E7: multi-MB pages rendering hundreds of hidden cards
- E8: raw-JSON 404 page
- E9: refunds that never reach the payment gateway
- E10: DB races in OTP consume and credit balances
- E11: docs claiming "100/100" audit scores

---

## Q1. Test oracle problem, tests that encode the bug, and detecting tests that assert insecure behaviour

### Takeaway
A test is only as good as its oracle, meaning its idea of the correct answer. When the oracle is "whatever the code does today", as in a characterization test or a test written after the code, the suite locks the bug in (E5). The fix is to derive security oracles from an external standard such as OWASP ASVS requirements or abuse cases, not from the implementation. Negative tests ("user A cannot read B's data", "a forged token is rejected", "DB down means 401/503, not 200") are the oracle that catches E1, E4 and E5.

### Cited Findings
- The oracle problem is defined as the challenge of telling correct behaviour from incorrect behaviour. The survey covers automated oracles (specifications, contracts, metamorphic relations, models) and concludes that when none is adequate, "the final source of test oracle information remains the human." Barr, Harman, McMinn, Shahbaz, Yoo, IEEE TSE 41(5), 2015, DOI 10.1109/TSE.2014.2372785 — [UCL open-access copy](https://discovery-pp.ucl.ac.uk/id/eprint/1471263) **[search-verified]**
- ASVS 5.0.0 is the current stable release, published 30 May 2025 (PDF/DOCX/CSV). It gives a requirement catalogue that can be turned directly into test cases — [OWASP ASVS](https://asvs.owasp.org/) **[fetched]**. ASVS levels: L1 is the minimum for all apps, L2 is the recommended level for apps handling sensitive data, and L3 is for critical apps — [unverified URL, prior knowledge; the fetched page did not describe levels].
- Broken Access Control stays at A01 in the OWASP Top 10:2025. OWASP reports that 100% of tested applications showed some form of it. The category now absorbs SSRF and explicitly covers BOLA/BFLA (object- and function-level authorization) — [OWASP A01:2025](https://owasp.org/Top10/2025/A01%5F2025-Broken%5FAccess%5FControl/); [Qualys summary, June 2026](https://blog.qualys.com/qualys-insights/2026/06/15/what-changed-in-owasp-top-10-2025-and-recommendations-for-each-category) **[search-verified]**
- OWASP Top 10:2025 adds A10 "Mishandling of Exceptional Conditions", which covers poor error and exception handling. This is the category for E4 (fail-open except) and E8 (raw error/404 output) — [eSecurityPlanet](https://www.esecurityplanet.com/threats/news-owasp-top-10-2025/); [OWASP 2025 intro](https://owasp.org/Top10/2025/0x00_2025-Introduction/) **[search-verified]**. Sources disagreed in late 2025 on whether it was a release candidate or final; check its current status.
- Characterization tests, from Michael Feathers' *Working Effectively with Legacy Code* (2004), deliberately capture current behaviour, bugs included, as a safety net before refactoring. They are not specifications — [unverified URL, prior knowledge: https://en.wikipedia.org/wiki/Characterization_test].
- OWASP Authorization Cheat Sheet: deny by default, enforce authorization on every request server-side, validate object ownership, and write unit and integration tests for authorization logic — [unverified URL, prior knowledge: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html].

### Inferences
- E5 is a textbook oracle failure. The test's expected value came from the implementation (the body `user_id` is honoured), not from the requirement (the user ID must come from the session). Coverage and pass rate both looked healthy.
- **Cheap application.** Keep a `tests/security/` suite where every test name is an ASVS requirement ID or abuse case, and every assertion is negative: cross-user 403/404, forged or unsigned token rejected, `alg=none` rejected, DB exception leads to deny. Add a review rule that any test asserting a 200 on a request carrying another user's ID needs a written justification.
- **Detecting tests that encode insecure behaviour.** (a) Grep tests for request bodies or params containing `user_id`, `role`, `is_admin`, or `price`, and check what they assert. (b) Run mutation testing on auth code (Q6). If deleting the ownership check does not fail a test, no oracle exists. (c) Write a "what should be impossible" list per route from the ASVS V8 Authorization chapter and diff it against the tests.

### Gaps
- I did not fetch ASVS 5.0 chapter numbering or level definitions directly. Verify chapter IDs (e.g. Authorization, Session, OAuth) before citing specific requirement numbers.
- I found no primary empirical study specifically on "tests that assert insecure behaviour". The concept follows from the oracle literature and characterization-test practice.

---

## Q2. Goodhart's law and gate gaming: limits of grep/AST rule gates vs semantic review

### Takeaway
Once a checker's score or pass becomes the goal, effort shifts to satisfying the checker, not to the property it stands for. Code coverage is the best-studied case: it correlates only weakly with fault detection once suite size is controlled for. Grep/AST gates catch known syntactic shapes. They cannot see semantic flaws such as a missing ownership check, a fail-open branch reached through an unexpected exception type, or prose contradicting a cron schedule. Self-reported "100/100" scores (E11) are Goodhart in its purest form.

### Cited Findings
- Inozemtseva & Holmes (ICSE 2014, ACM SIGSOFT Distinguished Paper) studied 31,000 generated suites across five Java systems of up to 724 KLOC, using mutation kill rate as the effectiveness measure. Once suite size is controlled for, the coverage–effectiveness correlation drops to low-to-moderate, so it is "not generally safe to assume that effectiveness is correlated with coverage." Coverage remains useful for finding untested code but should not be a target — [paper PDF](https://cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf); [Never Work in Theory summary](https://neverworkintheory.org/2021/09/24/coverage-is-not-strongly-correlated-with-test-suite-effectiveness.html) **[search-verified]**
- Industry reports describe coverage targets being met with trivial-input or assertion-free tests, for example a team hitting 85% with tests that barely verified anything — [Industrial Logic, "Metrics Mislead"](https://www.industriallogic.com/blog/metrics-mislead/) **[search-verified; practitioner opinion]**
- Goodhart's original 1975 phrasing was about statistical regularities collapsing under control pressure. "When a measure becomes a target…" is a later popularization (Strathern) — noted in the same search set; [briefhq overview](https://briefhq.ai/blog/goodharts-law/) **[search-verified; secondary]**
- Suggested countermeasure: pair a quantity metric with an outcome metric (e.g. coverage with escaped defects) so gaming one shows up in the other — [library-d7m notes](https://library-d7m.pages.dev/mental-models-for-engineers/second-order-effects/unintended-side-effects) **[search-verified; secondary]**
- Google's mutation-testing work found that a developer-feedback loop raised the share of surfaced findings judged useful from 20% to 80%. Gate value depends on findings being actionable, not on count — [Petrović & Ivanković, ICSE-SEIP 2018](https://research.google/pubs/state-of-mutation-testing-at-google/) (PDF mirror: [umich](https://web.eecs.umich.edu/~weimerw/2022-481W/readings/mutation-google.pdf)) **[search-verified]**

### Inferences
- The project's AST gate (`verify_reality_audit.py`, GATE-1..12) is a useful lint, but it is the same instrument the code is written to pass. It cannot detect E1, E2 (one branch), E4, E5, E9 or E10, which are semantic or interprocedural. "Gates green" therefore says nothing about these classes.
- **Cheap application.** (1) Never publish a self-computed score as a quality claim. Report the raw findings list and the date instead. (2) Rotate in an instrument the code was not written against: Semgrep/CodeQL with community rule packs, Bandit, ZAP baseline, and a mutation run. (3) Track escaped defects (bugs found after merge or in prod) as the outcome metric next to any gate metric.
- Rule gates suit syntactic invariants (no `ssl._create_unverified_context`, no `| safe` on user input). Semantic properties need behavioural tests: auth fail-closed, ownership, idempotency.

### Gaps
- No primary study measures AST-gate gaming specifically. The evidence is the coverage literature plus practitioner reports.

---

## Q3. Escape analysis and defect root-cause methods

### Takeaway
Treat each escaped bug as data about the verification process, not just the code. For each escape, ask what the defect was (type), what finally surfaced it (trigger), and which earlier activity should have caught it and why it didn't. Orthogonal Defect Classification (ODC) supplies the type × trigger matrix. Blameless postmortems supply the narrative and action items. The SSDF requires root-cause analysis of vulnerabilities.

### Cited Findings
- ODC was developed by Ram Chillarege at IBM Research and published in IEEE TSE in 1992. *Defect type* is the nature of the fix (seven values in the original scheme, such as assignment, checking, algorithm, interface). *Trigger* is the condition or activity that surfaced the fault. Crossing type with trigger measures how effective each testing activity is. Chillarege reports the cost of analysis fell from about 1 hour to about 4 minutes per defect — [Chillarege, ODC concept](https://www.chillarege.com/node/23); [ODC – a 10x for Root Cause Analysis](https://chillarege.com/node/16) **[search-verified]**. Calibration distributions are reportedly proprietary.
- Google SRE book, chapter 15 (Postmortem Culture). Agree trigger criteria in advance: user-visible downtime or degradation, any data loss, on-call intervention, long resolution time, and monitoring failures where a human found the issue. A postmortem records impact, mitigation, root cause(s) and follow-up actions. "An unreviewed postmortem might as well never have existed." "You can't 'fix' people, but you can fix systems and processes." — [Google SRE Book ch. 15](https://sre.google/sre-book/postmortem-culture/) **[fetched]**
- NIST SP 800-218 SSDF v1.1, published February 2022, organizes practices into PO (Prepare the Organization), PS (Protect Software), PW (Produce Well-Secured Software) and RV (Respond to Vulnerabilities). RV.2/RV.3 cover assessing and fixing vulnerabilities and analysing them for root causes so similar ones can be prevented — [NIST CSRC SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) **[fetched: date and version confirmed; practice IDs from prior knowledge, verify in the PDF]**

### Inferences
- A sample ODC-style classification of the escape list (trigger = what found it; missed-by = the activity that should have):
  - E1, E4: type checking/assignment; missed by fault-injection and negative tests.
  - E2: missed by branch-level XSS tests and an autoescape audit.
  - E3: missed by CI-config review against GitHub guidance.
  - E5: missed by an oracle defect (a wrong test).
  - E6, E11: claim-vs-behaviour; missed because no test reads copy.
  - E7: missed by a performance budget.
  - E8: missed by error-path UI tests.
  - E9: interface defect with an external system; missed by reconciliation.
  - E10: timing/serialization; missed by concurrency tests.
- The pattern is that almost every escape sits on a path the suite never exercises: an error path, a second branch, an external system, concurrency, or production config. That is the systemic root cause, not any one bug.
- **Cheap application.** Keep an `ESCAPES.md` ledger, one row per escaped bug, with columns for type, trigger, missed-by and new guard (test/gate/monitor). Monthly, compute escaped-defect rate (escaped ÷ total found) and see which "missed-by" column dominates.
- "5 Whys" is a lightweight fit for a solo dev, but it tends to converge on one linear cause. ODC's type × trigger view and the SRE "contributing factors" framing correct for that. [No primary source fetched for 5 Whys; Toyota origin is prior knowledge.]

### Gaps
- I did not find a public primary source on a named "Google/Microsoft escape analysis" process or a canonical "defect escape rate" definition. The term is common in industry but I located no authoritative spec this session.

---

## Q4. Threat modelling, ASVS, OWASP Top 10 (access control and business logic), GitHub Actions script injection

### Takeaway
A one-page threat model per trust boundary (browser→FastAPI, OAuth provider→callback, GitHub→CI runner, Razorpay→webhook, cron→DB) would have flagged E1–E5 and E9–E10 in advance. GitHub's own hardening guide names the exact E3 pattern: never interpolate `${{ … }}` untrusted context into `run:` scripts; pass it through `env:` and quote it.

### Cited Findings
- GitHub Actions hardening guidance [fetched]:
  - Expressions such as `github.event.pull_request.title` can inject commands into inline scripts. Preferred fixes are a JavaScript action taking the value as an argument, or assigning the value to an intermediate environment variable so it "doesn't interact with the script generation process", plus double-quoting shell variables.
  - Avoid `pull_request_target` unless necessary, and never check out untrusted PR code in it. Prefer `workflow_run` for privilege separation.
  - Give `GITHUB_TOKEN` least privilege: default to read-only contents and raise per job.
  - Pin third-party actions to full commit SHAs, and verify the SHA belongs to the upstream repo. The guide says a lockfile, where adopted, "supersedes SHA pinning".
  - Source: [GitHub Docs: Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)
- OWASP Top 10:2025: A01 Broken Access Control (incl. BOLA/IDOR, SSRF); A02 Security Misconfiguration (moved up from #5); A03 Software Supply Chain Failures (relevant to E3/CI); A10 Mishandling of Exceptional Conditions (new) — [OWASP Top 10:2025](https://owasp.org/Top10/2025/0x00_2025-Introduction/); [Orca summary](https://orca.security/resources/blog/owasp-top-10/) **[search-verified]**
- ASVS 5.0.0 (30 May 2025) is the testable requirement set to derive cases from — [asvs.owasp.org](https://asvs.owasp.org/) **[fetched]**
- STRIDE (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege) is Microsoft's threat-classification mnemonic used in the SDL Threat Modeling Tool — [unverified URL, prior knowledge: https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats]. OWASP's Threat Modeling Cheat Sheet poses four questions: what are we working on, what can go wrong, what are we going to do about it, did we do a good job — [unverified URL, prior knowledge: https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html].

### Inferences
- STRIDE mapped to the escapes:
  - Spoofing: E1 (unverified token claims).
  - Tampering / Elevation: E5 (body `user_id`), E3 (workflow input → shell).
  - Information disclosure: E2 (XSS), E8 (raw JSON error).
  - Elevation: E4 (fail-open admin).
  - Tampering / Repudiation: E9, E10 (money and OTP state).
- **Cheap application.** Write a 30-minute STRIDE table per trust boundary in `docs/threat_model.md` and turn each "what can go wrong" row into one negative test. For CI, run `zizmor` or `actionlint` (a static analyser for workflow injection) in pre-commit. Grep `.github/workflows` for `${{ github.event` or `${{ inputs.` inside `run:` blocks. [zizmor/actionlint are prior knowledge, not verified this session.]
- For E2: one OAuth-callback branch rendered a parameter unescaped. Test every branch, including error branches like `?error=…&error_description=…`, with an XSS payload and assert it comes back escaped. Ban `|safe` and `Markup()` on request-derived data.

### Gaps
- I did not fetch the ASVS 5.0 level definitions or OAuth chapter contents. I also did not fetch Microsoft STRIDE docs this session.

---

## Q5. Production-facing verification: synthetic monitoring, contract tests, canaries, RUM, performance budgets, DOM size

### Takeaway
Many escapes (E6 schedule drift, E7 page weight, E8 404 rendering, E9 refunds) only exist in the deployed system and its config. They are invisible to unit tests on a dev box. Synthetic monitoring, meaning a subset of tests run against production on a schedule, plus performance budgets in CI, covers this layer cheaply.

### Cited Findings
- Fowler defines synthetic (semantic) monitoring as running a subset of automated tests against the live production system on a regular basis (bliki, 25 Jan 2017) — [Martin Fowler, SyntheticMonitoring](https://martinfowler.com/bliki/SyntheticMonitoring.html) **[search-verified]**. Microsoft's engineering playbook frames these as "synthetic transactions" and says they complement, not replace, real-user monitoring — [Microsoft Code-With Playbook](https://microsoft.github.io/code-with-engineering-playbook/automated-testing/synthetic-monitoring-tests/) **[search-verified]**
- The SRE postmortem triggers include monitoring failures where an incident was found manually, so a gap in monitoring is itself an incident — [Google SRE ch.15](https://sre.google/sre-book/postmortem-culture/) **[fetched]**
- DOM size: Lighthouse warns above 800 nodes and fails above 1,400. Large DOMs raise style, layout and paint cost and hurt INP, where "good" is ≤200 ms. Recommended fixes include `content-visibility`, adding initially hidden content only when needed ("additive rendering"), CSS containment, and simpler selectors — [web.dev, DOM size and interactivity](https://web.dev/articles/dom-size-and-interactivity) **[fetched; page date not shown]**
- Lighthouse CI supports assertions in `lighthouserc` (e.g. `"dom-size": ["error", {"maxNumericValue": …}]`, `resource-summary:document:size`) and budget files. `treosh/lighthouse-ci-action` fails the build when a URL exceeds the budget. Units trap: budget.json uses KB, while LHCI `maxNumericValue` for resource sizes is in bytes — [Lighthouse CI Action](https://www.github.com/marketplace/actions/lighthouse-ci-action?version=v2); [Unlighthouse budgets guide](https://unlighthouse.dev/learn-lighthouse/lighthouse-ci/budgets) **[search-verified; secondary for syntax, verify against GoogleChrome/lighthouse-ci docs]**
- Consumer-driven contract tests (Pact) check that a provider still satisfies what consumers expect. Fowler's "ContractTest" article recommends separate tests against real external services to detect drift — [unverified URL, prior knowledge: https://martinfowler.com/bliki/ContractTest.html; https://docs.pact.io/].

### Inferences
- **E7.** A Lighthouse CI assertion (`dom-size` error at ~1,400; `resource-summary:document:size` error at e.g. 300 KB) on the five heaviest directory pages would have failed the build. Fix by paginating or lazy-loading cards instead of rendering hidden ones.
- **E8.** Add a synthetic check: GET a nonsense path with `Accept: text/html`, then assert status 404, `Content-Type: text/html`, and the presence of the site chrome.
- **E6.** A synthetic "freshness" probe asserts that the latest edition timestamp is within N hours of the advertised schedule, and alerts otherwise. It runs from outside Render, e.g. a GitHub Actions cron or a free uptime service.
- **E9.** A daily contract/reconciliation probe against Razorpay (Q8).
- **Cheap application.** A `tests/synthetic/` pytest file run by a GitHub Actions `schedule:` every 30 minutes against prod. It checks home, a dossier, 404 HTML, `/health`, freshness and login page CSP headers, and opens an issue on failure. Add LHCI on PRs for the top pages.

### Gaps
- I did not fetch Google SRE "Monitoring Distributed Systems" (four golden signals) or the official LHCI assertion docs this session.
- I found no primary source for canary analysis tailored to single-instance Render deploys. Render's own deploy health-check docs were not checked.

---

## Q6. Spec/claim vs behaviour: acceptance tests from marketing copy, consumer protection, timestamp honesty

### Takeaway
Marketing and pricing copy are specifications. Every factual promise ("daily at 9:00 AM", "refund within N days", feature lists on pricing tiers) should map to an executable check against real config or prod data. In India, misleading claims about the timing or availability of a service fall under consumer-protection law. The CCPA's Dark Patterns Guidelines (30 Nov 2023) cover false urgency and related practices.

### Cited Findings
- The Central Consumer Protection Authority issued the "Guidelines for Prevention and Regulation of Dark Patterns, 2023" on 30 November 2023 under Section 18 of the Consumer Protection Act, 2019. They apply to platforms, advertisers and sellers offering goods or services in India and list 13 practices, including false urgency ("falsely stating or implying the sense of urgency or scarcity…"). Illustrations are guidance, not binding interpretation, and commentators note no standalone penalty is specified in the guidelines — [Vikaspedia text](https://en.vikaspedia.in/viewcontent/social-welfare/social-awareness/consumer-education/the-guidelines-for-prevention-and-regulation-of-dark-patterns-2023); [JSA Law summary](https://www.jsalaw.com/newsletters-and-updates/ccpa-issues-guidelines-for-prevention-and-regulation-of-dark-patterns-2023/); [Mondaq](https://www.mondaq.com/india/consumer-trading-unfair-trading/1398262/ccpa-issues-guidelines-for-prevention-and-regulation-of-dark-patterns-2023-effective-30-november-2023) **[search-verified; rely on the gazette text for legal use]**
- The Consumer Protection Act, 2019 defines "misleading advertisement" and empowers the CCPA to act on it, separately from the dark-patterns guidelines — [unverified, prior knowledge; check the Act text at https://consumeraffairs.nic.in].
- Oracle survey: specifications and contracts are a primary source of automated oracles — [Barr et al. 2015](https://discovery-pp.ucl.ac.uk/id/eprint/1471263) **[search-verified]**

### Inferences
- E6 and E11 are claim-vs-behaviour escapes. No test ever read the copy, so the copy was never a spec. A hardcoded timestamp is also a provenance lie: the UI asserts freshness it does not measure.
- **Cheap application.** Keep a `claims.yaml` registry. Each user-facing promise (text, page, and check) has a test that (a) parses the cron expression from `render.yaml` and asserts it matches the advertised time, in IST and with UTC conversion explicit, and (b) asserts the rendered "last updated" value equals `MAX(edition_date)` from the DB, not a literal. A CI grep fails if a date or time literal appears in a template near "updated" or "released".
- For a SEBI-adjacent investment-research product, overstated freshness or audit claims carry regulatory as well as consumer-law risk. Prefer understated, measured statements ("usually published by ~9:30 AM IST; last run: <timestamp>").

### Gaps
- I did not verify whether SEBI's Research Analyst regulations impose specific disclosure-timing rules relevant to "released daily" claims. Out of scope for this search.
- I did not fetch the official gazette PDF of the dark-patterns guidelines.

---

## Q7. Mutation testing, property-based testing, differential testing, fault injection

### Takeaway
These techniques test the tests. Mutation testing asks whether the suite would notice if a check were deleted. Property-based testing generates inputs the author didn't think of. Fault injection forces dependencies (DB, JWKS, Razorpay) to fail and asserts that the system fails closed. Fault injection is the direct oracle for E1 and E4.

### Cited Findings
- Google's diff-based mutation testing (Petrović & Ivanković, ICSE-SEIP 2018) mutates only changed lines and surfaces results in code review: more than 70,000 diffs, 1.1M mutants, 150,000 actionable findings, and usefulness rising from 20% to 80% through feedback. The TSE 2021 journal version (with Just and Fraser) reports nearly 17M mutants — [ICSE-SEIP'18 PDF mirror](https://web.eecs.umich.edu/~weimerw/2022-481W/readings/mutation-google.pdf); [TSE 2021 PDF](https://homes.cs.washington.edu/~rjust/publ/practical_mutation_testing_tse_2021.pdf); [SE Radio 632 interview, Sept 2024](https://se-radio.net/2024/09/se-radio-632-goran-petrovic-on-mutation-testing-at-google/) **[search-verified]**
- Mutation score is used as the ground-truth effectiveness measure in the coverage study, and coverage was only weakly correlated with it — [Inozemtseva & Holmes 2014](https://cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf) **[search-verified]**
- Metamorphic testing, where relations between outputs of related inputs act as oracles, is reviewed as an oracle-automation technique in [Barr et al. 2015](https://discovery-pp.ucl.ac.uk/id/eprint/1471263) **[search-verified]**
- Python tooling: `mutmut` / `cosmic-ray` for mutation testing and Hypothesis for property-based testing — [unverified URL, prior knowledge: https://hypothesis.readthedocs.io/; https://github.com/boxed/mutmut].

### Inferences
- **Mutation testing, cheaply.** Run `mutmut` only on `auth/`, `billing/`, and the admin dependency module, Google-style scoped to changed files. Any surviving mutant that deletes or negates an `if not owner`, `verify=True`, or `raise HTTPException(401)` is a missing test. This would have exposed E5's insecure test and E4's fail-open path.
- **Fault injection, cheaply.** Parametrize auth tests with monkeypatched failures: DB `OperationalError`, JWKS fetch timeout, Supabase returning `{}`, an expired token, an `alg=none` token. Assert 401/403/503 and never 200. One pytest fixture covers E1 and E4.
- **Property-based.** Use Hypothesis on credit arithmetic (balance never negative; sum of ledger rows equals balance) and on HTML escaping (for any string `s`, the rendered callback never contains raw `<script` from `s`).
- **Differential.** Compare the app's payment state with Razorpay's API (Q8), or compare the old and new render of a page for DOM node count and size.

### Gaps
- I found no empirical study quantifying mutation testing on Python web apps specifically.

---

## Q8. Database concurrency testing and payment reconciliation

### Takeaway
Check-then-act sequences in application code (read OTP → compare → mark used; read balance → subtract → write) are race windows that sequential tests never hit. Close them with atomic single-statement updates (`UPDATE … WHERE used=false RETURNING`, `UPDATE … SET bal = bal - x WHERE bal >= x`) or row locks. Prove the fix with a parallel-request test. For payments, the gateway is the source of truth: treat your DB as a cache, and run a scheduled reconciliation that diffs it against Razorpay.

### Cited Findings
- PostgreSQL: `SELECT … FOR UPDATE` locks the rows "as though for update", blocking other transactions from locking, modifying or deleting them until commit. A concurrent `FOR UPDATE` waits, then sees the updated row. Under REPEATABLE READ/SERIALIZABLE it errors if the row changed. Advisory locks have application-defined meaning, and transaction-level ones release automatically at commit — [PostgreSQL docs: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) **[fetched]**. `NOWAIT`/`SKIP LOCKED` are documented on the SELECT reference page [not fetched].
- PortSwigger "limit overrun" races: send many requests to a single-use or limited endpoint at once (OTP redeem, coupon, credit spend). The single-packet attack (Black Hat USA 2023, published 18 Oct 2023) completes 20–30 HTTP/2 requests in one TCP packet, which removes network jitter and makes even tiny race windows exploitable. It is available in Burp Repeater ("Send group in parallel") and Turbo Intruder — [PortSwigger Web Security Academy: Race conditions](https://portswigger.net/web-security/race-conditions); [Kettle, "The single-packet attack"](https://portswigger.net/research/the-single-packet-attack-making-remote-race-conditions-local); [Smashing the state machine](https://portswigger.net/research/smashing-the-state-machine) **[search-verified]**
- Razorpay refunds: a refund can stay `pending` while the bank or network processes it. Razorpay recommends handling both the Refund API response (immediate status) and the `refund.processed` webhook (final status). `refund.failed` signals inability to process. Razorpay may mark a refund processed before the ARN/RRN arrives. `settlement.processed` carries a UTR for matching against bank statements — [Razorpay Refund webhooks](https://razorpay.com/docs/webhooks/refunds/); [Razorpay Refund FAQs](https://razorpay.com/docs/us/payments/refunds/faqs.md); [Settlement webhooks](https://razorpay.com/docs/us/webhooks/settlements.md) **[search-verified]**
- A scheduled job that lists recent payments and refunds from the gateway API and diffs them against the local DB is a commonly recommended pattern. This is third-party, not official Razorpay guidance — [DEV: Razorpay webhooks done right (2026)](https://dev.to/buildbyravirai/razorpay-webhooks-done-right-2026-signature-verification-idempotency-and-reconciliation-a9m) **[search-verified; secondary]**

### Inferences
- **E10, cheap.** Write a pytest that opens N=20 threads or `asyncio.gather` calls hitting `/verify-otp` or `/spend-credit` simultaneously against a real Postgres (a Supabase branch, or local Docker). Assert exactly one success, or final balance = initial − (successes × cost) and never below 0. Implement consume as one conditional `UPDATE … RETURNING`, and add a DB `CHECK (balance >= 0)` as a backstop.
- **E9, cheap.** Three guards:
  - A refund in the app is only "done" when Razorpay returns a refund ID. Store `razorpay_refund_id` with a NOT NULL constraint for status `refunded`.
  - Handle the `refund.processed` and `refund.failed` webhooks with signature verification and idempotency keyed on event ID.
  - Run a nightly reconciliation cron that lists Razorpay refunds and payments for the last 7 days, diffs them against the DB, and emails or opens an issue on any mismatch (an app-side refund with no gateway refund, or the reverse).
- Webhook handlers must be idempotent, because gateways retry. Store processed event IDs with a unique constraint.

### Gaps
- I did not find an official Razorpay reconciliation-API guide or a settlement-report API endpoint in these results. Check the Razorpay API reference for `GET /refunds` and settlement recon endpoints.

---

## Q9. Multiple independent reviewers and tools (diversity of methods) and triaging disagreement

### Takeaway
Different verification methods catch different defect classes. ODC's type × trigger matrix exists precisely to show which activity finds which defects, and Google found that tool findings are only valuable when triaged for actionability. Use independent instruments (SAST, DAST, mutation, synthetic probes, a fresh-eyes human or LLM reviewer given no project rules), and treat their disagreement as a signal that needs evidence, not a vote.

### Cited Findings
- Crossing defect type with trigger measures "the effectiveness of the testing for a particular maturity of product development". Different triggers (review, unit, system, field) surface different defect types — [Chillarege ODC](https://www.chillarege.com/node/23) **[search-verified]**
- Google mutation testing: findings shown in code review with feedback buttons. Pruning unproductive mutants raised perceived usefulness from 20% to 80% — [Petrović & Ivanković 2018](https://web.eecs.umich.edu/~weimerw/2022-481W/readings/mutation-google.pdf) **[search-verified]**
- Postmortem drafts are reviewed by senior engineers for whether the root cause analysis went deep enough. Independent review is part of the process — [Google SRE ch.15](https://sre.google/sre-book/postmortem-culture/) **[fetched]**
- Synthetic monitoring complements real-user monitoring and does not replace it — [Microsoft playbook](https://microsoft.github.io/code-with-engineering-playbook/automated-testing/synthetic-monitoring-tests/) **[search-verified]**

### Inferences
- The project's escapes slipped through because every check shared one viewpoint: rules written by the same author, run on the same local corpus, asserting the same assumptions. Defence in depth needs methods that fail differently: static (Semgrep/CodeQL/Bandit/zizmor), dynamic (OWASP ZAP baseline against staging), test-strength (mutation), production (synthetic plus reconciliation), and human/adversarial review (a reviewer briefed with the threat model, not with the project's own "100/100" docs).
- **Triage rule for disagreements, cheap.** (1) A finding is resolved only by a reproducing test, either a failing test that becomes passing or a test proving the finding false. It is never resolved by argument or a gate score. (2) When tools disagree, the more specific evidence wins, such as a concrete request/response over a pattern match. (3) Record dismissed findings with a reason, so recurring false positives can be suppressed explicitly rather than silently.
- Do not let any reviewer, human or AI, read the project's self-assessment docs before reviewing. Anchoring on "100/100" is how claims like E11 propagate.

### Gaps
- I found no primary empirical study quantifying the marginal defect yield of adding a second, diverse tool for small web apps. The diversity argument here rests on ODC's trigger concept and practitioner consensus.
- Not researched: OWASP ZAP baseline docs, Semgrep/CodeQL rule coverage for FastAPI/Jinja, and LLM-reviewer effectiveness studies.
