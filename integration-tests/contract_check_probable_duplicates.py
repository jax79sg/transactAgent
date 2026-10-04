"""Frontend <-> API contract check for Epic 14 (run with any venv that has the API installed: python integration-tests/contract_check_probable_duplicates.py).
Compares, for every DTO the frontend declares for the duplicates feature:
  - the set of JSON field names (API OpenAPI schema vs TypeScript interface),
  - required vs optional/nullable,
  - string-literal enums,
and the route paths/methods the frontend calls vs the routes the API serves."""
import os, re, sys, json, pathlib
for n, v in (("DB_USER","t"),("DB_PASSWORD","t"),("JWT_SECRET","s"),("GOOGLE_OAUTH_CLIENT_ID","x"),("GOOGLE_OAUTH_CLIENT_SECRET","x"),("GEMINI_API_KEY","x")):
    os.environ.setdefault(n, v)
from api_service.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]
FE = pathlib.Path(os.environ.get("FE_SRC", ROOT / "frontend" / "src"))  # FE_SRC: point at a mutated copy to prove the check can fail
spec = app.openapi()
schemas = spec["components"]["schemas"]

# ---------- parse TS interfaces ----------
ts = (FE / "api/types.ts").read_text()
ts = re.sub(r"//[^\n]*", "", ts)
ts = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)
interfaces = {}
for m in re.finditer(r"export interface (\w+)\s*\{(.*?)\n\}", ts, flags=re.S):
    fields = {}
    for fm in re.finditer(r"^\s*(\w+)(\?)?:\s*([^;]+);", m.group(2), flags=re.M):
        fields[fm.group(1)] = {"optional": bool(fm.group(2)), "type": fm.group(3).strip()}
    interfaces[m.group(1)] = fields
aliases = {m.group(1): m.group(2).strip() for m in re.finditer(r"export type (\w+)\s*=\s*([^;]+);", ts)}

def literals(t):
    t = aliases.get(t, t)
    parts = [p.strip() for p in t.split("|")]
    return {p.strip('"') for p in parts if p.startswith('"')}

PAIRS = {  # API schema -> TS interface
    "StatementLabelDTO": "StatementLabel", "RemovalPreviewDTO": "RemovalPreview", "RemovalStatusDTO": "RemovalStatus",
    "PairDTO": "DuplicatePair", "PairPage": "DuplicatePairPage", "PendingPairCountResponse": "PendingPairCountResponse",
    "RemovalRequest": "RemovalRequest", "ComparisonRowDTO": "ComparisonRow", "ComparisonSideDTO": "ComparisonSide",
    "ComparisonDTO": "DuplicateComparison", "OverrideResponse": "OverrideResponse", "ScanStatusDTO": "ScanStatus",
    "RunFileDetail": "RunFileDetail", "SettingDTO": "SettingDTO",
}

def resolve(prop):
    """(types:set[str], enum:set|None) for an OpenAPI property, following anyOf/$ref/arrays one level."""
    enum = set(prop.get("enum", [])) or None
    types = set()
    for alt in prop.get("anyOf", [prop]):
        if "$ref" in alt:
            ref = schemas[alt["$ref"].split("/")[-1]]
            enum = enum or (set(ref["enum"]) if "enum" in ref else None)
            types.add("enum" if "enum" in ref else "object:" + alt["$ref"].split("/")[-1])
        else:
            types.add(alt.get("type", "?"))
            if "enum" in alt: enum = set(alt["enum"])
    return types, enum

