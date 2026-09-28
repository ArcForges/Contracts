// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fromJson } from "@bufbuild/protobuf";
import * as publicShapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";
import * as chat from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/chat_pb.js";
import * as ai from "../../src/internal/ts/ai-internal/dist/gen/http.js";

const publicFixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/public/con-10-chat-task-agent.json", import.meta.url),
    "utf8",
  ),
);
const internalFixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/internal/con-10-ai-internal.json", import.meta.url),
    "utf8",
  ),
);
const operationExport = JSON.parse(
  await readFile(new URL("../../eng/operations/con-10.json", import.meta.url), "utf8"),
);
const aiSchema = JSON.parse(
  await readFile(new URL("../../internal/ai-http/v1/schema.json", import.meta.url), "utf8"),
);

const aiDefinitions = aiSchema.$defs;
const resolve = (node) => (node.$ref ? aiDefinitions[node.$ref.slice("#/$defs/".length)] : node);

function branchFor(node, property) {
  const alternatives = node.oneOf.map((reference) => resolve(reference));
  return alternatives.find((alternative) => alternative.properties?.[property]) ?? alternatives[0];
}

function defaultString(node) {
  if (node.enum) return node.enum[0];
  if (typeof node.const === "string") return node.const;
  const candidates = [
    "10000000-0000-4000-8000-000000000001",
    "2026-09-28T00:00:00Z",
    "0",
    "1",
    "fixture",
    "x",
    "A",
    "AA==",
    "a".repeat(64),
  ];
  if (node.pattern) {
    const pattern = new RegExp(node.pattern);
    const match = candidates.find(
      (candidate) => pattern.test(candidate) && candidate !== node.not?.const,
    );
    if (match !== undefined) return match;
    const fallback = "x".repeat(Math.max(1, node.minLength ?? 1));
    if (pattern.test(fallback) && fallback !== node.not?.const) return fallback;
    throw new Error(`No deterministic fixture string matches ${node.pattern}`);
  }
  return "x".repeat(Math.max(1, node.minLength ?? 1));
}

function defaultValue(original, propertyHint, depth = 0) {
  assert.ok(depth < 40, "schema fixture builder exceeded recursion bound");
  const node = resolve(original);
  if (node.oneOf) return defaultValue(branchFor(node, propertyHint), undefined, depth + 1);
  if (node.type === "object") {
    const out = {};
    for (const property of node.required ?? [])
      out[property] = defaultValue(node.properties[property], undefined, depth + 1);
    return out;
  }
  if (node.type === "array")
    return Array.from({ length: node.minItems ?? 0 }, () =>
      defaultValue(node.items, propertyHint, depth + 1),
    );
  if (node.type === "string") return defaultString(node);
  if (node.type === "integer") return node.minimum ?? 0;
  if (node.type === "number") return node.minimum ?? 0.125;
  if (node.type === "boolean") return false;
  throw new Error(`Unsupported fixture schema node: ${JSON.stringify(node)}`);
}

function setPath(current, original, segments, replacement) {
  const node = resolve(original);
  if (node.oneOf) {
    const property = segments[0] === "[]" ? undefined : segments[0];
    const branch = branchFor(node, property);
    const keys = Object.keys(branch.properties ?? {});
    const required = branch.required ?? [];
    if (
      !current ||
      Object.keys(current).some((key) => !keys.includes(key)) ||
      required.some((key) => !Object.hasOwn(current, key))
    )
      current = defaultValue(branch);
    return setPath(current, branch, segments, replacement);
  }
  if (segments.length === 0) return replacement;
  const [segment, ...rest] = segments;
  if (segment === "[]") {
    assert.equal(node.type, "array");
    if (current.length === 0) current.push(defaultValue(node.items, rest[0]));
    current[0] = setPath(current[0], node.items, rest, replacement);
    return current;
  }
  assert.equal(node.type, "object", `cannot navigate ${segment} through ${node.type}`);
  const child = node.properties[segment];
  assert.ok(child, `unknown fixture path property ${segment}`);
  if (rest.length === 0) current[segment] = replacement;
  else {
    if (!Object.hasOwn(current, segment)) current[segment] = defaultValue(child, rest[0]);
    current[segment] = setPath(current[segment], child, rest, replacement);
  }
  return current;
}

function valuePath(path) {
  return path.replace(/\[\]/g, ".[]").split(".").filter(Boolean);
}

function fixtureValue(vector) {
  if (!vector.valuePattern) return vector.value;
  return vector.valuePattern.repeat.repeat(vector.valuePattern.count) + (vector.suffix ?? "");
}

function aiInputAtPath(vector, value) {
  const segments = valuePath(vector.path);
  const input = defaultValue(aiDefinitions[vector.schema], segments[0]);
  return setPath(input, aiDefinitions[vector.schema], segments, value);
}

