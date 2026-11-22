# Penetration Test — Component Methods

Signatures and purpose only. Business rules (exact limits, schema fields, rule lists, test catalogue) are defined in
Functional Design, per unit. Python 3.12, typed; names are indicative and may be refined there without changing the
design. "Raises" lists the failures a caller must handle.

Shared types (in `pentest/src/pentest/types.py`):

```python
class Phase(Enum): PREFLIGHT, BUILD, UP, SEED, ISOLATION, SUITE, SCANNERS, NORMALISE, VALIDATE, REPORT, TEARDOWN
class FindingState(Enum): CONFIRMED, NEEDS_VALIDATION, REJECTED, HARDENING_NOTE
class Severity(Enum): INFORMATIONAL, LOW, MEDIUM, HIGH, CRITICAL
@dataclass(frozen=True) class LiveIdentity: container_names: frozenset[str]; published_ports: frozenset[int]; database_names: frozenset[str]; project_name: str
@dataclass(frozen=True) class ResourceLimits: cpus: float; mem_mb: int; pids: int
@dataclass(frozen=True) class Violation: rule: str; service: str | None; detail: str
@dataclass(frozen=True) class Candidate: source: str; title: str; attacker: str; boundary: str; paths: list[str]; evidence: str
```

## C1. Stack Manager

| Method | Purpose | Input → output |
|---|---|---|
| `render_config(project: str) -> ComposeConfig` | Run `docker compose config` for the throwaway project and parse it | project name → rendered configuration |
| `build(config) -> BuildRecord` | Build product and support images under project-prefixed tags | → image digests, commit, `source_clean: bool` |
| `up(config, limits: dict[str, ResourceLimits], timeout_s: int) -> StackHandle` | Start all services with limits | → handle (project, network, service names) |
| `wait_healthy(handle, timeout_s: int) -> None` | Wait for every service's health check | raises `StackUnhealthy` |
| `schema_revision(handle) -> str` | Read the migration revision reached from empty | → revision id |
| `mark_synthetic(handle) -> None` | Set the synthetic-data marker on the database | |
| `export_images(handle, dest: Path) -> list[Path]` | `docker save` the built images for the offline scan | → tarball paths |
| `teardown(handle, remove_volumes: bool = True) -> TeardownReport` | Stop and remove containers, volumes, networks | → what was removed |
| `leftovers(project: str) -> list[str]` | Anything of the project still present | → resource names (must be empty) |

## C2. Compose Linter

| Method | Purpose |
|---|---|
| `load_live_identity(compose_file: Path) -> LiveIdentity` | Read names, ports, database name from the repository's own `docker-compose.yml` (never `.env`) |
| `lint(config, live: LiveIdentity) -> list[Violation]` | Apply the D3 safety rules to the rendered configuration |
| `parity(config, live_compose: Path) -> list[Difference]` | Compare throwaway services with the real compose file; differences outside the allowed list are violations |
| `assert_clean(config, live) -> None` | Raises `UnsafeStack` with every violation if any |

## C3. Request Guard

| Method | Purpose |
|---|---|
| `Guard(allowed_hosts: frozenset[str], live: LiveIdentity)` | Build a guard for one run |
| `check_url(url: str) -> None` | Raises `GuardRefusal` unless the host is allowlisted and not live |
| `check_database(dsn: str) -> None` | Raises `GuardRefusal` if the name is live or the synthetic marker is missing |
| `httpx_hook() -> Callable` | Request hook that calls `check_url` on every request, redirects included |
| `self_test() -> list[CaseResult]` | Try every live port and name and a set of lookalikes; each must be refused |

## C4. Synthetic Seed

| Method | Purpose |
|---|---|
| `generate(random_seed: int) -> SeedPlan` | Build the full deterministic data plan in memory |
| `apply(plan: SeedPlan, engine) -> SeedSummary` | Insert using the project's own models; refuses unless `check_database` passes |
| `verify(summary: SeedSummary) -> list[str]` | Names of any feature with no data (must be empty) |

## C5. Stub Server

| Method / endpoint | Purpose |
|---|---|
| `generate_ca(hostnames: list[str], out_dir: Path) -> CertBundle` | Throwaway authority and server certificate, public certificate published to the shared volume |
| `serve(scenarios: ScenarioStore) -> None` | Serve the Google, Gemini and OpenAI-style endpoints |
| `POST /_control/scenario` `{name, payload}` | Select the reply for a test (normal, hostile text, oversized, malformed, slow, error) |
| `GET /_control/requests?host=` | Everything the application sent to a stubbed host, for assertions |
| `POST /_control/reset` | Clear scenarios and the request log between tests |
| `hostnames() -> list[str]` | The real hostnames the stub takes as network aliases |

## C6. Track B Suite

| Item | Purpose |
|---|---|
| fixture `client` | Guarded HTTP client against the API and frontend service names |
| fixture `signed_in(user)` | Token obtained through the real login route |
| `forge_token(claims: dict, key: str, alg: str) -> str` | Craft tampered, expired or wrongly signed tokens |
| fixture `caps` | The fixed limits (requests, bytes, seconds) for the exhaustion and guessing tests |
| fixture `stubs` | Control interface of C5 |
| fixture `db_oracle` | Read-only checks of the throwaway database |
| fixture `browser_page` | Headless browser page from the runner image, guarded |
| marker `@finding("PT-NNN")` | Bind a test to a finding id; applies `xfail(strict=True)` while the finding is open |
| `catalogue() -> list[CatalogueEntry]` | `(test id, area, OWASP API Top 10 item, ASVS item)` for coverage reporting |

