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
CON08_EXPORT = "eng/operations/con-08.json"
CON08_OPERATIONS = frozenset({
    "entitlement.getSnapshot", "entitlement.getServiceTerm", "entitlement.getCapacity",
    "entitlement.listGrants", "entitlement.getUsage", "entitlement.check",
    "commerce.authoriseExtraUsage", "commerce.revokeExtraUsage", "commerce.explainCharge",
    "commerce.getCatalogue", "commerce.createPurchaseIntent", "commerce.createCheckoutAttempt",
    "commerce.getPurchaseState", "commerce.getSubscription", "commerce.cancelSubscription",
    "commerce.reactivateSubscription", "commerce.getCredits", "commerce.listBillingHistory",
    "commerce.requestRefund", "commerce.exportEvidence",
})
SCOPES = {"account", "assistant", "product-owner", "resource-owner", "application-target",
          "in-process", "private-helper", "operator", "future"}
ACTORS = {"human", "agent", "automation", "extension", "operator", "service", "provider",
          "preauth", "product-handler", "extension-child", "owning-parent", "helper-parent", "helper-child"}
TOOL_ACTORS = {"agent", "automation", "extension"}
SURFACES = {"public", "in-process", "private-helper", "operator", "cf-internal", "http-exception"}
CLASSES = {"Q", "IW", "CC", "AP", "NI", "EX", "DE"}
CF_SERVICE_OPERATIONS = {
    "cf.ai.authorize": ("resource-owner", "authorize", "Q"),
    "cf.ai.claim": ("assistant", "claim", "IW"),
    "cf.ai.renew": ("assistant", "renew", "IW"),
    "cf.ai.reconcile": ("assistant", "reconcile", "Q"),
    "cf.ai.context": ("assistant", "context", "Q"),
    "cf.ai.model-intent": ("assistant", "model-intent", "IW"),
    "cf.ai.model-outcome": ("assistant", "model-outcome", "IW"),
    "cf.ai.settle": ("assistant", "settle", "IW"),
    "cf.ai.prepare-tools": ("assistant", "prepare-tools", "IW"),
    "cf.ai.cloud-tool": ("assistant", "cloud-tool", "IW"),
    "cf.ai.wait": ("assistant", "wait", "IW"),
    "cf.ai.finalize": ("assistant", "finalize", "IW"),
    "cf.ai.stream-state": ("assistant", "stream-state", "IW"),
    "cf.ai.late-outcome": ("assistant", "late-outcome", "IW"),
}
# CON.15's 17 private Cloudflare routes are exact literal tuples from the pinned manifest11 route table:
# (scope, method and path, idempotency, authored source, source rule). There is no route template, and
# the public session-ticket GET/PUT object routes are deliberately not cf-service operations.
CON15_CF_SOURCE = "internal/cf-http/v1/schema.json"
CON15_RULE_PORTS = "docs/architecture/contracts/05-cloudflare-integration.md#3-exact-internal-ports"
CON15_RULE_OBJECTS = "docs/architecture/contracts/05-cloudflare-integration.md#9-job-authorized-objects-control-inventory-and-resource-budgets"
CON15_RULE_WEB_SEARCH = "docs/architecture/contracts/05-cloudflare-integration.md#execution-owner-and-web-search-additions"
CON15_RULE_INFERENCE = "docs/architecture/contracts/05-cloudflare-integration.md#8-session-bindings-inference-jobs-and-deployment-transitions"
CON15_CF_SERVICE_OPERATIONS = {
    "cf.objects.authorize": ("resource-owner", "POST /internal/objects/v1/authorize", "Q", CON15_CF_SOURCE, CON15_RULE_PORTS),
    "cf.objects.part-receipt": ("resource-owner", "POST /internal/objects/v1/part-receipt", "IW", CON15_CF_SOURCE, CON15_RULE_PORTS),
    "cf.objects.verification": ("resource-owner", "POST /internal/objects/v1/verification", "IW", CON15_CF_SOURCE, CON15_RULE_PORTS),
    "cf.objects.job-grant": ("resource-owner", "POST /internal/objects/v1/job-grant", "IW", CON15_CF_SOURCE, CON15_RULE_OBJECTS),
    "cf.objects.job-authorize": ("resource-owner", "POST /internal/objects/v1/job-authorize", "Q", CON15_CF_SOURCE, CON15_RULE_OBJECTS),
    "cf.objects.job-read": ("resource-owner", "GET /internal/objects/v1/jobs/{grantId}", "Q", CON15_CF_SOURCE, CON15_RULE_OBJECTS),
    "cf.objects.job-write": ("resource-owner", "PUT /internal/objects/v1/jobs/{grantId}", "IW", CON15_CF_SOURCE, CON15_RULE_OBJECTS),
    "cf.ai.dispatch": ("assistant", "POST /internal/ai/v1/dispatch", "IW", CON15_CF_SOURCE, CON15_RULE_PORTS),
    "cf.ai.control": ("assistant", "POST /internal/ai/v1/control", "IW", CON15_CF_SOURCE, CON15_RULE_PORTS),
    "cf.ai.delete": ("account", "POST /internal/ai/v1/delete", "IW", CON15_CF_SOURCE, CON15_RULE_PORTS),
    "cf.ai.web-search": ("assistant", "POST /internal/ai/v1/web-search", "IW", CON15_CF_SOURCE, CON15_RULE_WEB_SEARCH),
    "cf.ai.inference-job": ("resource-owner", "POST /internal/ai/v1/inference-job", "IW", CON15_CF_SOURCE, CON15_RULE_INFERENCE),
    "cf.ai.inference-lease": ("resource-owner", "POST /internal/ai/v1/inference-lease", "IW", CON15_CF_SOURCE, CON15_RULE_INFERENCE),
    "cf.ai.inference-input": ("resource-owner", "POST /internal/ai/v1/inference-input", "Q", CON15_CF_SOURCE, CON15_RULE_INFERENCE),
    "cf.ai.inference-outcome": ("resource-owner", "POST /internal/ai/v1/inference-outcome", "IW", CON15_CF_SOURCE, CON15_RULE_INFERENCE),
    "cf.ai.inference-late-outcome": ("resource-owner", "POST /internal/ai/v1/inference-late-outcome", "IW", CON15_CF_SOURCE, CON15_RULE_INFERENCE),
    "cf.ai.inference-state": ("resource-owner", "POST /internal/ai/v1/inference-state", "Q", CON15_CF_SOURCE, CON15_RULE_INFERENCE),
}
TASK_CREATE_BINDING = "arcforges.publicapi.v1.TaskService/Create"
TASK_CREATE_SOURCE = "public/proto/arcforges/publicapi/v1/chat.proto"
TASK_CREATE_SOURCE_RULE = "docs/architecture/contracts/01-public-api-operations.md#7-task-approval-and-remote-work"
# CON.07: the only two registry operations whose catalogue risk is R4. Both are step-up,
# human-only account commands in the public identity proto; no other R4 row is admitted here.
CON07_IDENTITY_SOURCE = "public/proto/arcforges/publicapi/v1/identity.proto"
CON07_R4_OPERATIONS = {
    "identity.requestAccountDeletion": ("arcforges.publicapi.v1.IdentityService/RequestAccountDeletion", "IW"),
    "workspace.requestDataDeletion": ("arcforges.publicapi.v1.WorkspaceService/RequestDataDeletion", "CC"),
}
PROFILES = {"human-owner", "tool-delegation", "product-handler", "extension-peer", "helper-parent",
            "operator", "cf-service", "provider", "one-use-auth", "delegated-invocation", "launch-bootstrap-only",
            "in-process-invocation", "human-approval-decision", "public-human-approval-decision"}