problems, checked = [], 0
for api_name, ts_name in PAIRS.items():
    if api_name not in schemas: problems.append(f"API schema {api_name} not found"); continue
    if ts_name not in interfaces: problems.append(f"TS interface {ts_name} not found"); continue
    api, fe = schemas[api_name], interfaces[ts_name]
    props, required = api.get("properties", {}), set(api.get("required", []))
    for name in sorted(set(props) | set(fe)):
        checked += 1
        if name not in fe:
            problems.append(f"{ts_name}.{name}: sent by the API, not declared in the frontend (harmless but unread)") if name not in () else None
            continue
        if name not in props:
            problems.append(f"{ts_name}.{name}: declared in the frontend, NEVER sent by the API"); continue
        types, enum = resolve(props[name])
        fe_optional, fe_type = fe[name]["optional"], fe[name]["type"]
        api_nullable = "null" in types
        fe_nullable = "null" in [p.strip() for p in fe_type.split("|")]
        if name not in required and not fe_optional and not fe_nullable and not api_nullable and props[name].get("default") is None:
            problems.append(f"{ts_name}.{name}: API may omit it but the frontend requires it")
        if api_nullable and not (fe_nullable or fe_optional):
            problems.append(f"{ts_name}.{name}: API may send null but the frontend type does not allow null")
        if enum and literals(fe_type) and enum != literals(fe_type):
            problems.append(f"{ts_name}.{name}: enum mismatch API={sorted(enum)} FE={sorted(literals(fe_type))}")
        if enum and not literals(fe_type) and fe_type.split("|")[0].strip() in ("string",):
            problems.append(f"{ts_name}.{name}: API has an enum {sorted(enum)}, frontend types it as plain string (weaker, not wrong)")


# ---------- enum values: the OpenAPI schema types these as plain strings, so compare with the real sources ----------
import ast
from transactagent_db import models as M
svc = ROOT / "api-service" / "src" / "api_service" / "duplicates" / "service.py"
tree = ast.parse(svc.read_text())
state_fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in ("get_comparison", "_overridden_state")]
state_consts = {c.value for fn in state_fns for c in ast.walk(fn)
                if isinstance(c, ast.Constant) and isinstance(c.value, str) and re.fullmatch(r"[a-z_]+", c.value)} - {"earlier", "later"}
def vals(e): return {x.value for x in e}
ENUMS = [  # (TS interface, field, expected set, where it comes from)
    ("DuplicatePair", "status", vals(M.DuplicatePairStatus), "database DuplicatePairStatus"),
    ("RemovalStatus", "status", vals(M.StatementRemovalJobStatus), "database StatementRemovalJobStatus"),
    ("ComparisonRow", "marker", vals(M.ComparisonRowMarker), "database ComparisonRowMarker"),
    ("DuplicateComparison", "thisFileSide", vals(M.ComparisonSide), "database ComparisonSide"),
    ("DuplicateComparison", "state", state_consts, "string constants in duplicates/service.py get_comparison/_overridden_state"),
    ("RunFileDetail", "outcome", vals(M.IngestionRunFileOutcome), "database IngestionRunFileOutcome"),
]
for iface, field, expected, source in ENUMS:
    checked += 1
    got = literals(interfaces[iface][field]["type"].replace("| null", "").strip())
    if got != expected:
        problems.append(f"{iface}.{field}: frontend {sorted(got)} != {source} {sorted(expected)}")
# the override response's two states must be a subset of the comparison states the service can produce
ov = literals(interfaces["OverrideResponse"]["state"]["type"])
if not ov <= state_consts:
    problems.append(f"OverrideResponse.state {sorted(ov)} not all produced by the service {sorted(state_consts)}")
print("enum sets compared:", [f"{i}.{f}={len(e)}" for i, f, e, _ in ENUMS])

# ---------- routes: every call in frontend/src/api/duplicates.ts must hit a route the API serves, and vice versa ----------
def norm(path):
    return re.sub(r"\$\{[^}]+\}|\{[^}]+\}", "{}", path)

api_routes = {(m.upper(), norm(p)) for p, ops in spec["paths"].items() if p.startswith("/duplicates") for m in ops}
src = (FE / "api/duplicates.ts").read_text()
fe_routes = set()
for call in re.finditer(r"apiRequest<[^>]+>\((.*?)\);", src, flags=re.S):
    body = call.group(1)
    path = re.search(r"[`\"]([^`\"]+)[`\"]", body).group(1)
    method = re.search(r'method:\s*"(\w+)"', body)
    fe_routes.add(((method.group(1) if method else "GET").upper(), norm(path)))
checked += len(fe_routes)
for r in sorted(fe_routes - api_routes): problems.append(f"frontend calls {r}, which the API does not serve")
for r in sorted(api_routes - fe_routes): problems.append(f"API serves {r}, which the frontend never calls")
print(f"routes compared: {len(fe_routes)} frontend / {len(api_routes)} API")

print("fields, enums and routes compared:", checked)
print("PROBLEMS:" if problems else "no problems")
for p in problems: print(" -", p)
sys.exit(1 if problems else 0)