## C7. Scanner Adapters

| Method | Purpose |
|---|---|
| `run_zap_baseline(target_url: str, limits: ResourceLimits, time_limit_s: int) -> ScanResult` | Baseline web scan |
| `run_zap_api_scan(openapi_url: str, token: str, limits, time_limit_s) -> ScanResult` | API scan driven by the OpenAPI document |
| `refresh_trivy_db(volume: str) -> DbRefreshResult` | The separate, announced download; records size and date |
| `run_trivy(kind: Literal["image","fs","config"], subject: Path) -> ScanResult` | Offline scan with `--network none` |
| `normalise(result: ScanResult) -> list[Candidate]` | Map to `needs_validation` candidates with the scanner's rule id, version, digest |

## C8. Findings Register and Validator

| Method | Purpose |
|---|---|
| `Register.load(path: Path) -> Register` / `save(path)` | Read and write `findings.json` |
| `add_candidate(c: Candidate) -> str` | Create a record in `needs_validation`; returns its id |
| `confirm(id: str, run: RunResults, severity: Severity) -> None` | Move to `confirmed` only if the bound test xfailed in `run` on an unmodified commit; raises `NoProof` |
| `reject(id: str, reason: str)` / `note_hardening(id: str, text: str)` | The other two states |
| `record_owner_notice(id: str, when: date) -> None` | A2: the date the owner was told of a high or critical finding |
| `Validator.validate(reg, repo_root: Path, suite_index: SuiteIndex) -> list[Problem]` | Schema, cited paths and lines exist, state rules, two-way test binding, A2 date, Leak Check |
| `funnel(reg) -> Funnel` | Counts by state for the report |

## C9. Audit Kit

| Method | Purpose |
|---|---|
| `Ledger.load(path) / save(path)` | Coverage ledger of units to hunt |
| `Ledger.mark(item_id, wave: int, candidates: int, depth: Literal["deep","shallow"])` | Record the outcome of a hunt; shallow is not clean |
| `build_workpackage(group: str, procedure: Path, out: Path) -> Path` | Plain file: group, source paths, procedure, output format, nothing else |
| `ingest_candidates(scratch_dir: Path) -> list[Candidate]` | Parse a sub-agent's candidate files for me to review |
| `RunBudget(caps: dict[str, int], ceiling: int = 60)` | Cap table from the execution plan |
| `RunBudget.charge(kind: str) -> None` | Count one sub-agent run; raises `BudgetExceeded` |
| `RunBudget.report() -> BudgetReport` | Runs used by kind, for the pause before wave 2 and the final report |

## C10. Leak Check

| Method | Purpose |
|---|---|
| `load_patterns(path: Path \| None) -> Patterns` | Raises `LeakCheckUnconfigured` if the local file is absent |
| `scan(paths: list[Path], patterns: Patterns) -> list[Hit]` | `Hit(pattern_no, file, line)`: never the matched text |

## C11. Report Generator

| Method | Purpose |
|---|---|
| `render(reg: Register, ledger: Ledger, meta: RunMeta) -> str` | The full `REPORT.md` text |
| `write(text: str, dest: Path) -> None` | Runs the Leak Check first; refuses on a hit |
| `RunMeta` | commit, source clean flag, image digests, tool versions, caps used, sub-agent runs, date |

## C12. Run Orchestrator

| Method | Purpose |
|---|---|
| `run(opts: RunOptions) -> RunOutcome` | The fixed phase sequence; teardown in a `finally` |
| `preflight(opts) -> PreflightReport` | Linter, guard self-test, Leak Check configured, and for a local run: live container health and free memory |
| `live_health() -> HealthReport` | Docker health status of the five live containers; does not contact the application |
| `RunOptions(ci: bool, quiet_confirmed: bool, skip: frozenset[Phase], overall_timeout_s: int)` | A local run needs `quiet_confirmed=True` |
| `main(argv: list[str]) -> int` | Exit 0 success; 1 unexpected test failure or new high/critical finding; 2 harness refused to run |

## C13. Live Exposure Check

| Method | Purpose |
|---|---|
| `LiveGate(allow_paths: frozenset[str], methods: frozenset[str] = {"GET","OPTIONS"}, cap: int = 20)` | The only gate for the live target |
| `LiveGate.send(method: str, path: str) -> Observation` | Raises `GateRefusal` for any other method, path, credential or over the cap |
| `run(target: str) -> ExposureReport` | Target supplied at run time; prints what a neighbour could see |

## Refinements made in Functional Design (U0, 2026-11-22)

Signatures for C8 (Findings Register and Validator) and C10 (Leak Check) were refined when their business rules were
written, as this file's header allows: optional attacker and boundary on `Candidate`, `AddResult` from
`add_candidate`, `confirm` taking the suite index and a `SeverityRating`, `save` taking the leak patterns, the
validator taking patterns, today's date and optional run results, new mutators (`reopen`, `rerate`, `record_triage`,
`mark_fixed`, `reopen_fix`), and the leak check split into `scan_files`, `scan_added_lines` and `scan_text`. No
component, dependency or unit boundary changed. The full table is in
`aidlc-docs/construction/pentest/u0-evidence-core/functional-design/business-logic-model.md` section 8.