PAT_OPERATIONS = {"workspace.list", "workspace.get", "catalog.search", "catalog.getPackage",
                  "catalog.listVersions", "catalog.submitVersion", "catalog.getSubmission",
                  "resource.beginUpload", "resource.completeUpload", "resource.getUploadStatus",
                  "resource.renewUploadTicket", "support.listCases"}
# These are immutable migration-example identities, not wildcards or production grants.
EXAMPLES = {"arcforges.hello.v1.HelloService/SayHello": "public/proto/arcforges/hello/v1/hello.proto"}
# CON.11's private RunStream binding is a schema projection for an already
# authenticated attempt, not a caller operation. Keep this one exact exception
# tied to its authored source and independent RPC fixture; do not generalize it.
CON11_EXPORT = "eng/operations/con-11.json"
CON11_PRIVATE_RUN_STREAM = {
    "binding": "arcforges.cf.v1.RunStreamService/Run",
    "source": "internal/proto/arcforges/cf/v1/stream.proto",
    "fixture": "fixtures/internal/con-11-run-stream.json",
    "rpcVector": {
        "id": "cloudinternal.run-stream.run",
        "service": "arcforges.cf.v1.RunStreamService",
        "method": "Run",
        "input": "RunStreamRequest",
        "output": "arcforges.events.v1.StreamFrame",
        "streamType": "serverStreaming",
        "requestFields": [["execution", 1], ["attemptId", 2], ["generation", 3]],
    },
}
OPERATOR_BREAK_GLASS_BINDING = ("operator.startBreakGlass", "arcforges.operator.v1.OperatorService/StartBreakGlass",
                                "internal/proto/arcforges/operator/v1/operator.proto")
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


