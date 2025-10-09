# Copilot PR Review Instructions (NASA-PDS)

> These instructions guide GitHub Copilot when reviewing Pull Requests across NASA-PDS repos. Copilot: use this file as your primary rubric. When in doubt, ask targeted questions and propose concrete diffs.

## Review Goals
1. **Correctness & Safety**: Code does what it claims, handles edge cases, fails safely.
2. **Security & Compliance**: No obvious vulns; follows least-privilege and supply-chain hygiene.
3. **Performance & Scalability**: Efficient algorithms; streaming over buffering; cost-aware in cloud.
4. **Test Quality**: High-signal unit tests + focused integration/e2e tests; reproducible CI.
5. **Maintainability**: Clear structure, typed APIs, idiomatic code, small focused diffs.
6. **Docs & Operability**: Updated README/CHANGELOG/OpenAPI; meaningful logs/metrics.

---

## What to Review (Scope)
- Source code, tests, workflows (CI/CD), IaC (Terraform), API specs, data schemas, scripts.
- Ignore generated artifacts and vendored third-party code unless modified.

---

## High-Impact Checklist

### 1) Correctness
- [ ] Clear invariants and error handling (no silent catch/ignore).
- [ ] Input validation for public or API-reachable paths.
- [ ] Nullability / optionality handled (Java: `Optional`, annotations; Python: `Optional[T]`).
- [ ] Time, timezone, and encoding handled explicitly (UTC, UTF-8).

### 2) Security
- [ ] No secrets in code/CI/logs; uses GitHub secrets & OIDC where applicable.
- [ ] Dependency updates don’t introduce known CVEs (SCA/Dependabot passes).
- [ ] HTTP: timeouts, retries with backoff, TLS verification on; no `verify=False`.
- [ ] SQL/NoSQL/OpenSearch queries are parameterized; user input is sanitized.
- [ ] Principle of least privilege in AWS IAM; narrow resource ARNs; avoid `*`.
- [ ] SBOM present or CI job generates one (e.g., Syft); license headers intact.

### 3) Performance & Cost
- [ ] Algorithmic complexity reasonable for expected data sizes; avoids N² on hot paths.
- [ ] Streams/iterators over full in-memory loads for large files.
- [ ] OpenSearch: prefer `search_after` over deep pagination; bounded result windows.
- [ ] S3: use range/multipart and requester-pays rules where required; retries + backoff.
- [ ] Avoid chatty network loops; batch I/O; exponential backoff + jitter.

### 4) Testing
- [ ] Unit tests cover new logic & edge cases; negative tests included.
- [ ] Integration tests use local emulators (Testcontainers, LocalStack, OpenSearch/ES container) where possible.
- [ ] Deterministic tests (fixed seeds, golden files); no flakiness (no sleeps unless justified).
- [ ] Coverage signals added for critical paths (parsers, converters, API handlers).

### 5) PDS-Specific
- [ ] PDS4: schema/IM version pinned; label parsing robust; LID/LIDVID handled correctly.
- [ ] Registry/API: field names & facets align with current PDS Search API; pagination uses `search_after`.
- [ ] Data pipelines tolerate large collections and mixed product types; graceful skip & audit when malformed.
- [ ] OpenAPI contracts updated when API changes; generated clients re-synced.

### 6) Code Quality
- **Java**: Error Prone/SpotBugs clean; no raw types; prefer immutables; avoid Lombok magic where it harms clarity; `try-with-resources` for I/O; follow Google's Java Style Guide
- **Python**: Type-hints + `mypy` clean; `black` + `isort`; `pathlib` over string paths; avoid broad exceptions; follow PEP8 standards, where it makes sense.
- **General**: Small functions; single responsibility; avoid deep nesting; meaningful names; delete dead code.

### 7) Observability & Ops
- [ ] Logs have stable keys and context (no secrets); use structured logging.
- [ ] Metrics/traces for critical operations; SLO-relevant counters/histograms.
- [ ] Feature flags or config to disable risky behavior.

### 8) Docs & Change Management
- [ ] README/USAGE updated; migration notes if behavior changes.
- [ ] CHANGELOG entry with user impact.
- [ ] ADR added/updated for architectural decisions (when applicable).

---

## Copilot: How to Review & Respond

When posting review comments:
- Be **specific**: quote the line(s), explain the risk, show a fix.
- Prefer **actionable diffs**. Example:

> Performance: avoid loading entire file into memory; stream instead.  
> **Suggested change (Python)**  
> ```diff
> - data = f.read()
> - process(data)
> + for chunk in iter(lambda: f.read(1024 * 1024), b""):
> +     process(chunk)
> ```

Prioritize issues by severity:

| Severity | Meaning | Example |
|---|---|---|
| **critical** | Must fix before merge | Leaks secret, incorrect result, schema/API break without migration |
| **high** | Strongly recommended before merge | N² path on large data; IAM `*`; missing retries/timeouts |
| **medium** | Should fix soon | Test gaps on new logic, unclear error messages |
| **low** | Nice to have | Minor style, micro-perf |

---

## Copilot Review Prompts (use these)

Use these cues when analyzing diffs:

- **Correctness**: “Are there unvalidated inputs, unchecked errors, or edge cases (empty, huge, malformed) that can break the code? Propose tests.”
- **Security**: “Do changes introduce injection, path traversal, insecure deserialization, SSRF, or excessive IAM permissions? Suggest least-privilege policies.”
- **Performance**: “What’s the big-O and memory profile? Can this stream/batch? Are OpenSearch queries paginated with `search_after`?”
- **Resilience**: “Do outbound calls set timeouts, retries with backoff/jitter, and idempotency where needed?”
- **API Contracts**: “If request/response shapes changed, is the OpenAPI updated and versioned? Are clients regenerated?”
- **Testing**: “Which lines/branches are uncovered? Provide a focused test diff.”
- **Docs**: “What should be added to README and online documentation (maven site or Sphinx docs) for users/operators?”

---

## Snippets Copilot Can Propose

**Java OpenSearch search_after (Testcontainers example)**
```java
// Ensure search_after for deep pagination
// ... build query with sort on unique, immutable field(s)
```

**Python requests with robust timeouts/backoff**
```python
import requests, time, random

def get_with_retry(url, *, attempts=5, timeout=(3.05, 10)):
    for i in range(attempts):
        try:
            return requests.get(url, timeout=timeout)
        except requests.RequestException:
            time.sleep(min(2 ** i, 30) + random.random())
    raise
```

**GitHub Actions safety for secrets**
```yaml
permissions:
  contents: read
  id-token: write
  pull-requests: write
```

---

## Minimal Standards (fail if missing)
- CI green on lint, type-checks, tests.
- New/changed APIs have OpenAPI updates and sample requests.
- New logic **must** have unit tests; external effects have integration tests.
- No hard-coded secrets; no wildcard IAM for new infra.
- Performance concerns acknowledged with test or comment if unavoidable.

---

## NASA-PDS Context Cues for Copilot
- Prefer **information-model-driven** approaches (PDS4).
- Respect data volume/heterogeneity: design for **scalability** and **streaming**.
- Be **cloud cost aware** (S3, OpenSearch, egress).
- Keep **backwards compatibility** and migration paths visible.

---

## What to Praise (so we keep it!)
- Deleted code and simplified flows.
- Replacing deep pagination with `search_after`.
- Adding property-based tests for parsers/label readers.
- Converting ad-hoc scripts into repeatable CI jobs.
- Clear, documented error messages and structured logs.

---

**End of file.**
