# SPDX-License-Identifier: Apache-2.0
"""Check authored operation exports against the pinned Design scope oracle.

This is an offline producer policy gate, not a runtime authorization engine.
Missing future implementations stay pending; every actual proto method must have
one complete export. Domain exports live in eng/operations/*.json. No generated
client, service, credential or runtime grant is synthesized by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"capability", "risk", "approval", "stepUp", "localPresence", "egress", "patEligible", "actorKinds"}
ROW_REQUIRED = {"operationId", "binding", "kind", "source", "scope", "surface", "profile",
                "sourceRule", "idempotency", "authorization"}
ROW_OPTIONAL = {"delegation", "launchRoles", "requireLaunchRole"}
SCOPES = {"account", "assistant", "product-owner", "resource-owner", "application-target",
          "in-process", "private-helper", "operator", "future"}
ACTORS = {"human", "agent", "automation", "extension", "operator", "service", "provider",
          "preauth", "product-handler", "extension-child", "owning-parent", "helper-parent", "helper-child"}
TOOL_ACTORS = {"agent", "automation", "extension"}
SURFACES = {"public", "in-process", "private-helper", "operator", "cf-internal", "http-exception"}
CLASSES = {"Q", "IW", "CC", "AP", "NI", "EX", "DE"}
PROFILES = {"human-owner", "tool-delegation", "product-handler", "extension-peer", "helper-parent",
            "operator", "cf-service", "provider", "one-use-auth", "delegated-invocation", "launch-bootstrap-only"}
PAT_OPERATIONS = {"workspace.list", "workspace.get", "catalog.search", "catalog.getPackage",
                  "catalog.listVersions", "catalog.submitVersion", "catalog.getSubmission",
                  "resource.beginUpload", "resource.completeUpload", "resource.getUploadStatus",
                  "resource.renewUploadTicket", "support.listCases"}
# These are immutable migration-example identities, not wildcards or production grants.
EXAMPLES = {"arcforges.hello.v1.HelloService/SayHello": "public/proto/arcforges/hello/v1/hello.proto"}
HUMAN_ONLY = {"approval.decide", "IChatOperations.SubmitApproval", "source.createConsent",
              "source.revokeConsent", "source.setPolicy", "source.clearPolicy", "preference.put",
              "connector.beginConnection", "connector.completeConnection", "connector.revokeConnection",
              "support.decideAccess", "device.setRemotePolicy", "device.setTrust", "device.setRemoteEnabled"}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"ambiguous duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    require(isinstance(value, dict), f"object required: {path}")
    return value


def source_path(root: Path, source: str) -> Path:
    require(isinstance(source, str) and bool(source), "missing source path")
    path = (root / source).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), f"invalid source path: {source}")
    return path


def oracle_rows(text: str) -> list[dict]:
    rows = [{"operationId": name, "scope": scope} for name, scope in re.findall(
        r"^\|\s*`([^`]+)`\s*\|\s*([a-z-]+)\s*\|\s*$", text, re.M)]
    require(bool(rows), "empty scope oracle")
    require(len({r["operationId"] for r in rows}) == len(rows), "ambiguous duplicate oracle operation")
    require(all(r["scope"] in SCOPES for r in rows), "unclassified oracle scope")
    return sorted(rows, key=lambda row: row["operationId"])


def proto_methods(root: Path) -> dict[str, str]:
    """Read authored declarations, including streaming/options bodies; never client code."""
    methods = {}
    for base in (root / "public/proto", root / "internal/proto"):
        for path in sorted(base.rglob("*.proto")):
            text = path.read_text(encoding="utf-8")
            text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
            package = re.search(r"\bpackage\s+([\w.]+)\s*;", text)
            for service in re.finditer(r"\bservice\s+(\w+)\s*\{", text):
                require(package is not None, f"service without package: {path}")
                start, depth, end = service.end(), 1, service.end()
                while depth and end < len(text):
                    depth += (text[end] == "{") - (text[end] == "}")
                    end += 1
                require(depth == 0, f"unclosed service declaration: {path}")
                for method in re.finditer(r"\brpc\s+(\w+)\s*\(", text[start:end - 1]):
                    binding = f"{package.group(1)}.{service.group(1)}/{method.group(1)}"
                    require(binding not in methods, f"ambiguous duplicate method: {binding}")
                    methods[binding] = path.relative_to(root).as_posix()
    return methods


def public_imports(root: Path) -> None:
    # The existing compiled package-access gate also enforces dependency closure.
    for path in sorted((root / "public/proto").rglob("*.proto")):
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.S)
        for imported in re.findall(r'\bimport\s+(?:public\s+|weak\s+)?"([^"]+)"', text):
            require(not imported.startswith(("arcforges/local/", "internal/")),
                    f"public import of local schema: {path}: {imported}")


def protected(operation: str) -> bool:
    return (operation in HUMAN_ONLY or operation.startswith(("identity.", "commerce.", "operator.",
            "IConnectorBroker.", "ILocalBootstrap.")))


def authorization(row: dict, tool_allowlist: set[str]) -> tuple[list[str], list[str]]:
    operation = row["operationId"]
    auth = row.get("authorization")
    require(isinstance(auth, dict) and set(auth) == FIELDS, f"{operation}: exactly eight authorization fields required")
    require(row.get("profile") in PROFILES, f"{operation}: unclassified source profile")
    optional = {"delegated-invocation": {"delegation"}, "launch-bootstrap-only": {"launchRoles", "requireLaunchRole"},
                "helper-parent": {"launchRoles"}}.get(row["profile"], set())
    require(set(row) & ROW_OPTIONAL <= optional, f"{operation}: metadata contradicts profile")
    require(isinstance(row.get("sourceRule"), str) and "#" in row["sourceRule"], f"{operation}: missing source rule")
    require(row.get("surface") in SURFACES, f"{operation}: unclassified surface")
    delegated = row["profile"] == "delegated-invocation"
    bootstrap = row["profile"] == "launch-bootstrap-only"
    retry = row.get("idempotency")
    require((delegated and retry == {"from": "admittedCapability.idempotency"}) or
            (not delegated and isinstance(retry, str) and retry in CLASSES), f"{operation}: unclassified idempotency")
    derived = []
    for field, value in auth.items():
        if isinstance(value, dict):
            if bootstrap:
                require(field == "actorKinds" and value == {"from": "verifiedLaunchProfile.actorKinds"},
                        f"{operation}: unsupported bootstrap expression")
                derived.append(field)
                continue
            descriptor_field = "operationId" if field == "capability" else field
            require(row["profile"] == "delegated-invocation" and field != "patEligible"
                    and value == {"from": "admittedCapability." + descriptor_field},
                    f"{operation}: ambiguous or unsupported derived {field}")
            derived.append(field)
    if derived and not bootstrap:
        require(set(derived) == FIELDS - {"patEligible"}, f"{operation}: partial delegated descriptor")
        require(row.get("delegation") == {"intersectOriginalActor": True, "requireCurrentGrant": True,
                "denyHumanOnly": True, "requireLaunchRole": True}, f"{operation}: incomplete delegated authority binding")
        require(row["surface"] in {"private-helper", "in-process"}, f"{operation}: delegated binding exposed publicly")
    for field in ("stepUp", "localPresence", "patEligible"):
        require(field in derived or type(auth[field]) is bool, f"{operation}: ambiguous {field}")
    require("risk" in derived or auth["risk"] in {"R0", "R1", "R2", "R3"}, f"{operation}: unclassified risk")
    for field in ("approval", "egress"):
        require(field in derived or (isinstance(auth[field], str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]*", auth[field])
                and auth[field].lower() not in {"pending", "unknown", "default", "tbd"}), f"{operation}: unclassified {field}")
    require("capability" in derived or auth["capability"] is None or auth["capability"] == operation,
            f"{operation}: capability is not the exact operation ID")
    actors = [] if "actorKinds" in derived else auth["actorKinds"]
    require(isinstance(actors, list) and (bool(actors) or "actorKinds" in derived)
            and all(isinstance(a, str) and a in ACTORS for a in actors)
            and len(actors) == len(set(actors)), f"{operation}: ambiguous actor kinds")
    tools = set(actors) & TOOL_ACTORS
    profile_actors = {"human-owner": {"human"}, "product-handler": {"human", "product-handler"},
                      "tool-delegation": {"human", "agent", "automation", "extension"},
                      "extension-peer": {"extension-child", "owning-parent"},
                      "helper-parent": {"human", "helper-parent", "owning-parent"},
                      "operator": {"operator"}, "cf-service": {"service"},
                      "provider": {"provider"}, "one-use-auth": {"preauth"},
                      "launch-bootstrap-only": set()}
    if row["profile"] in profile_actors:
        require(set(actors) <= profile_actors[row["profile"]], f"{operation}: profile identity mismatch")
    profile_surfaces = {"human-owner": {"public", "in-process", "http-exception"},
                        "tool-delegation": {"public", "in-process"}, "product-handler": {"in-process"},
                        "extension-peer": {"private-helper"}, "helper-parent": {"private-helper"},
                        "operator": {"operator"}, "cf-service": {"cf-internal"},
                        "provider": {"http-exception"}, "one-use-auth": {"public", "http-exception"},
                        "launch-bootstrap-only": {"private-helper"}, "delegated-invocation": {"private-helper"}}
    require(row["surface"] in profile_surfaces[row["profile"]], f"{operation}: profile surface mismatch")
    if row["scope"] in {"private-helper", "in-process"}:
        require(row["surface"] == row["scope"], f"{operation}: scope surface mismatch")
    if row["profile"] == "tool-delegation":
        require(operation in tool_allowlist and auth["capability"] == operation,
                f"{operation}: tool is not explicitly admitted")
    require(auth["capability"] is None or derived or row["profile"] == "tool-delegation",
            f"{operation}: capability outside tool binding")
    if row["surface"] == "public":
        require(row["profile"] in {"human-owner", "tool-delegation", "one-use-auth"},
                f"{operation}: wrong public identity profile")
    if row["surface"] == "operator" or row["scope"] == "operator":
        require(row["surface"] == "operator" and row["scope"] == "operator" and row["profile"] == "operator",
                f"{operation}: operator boundary mismatch")
    if row["surface"] == "private-helper":
        require(row["scope"] == "private-helper" and row["profile"] in
                {"extension-peer", "helper-parent", "launch-bootstrap-only", "delegated-invocation"},
                f"{operation}: helper boundary mismatch")
    require(not (protected(operation) and (tools or ("actorKinds" in derived and not bootstrap))),
            f"{operation}: human-only tool reachability")
    require(not tools or (operation in tool_allowlist and auth["capability"] == operation
            and row["profile"] == "tool-delegation"), f"{operation}: tool is not explicitly admitted")
    if auth["patEligible"]:
        require(operation in PAT_OPERATIONS and row["surface"] == "public" and not tools,
                f"{operation}: forbidden PAT reachability")
    if auth["localPresence"] is True:
        require(row["surface"] not in {"public", "http-exception", "cf-internal"}, f"{operation}: public local-presence binding")
    if row["scope"] == "operator":
        require(actors == ["operator"] and auth["capability"] is None and not auth["patEligible"],
                f"{operation}: wrong operator identity")
    if row["surface"] == "cf-internal":
        require(actors == ["service"] and auth["capability"] is None, f"{operation}: wrong CF service identity")
    if row["surface"] == "private-helper":
        human_parent = (row["profile"] == "helper-parent" and actors == ["human"]
                        and row.get("launchRoles") == ["owning-parent"] and not auth["patEligible"])
        require(human_parent or not set(actors) & {"human", "service", "provider", "preauth", "operator"},
                f"{operation}: helper cannot acquire customer/service authority")
    lifecycle = {"IExtensionHost.Handshake": "extension-child",
                 "IExtensionHost.RenewLease": "extension-child", "IExtensionHost.Stop": "owning-parent"}
    if operation in lifecycle:
        expected = {"capability": None, "risk": "R1", "approval": "none", "stepUp": False,
                    "localPresence": False, "egress": "none", "patEligible": False,
                    "actorKinds": [lifecycle[operation]]}
        require(auth == expected and row["profile"] == "extension-peer" and row["idempotency"] == "IW",
                f"{operation}: lifecycle metadata disagrees with source profile")
    if row["profile"] == "delegated-invocation":
        require(operation == "IExtensionHost.Invoke" and bool(derived) and auth["patEligible"] is False,
                f"{operation}: delegated profile outside admitted Invoke")
    if bootstrap:
        expected = {"capability": None, "risk": "R1", "approval": "none", "stepUp": False,
                    "localPresence": False, "egress": "none", "patEligible": False,
                    "actorKinds": {"from": "verifiedLaunchProfile.actorKinds"}}
        retry_classes = {"ILocalBootstrap.Challenge": "NI", "ILocalBootstrap.Confirm": "NI",
                         "ILocalBootstrap.Renew": "IW"}
        require(operation in retry_classes and auth == expected and retry == retry_classes[operation]
                and row.get("launchRoles") == {"from": "verifiedLaunchProfile.callerRoles"}
                and row.get("requireLaunchRole") is True, f"{operation}: incomplete bootstrap authority binding")
    return sorted(actors), sorted(derived)


def audit(root: Path, manifest: dict | None = None) -> dict:
    root = root.resolve()
    manifest = manifest if manifest is not None else load(root / "eng/operation-scope-manifest.json")
    require(manifest.get("schemaVersion") == "operation-scope.v1", "unsupported scope manifest")
    oracle = {}
    require(isinstance(manifest.get("operations"), list), "oracle operation list required")
    for row in manifest.get("operations", []):
        require(isinstance(row, dict), "oracle row object required")
        operation, scope = row.get("operationId"), row.get("scope")
        require(isinstance(operation, str) and bool(operation) and scope in SCOPES, "unclassified oracle row")
        require(operation not in oracle, f"ambiguous oracle row: {operation}")
        oracle[operation] = scope
    require(bool(oracle), "empty scope oracle")
    require(isinstance(manifest.get("idempotencyExamples"), list), "idempotency examples list required")
    for example in manifest.get("idempotencyExamples", []):
        require(isinstance(example, str), "idempotency example ID required")
        require(example in oracle and oracle[example] != "future", f"nonexistent idempotency example: {example}")
    allowed = manifest.get("toolAllowlist", [])
    require(isinstance(allowed, list) and all(isinstance(op, str) for op in allowed), "tool allowlist IDs required")
    tool_allowlist = set(allowed)
    require(all(op in oracle and oracle[op] != "future" and not protected(op) for op in tool_allowlist),
            "forbidden or unclassified tool allowlist operation")
    public_imports(root)
    methods = proto_methods(root)
    exported, bindings = {}, set()
    for path in sorted((root / "eng/operations").glob("*.json")):
        document = load(path)
        require(document.get("schemaVersion") == "operation-metadata.v1", f"unsupported operation export: {path}")
        require(isinstance(document.get("operations"), list), f"operation list required: {path}")
        for row in document["operations"]:
            require(isinstance(row, dict), f"operation row object required: {path}")
            require(ROW_REQUIRED <= set(row) <= ROW_REQUIRED | ROW_OPTIONAL,
                    f"missing or unknown operation export fields: {path}")
            operation = row.get("operationId")
            require(isinstance(operation, str), "operation ID required")
            require(operation in oracle, f"unclassified operation: {operation}")
            require(oracle[operation] != "future", f"reserved future operation registered: {operation}")
            require(operation not in exported, f"ambiguous duplicate export: {operation}")
            require(row.get("scope") == oracle[operation], f"{operation}: scope disagrees with oracle")
            binding = row.get("binding")
            require(isinstance(binding, str) and bool(binding) and binding not in bindings, f"ambiguous binding: {binding}")
            source = row.get("source")
            source_path(root, source)
            if row.get("kind") == "proto":
                require(methods.get(binding) == source, f"{operation}: nonexistent service method/source {binding}")
            else:
                require(row.get("kind") in {"http", "in-process"}, f"{operation}: unknown binding kind")
                require(row.get("surface") in ({"http-exception", "cf-internal"} if row["kind"] == "http" else {"in-process"}),
                        f"{operation}: binding surface mismatch")
            actors, derived = authorization(row, tool_allowlist)
            bindings.add(binding)
            exported[operation] = {**row, "reachableActors": actors, "derivedFields": derived,
                                   "metadataSource": path.relative_to(root).as_posix()}
    examples = []
    for binding, source in methods.items():
        if EXAMPLES.get(binding) == source:
            require(binding not in bindings, f"migration example exported as production: {binding}")
            examples.append(binding)
        else:
            require(binding in bindings, f"unclassified registered method: {binding}")
    matrix = []
    for operation in sorted(oracle):
        matrix.append({"operationId": operation, "scope": oracle[operation],
                       "status": "registered" if operation in exported else "reserved" if oracle[operation] == "future" else "pending",
                       **exported.get(operation, {})})
    return {"schemaVersion": "operation-reachability.v1", "result": "passed", "oracle": manifest.get("oracle"),
            "registered": len(exported), "pending": sum(r["status"] == "pending" for r in matrix),
            "reserved": sum(r["status"] == "reserved" for r in matrix), "migrationExamples": sorted(examples),
            "operations": matrix, "coverage": "offline metadata policy only; no runtime authorization acceptance"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--oracle", type=Path, help="Check pinned rows against the supplied authoritative manifest11")
    args = parser.parse_args()
    try:
        manifest = load(args.root / "eng/operation-scope-manifest.json")
        if args.oracle:
            data = args.oracle.read_text(encoding="utf-8").encode("utf-8")
            require(hashlib.sha256(data).hexdigest() == manifest["oracle"]["sha256"], "scope oracle source digest changed")
            require(oracle_rows(data.decode("utf-8")) == manifest["operations"], "scope oracle rows drifted")
        report = audit(args.root, manifest)
        output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(output, encoding="utf-8")
        print(f"Operation scope passed: {report['registered']} registered, {report['pending']} pending, {report['reserved']} reserved")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Operation scope failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