def validate_compatibility_class(export_path: str, row: dict) -> None:
    """Allow frozen metadata only on CON.08's exact export and owned operations."""
    operation = row.get("operationId")
    has_class = "compatibilityClass" in row
    if export_path == CON08_EXPORT:
        require(operation in CON08_OPERATIONS, f"unowned operation in CON.08 export: {operation}")
        require(has_class and row["compatibilityClass"] == "frozen",
                f"{operation}: CON.08 compatibilityClass must be literal frozen")
    else:
        require(not has_class, f"compatibilityClass is permitted only in {CON08_EXPORT}")


def validate_operation_export_fields(export_path: str, row: dict) -> None:
    validate_compatibility_class(export_path, row)
    allowed_fields = ROW_REQUIRED | ROW_OPTIONAL
    if export_path == CON08_EXPORT:
        allowed_fields |= {"compatibilityClass"}
    require(ROW_REQUIRED <= set(row) <= allowed_fields,
            f"missing or unknown operation export fields: {export_path}")


def oracle_rows(text: str) -> list[dict]:
    rows = [{"operationId": name, "scope": scope} for name, scope in re.findall(
        r"^\|\s*`([^`]+)`\s*\|\s*([a-z-]+)\s*\|\s*$", text, re.M)]
    require(bool(rows), "empty scope oracle")
    require(len({r["operationId"] for r in rows}) == len(rows), "ambiguous duplicate oracle operation")
    require(all(r["scope"] in SCOPES for r in rows), "unclassified oracle scope")
    return sorted(rows, key=lambda row: row["operationId"])


def proto_text(text: str, *, keep_strings: bool = False) -> str:
    # Lex strings together with comments: braces/rpc text inside option strings
    # must not end a service early or invent a declaration.
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*'
    return re.sub(tokens, lambda match: match.group() if keep_strings and
                  match.group().startswith(('"', "'")) else " ", text, flags=re.S)


def proto_methods(root: Path) -> dict[str, str]:
    """Read authored declarations, including streaming/options bodies; never client code."""
    methods = {}
    for base in (root / "public/proto", root / "internal/proto"):
        for path in sorted(base.rglob("*.proto")):
            text = path.read_text(encoding="utf-8")
            text = proto_text(text)
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


def private_service_projections(root: Path, methods: dict[str, str], bindings: set[str]) -> list[dict]:
    """Validate and separately report CON.11's one closed private schema projection."""
    # Small isolated unit-test roots do not contain the CON.11 domain export.
    # In the real Contracts tree that export makes the projection mandatory,
    # even if its proto or fixture is accidentally removed.
    if not (root / CON11_EXPORT).is_file():
        return []

    binding = CON11_PRIVATE_RUN_STREAM["binding"]
    source = CON11_PRIVATE_RUN_STREAM["source"]
    require(methods.get(binding) == source,
            "CON.11 private RunStream projection has a missing or wrong source binding")
    require(binding not in bindings,
            "CON.11 private RunStream projection must not have an operation export")

    fixture_path = source_path(root, CON11_PRIVATE_RUN_STREAM["fixture"])
    fixture = load(fixture_path)
    require(fixture.get("schemaVersion") == "con-11-run-stream.v1",
            "CON.11 private RunStream fixture identity mismatch")
    require(fixture.get("rpcVectors") == [CON11_PRIVATE_RUN_STREAM["rpcVector"]],
            "CON.11 private RunStream fixture RPC vector mismatch")
    return [{"binding": binding, "source": source,
             "fixture": CON11_PRIVATE_RUN_STREAM["fixture"],
             "rpcVectorId": CON11_PRIVATE_RUN_STREAM["rpcVector"]["id"]}]