test("CON.10 public chat and task shape vectors are consumed by generated validators", () => {
  for (const vector of publicFixture.contractShapeVectors) {
    const validate = publicShapes[`is${vector.shape}`];
    const schema = chat[`${vector.shape}Schema`];
    assert.equal(typeof validate, "function", `${vector.shape} validator is generated`);
    assert.ok(schema, `${vector.shape} protobuf schema is generated`);
    let actual;
    try {
      // fromJson accepts safe JS numbers for uint64 and would erase the forbidden wire spelling.
      const value = fromJson(schema, vector.input);
      const hasNumericEpoch =
        vector.shape === "ApplicationTarget" && typeof vector.input.instanceEpoch === "number";
      if (hasNumericEpoch) value.instanceEpoch = vector.input.instanceEpoch;
      actual = validate(value);
    } catch {
      actual = false;
    }
    assert.equal(actual, vector.valid, vector.id);
  }

  const journeys = new Map(publicFixture.journeyVectors.map((vector) => [vector.id, vector]));
  assert.equal(journeys.get("plain-append-no-generation").taskCreated, false);
  assert.equal(journeys.get("ordinary-generated-reply").owner.turnId !== undefined, true);
  assert.equal(journeys.get("ordinary-generated-reply").taskCreated, false);
  assert.equal(journeys.get("agent-mode").owner.taskId !== undefined, true);
  assert.equal(journeys.get("agent-mode").approvalRequiredForEffects, true);
  assert.equal(
    journeys.get("explicit-promotion-creates-agent-task").writeToolDispatchAllowed,
    false,
  );
  assert.equal(journeys.get("temporary-reply").historyListed, false);
  assert.equal(journeys.get("temporary-reply").searchable, false);
  assert.equal(journeys.get("save-temporary-content").copiesExecutionIdentity, false);
  assert.equal(journeys.get("save-temporary-content").rerunsExecution, false);
  assert.equal(journeys.get("cancel-pause-turn-reconciles-uncertainty").duplicateDispatch, false);
  assert.equal(journeys.get("agent-retry-reconciles-uncertainty").duplicateDispatch, false);
  for (const vector of publicFixture.journeyVectors) assert.equal(vector.valid, true, vector.id);
  for (const vector of publicFixture.negativeVectors) assert.equal(vector.valid, false, vector.id);
});

test("CON.10 publishes exactly the modeled Chat Task and Agent proto method bindings", () => {
  const services = [
    chat.TaskService,
    chat.ApprovalService,
    chat.BridgeService,
    chat.ChatService,
    chat.AgentService,
    chat.SearchService,
    chat.AutomationService,
    chat.SourceService,
  ];
  const actual = services.flatMap((service) =>
    service.methods.map(
      (method) => `arcforges.publicapi.v1.${service.typeName.split(".").at(-1)}/${method.name}`,
    ),
  );
  const registered = operationExport.operations
    .filter(
      (row) =>
        row.kind === "proto" && row.source === "public/proto/arcforges/publicapi/v1/chat.proto",
    )
    .map((row) => row.binding);
  assert.equal(actual.length, 57);
  assert.deepEqual(registered.toSorted(), actual.toSorted());
  for (const service of services)
    for (const method of service.methods) assert.equal(method.methodKind, "unary");
});

