# Cross-service checks (Epic 14, Probable Duplicate Statement Detection)

Each service's own suite fakes the other side. These two checks need the Ingestion Worker, the API Service and the
frontend's types at once, so they live here rather than in any one service. Neither touches the live stack:
the scenario starts its own throwaway PostgreSQL (testcontainers; needs Docker running), and the contract check only
reads code.

## One-time setup (a scratch virtual environment holding all three Python packages)

```bash
python3.12 -m venv /tmp/xvenv
/tmp/xvenv/bin/pip install -e ./database -e "./ingestion-worker[test]" -e "./api-service[test]"
```

## 1. Cross-service scenario

```bash
/tmp/xvenv/bin/python -m pytest integration-tests -q
```

One test, through the real code of both services against one real PostgreSQL (only Drive, extraction and the
vector store are faked): two downloads of one statement are ingested; the **worker** detects the pair; the **API**
lists it, refuses a stale or wrong confirmation, and queues a removal; the **worker** executes it; the **API** reports
it removed; the next ingestion run recognises the removed copy's file without reading it and the API shows
"probable duplicate of ..."; the user overrides, the worker re-ingests it, and the scan never proposes it again.

It reuses the worker's own `_run` helper from `ingestion-worker/tests/test_duplicates_end_to_end.py`, so it breaks if that
helper is renamed.

## 2. Frontend <-> API contract check

```bash
/tmp/xvenv/bin/python integration-tests/contract_check_probable_duplicates.py
```

Compares what the API actually sends with what `frontend/src/api/types.ts` and `frontend/src/api/duplicates.ts`
declare: field names, required/nullable, enumerated values (against the database enums and the service's state
strings, since the OpenAPI schema types those as plain strings), and all eight routes with their methods. Exits 1 and
lists every mismatch. `FE_SRC=<dir>` points it at a modified copy of `frontend/src`, which is how it was shown to fail
on a renamed field, enum typos and wrong routes.