def public_imports(root: Path) -> None:
    # The existing compiled package-access gate also enforces dependency closure.
    for path in sorted((root / "public/proto").rglob("*.proto")):
        text = proto_text(path.read_text(encoding="utf-8"), keep_strings=True)
        for _, imported in re.findall(r'''\bimport\s+(?:public\s+|weak\s+)?(["'])([^"']+)["']''', text):
            require(not imported.startswith(("arcforges/local/", "internal/")),
                    f"public import of local schema: {path}: {imported}")


def protected(operation: str) -> bool:
    return (operation in HUMAN_ONLY or operation.startswith(("identity.", "commerce.", "operator.",
            "IConnectorBroker.", "ILocalBootstrap.")))


def authorization(row: dict, tool_allowlist: set[str]) -> tuple[list[str], list[str]]:
    operation = row["operationId"]
    required_profile = {"ICapabilityProvider.Invoke": "in-process-invocation",
                        "IChatOperations.SubmitApproval": "human-approval-decision",
                        "approval.decide": "public-human-approval-decision"}.get(operation)
    require(required_profile is None or row.get("profile") == required_profile,
            f"{operation}: required closed authorization profile")
    auth = row.get("authorization")
    require(isinstance(auth, dict) and set(auth) == FIELDS, f"{operation}: exactly eight authorization fields required")
    require(row.get("profile") in PROFILES, f"{operation}: unclassified source profile")
    optional = {"delegated-invocation": {"delegation"}, "in-process-invocation": {"delegation"},
                "launch-bootstrap-only": {"launchRoles", "requireLaunchRole"},
                "helper-parent": {"launchRoles"}}.get(row["profile"], set())
    require(set(row) & ROW_OPTIONAL <= optional, f"{operation}: metadata contradicts profile")
    require(isinstance(row.get("sourceRule"), str) and "#" in row["sourceRule"], f"{operation}: missing source rule")
    require(row.get("surface") in SURFACES, f"{operation}: unclassified surface")
    delegated = row["profile"] in {"delegated-invocation", "in-process-invocation"}
    approval_decision = row["profile"] in {"human-approval-decision", "public-human-approval-decision"}
    bootstrap = row["profile"] == "launch-bootstrap-only"
    retry = row.get("idempotency")
    require((delegated and retry == {"from": "admittedCapability.idempotency"}) or
            (not delegated and isinstance(retry, str) and retry in CLASSES), f"{operation}: unclassified idempotency")
    derived = []
    for field, value in auth.items():
        if isinstance(value, dict):
            if approval_decision:
                proposal_field = "effectiveRisk" if field == "risk" else field
                require(field in {"risk", "stepUp", "localPresence"} and
                        value == {"from": "verifiedApprovalProposal." + proposal_field},
                        f"{operation}: unsupported approval proposal expression")
                derived.append(field)
                continue
            if bootstrap:
                require(field == "actorKinds" and value == {"from": "verifiedLaunchProfile.actorKinds"},
                        f"{operation}: unsupported bootstrap expression")
                derived.append(field)
                continue
            descriptor_field = "operationId" if field == "capability" else field
            require(delegated and field != "patEligible"
                    and value == {"from": "admittedCapability." + descriptor_field},
                    f"{operation}: ambiguous or unsupported derived {field}")
            derived.append(field)
    if derived and not bootstrap and not approval_decision:
        require(set(derived) == FIELDS - {"patEligible"}, f"{operation}: partial delegated descriptor")
        handler_guard = "requireRegisteredProductHandler" if row["profile"] == "in-process-invocation" else "requireLaunchRole"
        require(row.get("delegation") == {"intersectOriginalActor": True, "requireCurrentGrant": True,
                "denyHumanOnly": True, handler_guard: True}, f"{operation}: incomplete delegated authority binding")
        if row["profile"] == "in-process-invocation":
            require(all(value is True for value in row["delegation"].values()),
                    f"{operation}: incomplete delegated boolean authority binding")
        require(row["surface"] in {"private-helper", "in-process"}, f"{operation}: delegated binding exposed publicly")
    for field in ("stepUp", "localPresence", "patEligible"):
        require(field in derived or type(auth[field]) is bool, f"{operation}: ambiguous {field}")
    task_create_r2plus = (
        operation == "task.create" and row["binding"] == TASK_CREATE_BINDING and row["kind"] == "proto" and
        row["source"] == TASK_CREATE_SOURCE and row["scope"] == "assistant" and row["surface"] == "public" and
        row["profile"] == "human-owner" and row["sourceRule"] == TASK_CREATE_SOURCE_RULE and
        row["idempotency"] == "CC" and auth["risk"] == "R2+" and auth["actorKinds"] == ["human"]
    )
    # Registry04 9.1 assigns the SE-only incident-bound break-glass start R4. This closed exception
    # is exact: no other operator or public operation may use R4.
    operator_break_glass_r4 = (
        operation == OPERATOR_BREAK_GLASS_BINDING[0] and auth["risk"] == "R4" and
        row["binding"] == OPERATOR_BREAK_GLASS_BINDING[1] and row["kind"] == "proto" and
        row["source"] == OPERATOR_BREAK_GLASS_BINDING[2] and row["scope"] == "operator" and
        row["surface"] == "operator" and row["profile"] == "operator" and row["idempotency"] == "CC" and
        auth["actorKinds"] == ["operator"] and auth["localPresence"] is False and auth["stepUp"] is True
    )
    con07_r4 = (
        operation in CON07_R4_OPERATIONS and auth["risk"] == "R4" and row["kind"] == "proto" and
        row["source"] == CON07_IDENTITY_SOURCE and row["scope"] == "account" and row["surface"] == "public" and
        row["profile"] == "human-owner" and
        (row["binding"], row["idempotency"]) == CON07_R4_OPERATIONS[operation] and
        auth["stepUp"] is True and auth["actorKinds"] == ["human"] and auth["patEligible"] is False
    )
    require("risk" in derived or auth["risk"] in {"R0", "R1", "R2", "R3"} or task_create_r2plus or
            operator_break_glass_r4 or con07_r4, f"{operation}: unclassified risk")
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
                      "launch-bootstrap-only": set(), "human-approval-decision": {"human"},
                      "public-human-approval-decision": {"human"}}
    if row["profile"] in profile_actors:
        require(set(actors) <= profile_actors[row["profile"]], f"{operation}: profile identity mismatch")
    profile_surfaces = {"human-owner": {"public", "in-process", "http-exception"},
                        "tool-delegation": {"public", "in-process"}, "product-handler": {"in-process"},
                        "extension-peer": {"private-helper"}, "helper-parent": {"private-helper"},
                        "operator": {"operator"}, "cf-service": {"cf-internal"},
                        "provider": {"http-exception"}, "one-use-auth": {"public", "http-exception"},
                        "launch-bootstrap-only": {"private-helper"}, "delegated-invocation": {"private-helper"},
                        "in-process-invocation": {"in-process"}, "human-approval-decision": {"in-process"},
                        "public-human-approval-decision": {"public"}}
    require(row["surface"] in profile_surfaces[row["profile"]], f"{operation}: profile surface mismatch")
    if row["scope"] in {"private-helper", "in-process"}:
        require(row["surface"] == row["scope"], f"{operation}: scope surface mismatch")
    if row["profile"] == "tool-delegation":
        require(operation in tool_allowlist and auth["capability"] == operation,
                f"{operation}: tool is not explicitly admitted")
    require(auth["capability"] is None or derived or row["profile"] == "tool-delegation",
            f"{operation}: capability outside tool binding")
    if row["surface"] == "public":
        require(row["profile"] in {"human-owner", "tool-delegation", "one-use-auth", "public-human-approval-decision"},
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
    if operation in CF_SERVICE_OPERATIONS or operation in CON15_CF_SERVICE_OPERATIONS or row["profile"] == "cf-service":
        require(operation in CF_SERVICE_OPERATIONS or operation in CON15_CF_SERVICE_OPERATIONS,
                f"{operation}: unregistered CF service operation")
        expected = {"capability": None, "risk": "R1", "approval": "none", "stepUp": False,
                    "localPresence": False, "egress": "none", "patEligible": False,
                    "actorKinds": ["service"]}
        if operation in CF_SERVICE_OPERATIONS:
            scope, route, idempotency = CF_SERVICE_OPERATIONS[operation]
            binding, source, source_rule = (f"POST /internal/ai/v1/{route}", "internal/ai-http/v1/schema.json",
                                            "docs/architecture/contracts/05-cloudflare-integration.md#3-exact-internal-ports")
        else:
            scope, binding, idempotency, source, source_rule = CON15_CF_SERVICE_OPERATIONS[operation]
        require(row["kind"] == "http" and row["scope"] == scope and
                row["surface"] == "cf-internal" and row["profile"] == "cf-service" and
                row["binding"] == binding and row["source"] == source and
                row["sourceRule"] == source_rule and
                row["idempotency"] == idempotency and auth == expected,
                f"{operation}: exact CF HMAC transport binding mismatch")
    if operation == "task.create" or auth["risk"] == "R2+":
        require(task_create_r2plus, f"{operation}: exact task.create R2+ binding mismatch")
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
    if row["profile"] in {"in-process-invocation", "human-approval-decision"}:
        owner, interface, method = (("Platform", "ICapabilityProvider", "Invoke")
            if delegated else ("Chat", "IChatOperations", "SubmitApproval"))
        namespace = f"ArcForges.Contracts.LocalRpc.{owner}"
        require(operation == f"{interface}.{method}" and row["scope"] == "in-process" and
                row["binding"] == f"{namespace}.Ports.{interface}.{method}Async" and
                row["source"] == f"src/internal/dotnet/{namespace}/Generated/InprocessPorts.g.cs" and
                row["kind"] == "in-process", f"{operation}: closed in-process binding mismatch")
        if delegated:
            require(set(derived) == FIELDS - {"patEligible"} and auth["patEligible"] is False,
                    f"{operation}: incomplete in-process invocation descriptor")
        else:
            expected = {"capability": None, "risk": {"from": "verifiedApprovalProposal.effectiveRisk"},
                        "approval": "foregroundProposal", "stepUp": {"from": "verifiedApprovalProposal.stepUp"},
                        "localPresence": {"from": "verifiedApprovalProposal.localPresence"},
                        "egress": "none", "patEligible": False, "actorKinds": ["human"]}
            require(auth == expected and retry == "IW", f"{operation}: incomplete human approval proposal binding")
    if row["profile"] == "public-human-approval-decision":
        expected = {"capability": None, "risk": {"from": "verifiedApprovalProposal.effectiveRisk"},
                    "approval": "foregroundProposal", "stepUp": {"from": "verifiedApprovalProposal.stepUp"},
                    "localPresence": {"from": "verifiedApprovalProposal.localPresence"},
                    "egress": "none", "patEligible": False, "actorKinds": ["human"]}
        require(operation == "approval.decide" and row["scope"] == "assistant" and
                row["surface"] == "public" and row["kind"] == "proto" and
                row["binding"] == "arcforges.publicapi.v1.ApprovalService/Decide" and
                row["source"] == "public/proto/arcforges/publicapi/v1/chat.proto" and
                row["sourceRule"] == "docs/architecture/contracts/01-public-api-operations.md#rule-tk-02" and
                auth == expected and retry == "IW",
                f"{operation}: incomplete public human approval proposal binding")
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
            export_path = path.relative_to(root).as_posix()
            validate_operation_export_fields(export_path, row)
            operation = row.get("operationId")
            require(isinstance(operation, str), "operation ID required")
            require(operation in oracle, f"unclassified operation: {operation}")
            require(oracle[operation] != "future", f"reserved future operation registered: {operation}")
            require(operation not in exported, f"ambiguous duplicate export: {operation}")
            require(row.get("scope") == oracle[operation], f"{operation}: scope disagrees with oracle")
            binding = row.get("binding")
            require(isinstance(binding, str) and bool(binding) and binding not in bindings, f"ambiguous binding: {binding}")
            require(binding != CON11_PRIVATE_RUN_STREAM["binding"],
                    "CON.11 private RunStream projection must not have an operation export")
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
    private_projections = private_service_projections(root, methods, bindings)
    private_projection_bindings = {projection["binding"] for projection in private_projections}
    examples = []
    for binding, source in methods.items():
        if EXAMPLES.get(binding) == source:
            require(binding not in bindings, f"migration example exported as production: {binding}")
            examples.append(binding)
        elif binding in private_projection_bindings:
            continue
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
            "operations": matrix, "privateServiceProjections": private_projections,
            "coverage": "offline metadata policy only; no runtime authorization acceptance"}


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