test("CON.10 exact public approval profile and 14 CF transport rows remain closed", () => {
  const rows = operationExport.operations;
  const approval = rows.find((row) => row.operationId === "approval.decide");
  assert.deepEqual(approval, {
    operationId: "approval.decide",
    binding: "arcforges.publicapi.v1.ApprovalService/Decide",
    kind: "proto",
    source: "public/proto/arcforges/publicapi/v1/chat.proto",
    scope: "assistant",
    surface: "public",
    profile: "public-human-approval-decision",
    sourceRule: "docs/architecture/contracts/01-public-api-operations.md#rule-tk-02",
    idempotency: "IW",
    authorization: {
      capability: null,
      risk: { from: "verifiedApprovalProposal.effectiveRisk" },
      approval: "foregroundProposal",
      stepUp: { from: "verifiedApprovalProposal.stepUp" },
      localPresence: { from: "verifiedApprovalProposal.localPresence" },
      egress: "none",
      patEligible: false,
      actorKinds: ["human"],
    },
  });

  const expectedRetry = new Map([
    ["authorize", "Q"],
    ["claim", "IW"],
    ["renew", "IW"],
    ["reconcile", "Q"],
    ["context", "Q"],
    ["model-intent", "IW"],
    ["model-outcome", "IW"],
    ["settle", "IW"],
    ["prepare-tools", "IW"],
    ["cloud-tool", "IW"],
    ["wait", "IW"],
    ["finalize", "IW"],
    ["stream-state", "IW"],
    ["late-outcome", "IW"],
  ]);
  const aiRows = rows.filter((row) => row.operationId.startsWith("cf.ai."));
  assert.equal(aiRows.length, 14);
  assert.equal(internalFixture.ports.length, 14);
  for (const port of internalFixture.ports) {
    const route = port.path.split("/").at(-1);
    const row = aiRows.find((candidate) => candidate.operationId === `cf.ai.${route}`);
    assert.ok(row, `missing operation row for ${port.path}`);
    assert.equal(row.binding, port.path);
    assert.equal(row.kind, "http");
    assert.equal(row.source, "internal/ai-http/v1/schema.json");
    assert.equal(row.scope, route === "authorize" ? "resource-owner" : "assistant");
    assert.equal(row.surface, "cf-internal");
    assert.equal(row.profile, "cf-service");
    assert.equal(
      row.sourceRule,
      "docs/architecture/contracts/05-cloudflare-integration.md#3-exact-internal-ports",
    );
    assert.equal(row.idempotency, expectedRetry.get(route));
    assert.deepEqual(row.authorization, {
      capability: null,
      risk: "R1",
      approval: "none",
      stepUp: false,
      localPresence: false,
      egress: "none",
      patEligible: false,
      actorKinds: ["service"],
    });
  }
});

test("14 CF port roots validate, round-trip every union branch, and reject forged or oversized input", () => {
  assert.equal(internalFixture.ports.length, 14);
  for (const port of internalFixture.ports) {
    for (const name of [port.request, port.response]) {
      assert.equal(typeof ai[`is${name}`], "function", `${name} validator is generated`);
      assert.equal(typeof ai[`tryParse${name}Json`], "function", `${name} parser is generated`);
      assert.equal(
        typeof ai[`serialize${name}Json`],
        "function",
        `${name} serializer is generated`,
      );
    }
  }
  for (const vector of internalFixture.positiveVectors) {
    if (vector.input) {
      assert.equal(ai[`is${vector.schema}`](vector.input), true, vector.id);
      if (vector.assertRoundTrip) {
        const parsed = ai[`tryParse${vector.schema}Json`](
          ai[`serialize${vector.schema}Json`](vector.input),
        );
        assert.deepEqual(parsed, { ok: true, value: vector.input }, vector.id);
      }
    } else {
      const input = aiInputAtPath(vector, fixtureValue(vector));
      assert.equal(ai[`is${vector.schema}`](input), true, vector.id);
    }
  }
  for (const vector of internalFixture.negativeVectors) {
    if (vector.path) {
      const input = aiInputAtPath(vector, vector.input);
      assert.equal(ai[`is${vector.schema}`](input), false, vector.id);
    } else if (vector.input) assert.equal(ai[`is${vector.schema}`](vector.input), false, vector.id);
  }

  const overflowVector = internalFixture.negativeVectors.find(
    (vector) => vector.id === "structured-value-rejects-overflowing-number-lexeme",
  );
  const overflowInput = aiInputAtPath(overflowVector, 0.125);
  const overflowJson = JSON.stringify(overflowInput).replace('"number":0.125', '"number":1e999');
  assert.notEqual(
    overflowJson,
    JSON.stringify(overflowInput),
    "overflow fixture injects the exact raw number lexeme",
  );
  assert.equal(ai.tryParseAiModelOutcomeRequestJson(overflowJson).ok, false, overflowVector.id);

  const cursorVector = internalFixture.positiveVectors.find(
    (vector) => vector.id === "cursor-4096-ascii-bytes",
  );
  const boundary = aiInputAtPath(cursorVector, fixtureValue(cursorVector));
  assert.equal(ai.isAiReconcileRequest(boundary), true);
  const tooLong = aiInputAtPath(
    { ...cursorVector, valuePattern: { repeat: "a", count: 4097 } },
    "a".repeat(4097),
  );
  assert.equal(ai.isAiReconcileRequest(tooLong), false);

  const malformedSurrogate = internalFixture.negativeVectors.find(
    (vector) => vector.id === "cursor-rejects-unpaired-surrogate",
  );
  assert.equal(ai.tryParseAiReconcileRequestJson(malformedSurrogate.rawJson).failure, "malformed");
  const malformedUtf8 = internalFixture.negativeVectors.find(
    (vector) => vector.id === "cursor-rejects-invalid-utf8",
  );
  assert.equal(
    ai.tryParseAiReconcileRequestJson(Buffer.from(malformedUtf8.rawUtf8Hex, "hex")).failure,
    "malformed",
  );
});
