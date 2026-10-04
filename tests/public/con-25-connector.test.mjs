// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { create, fromBinary, toBinary, equals } from "@bufbuild/protobuf";
import {
  IdSchema,
  InstantSchema,
  PageStateSchema,
  RequestMetaSchema,
  RevisionSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import {
  ConnectorChallengeSchema,
  ConnectorConnectionSchema,
  ConnectorDefinitionSchema,
  ConnectorProofSchema,
  ConnectorService,
  ConnectorServiceBeginConnectionRequestSchema,
  ConnectorServiceCompleteConnectionRequestSchema,
  ConnectorServiceListConnectionsValueSchema,
  ConnectorServiceRevokeConnectionRequestSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/connector_pb.js";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/con-25-connector.json", import.meta.url), "utf8"),
);
const operations = JSON.parse(
  readFileSync(new URL("../../eng/operations/con-25.json", import.meta.url), "utf8"),
).operations;
const manifest = JSON.parse(
  readFileSync(new URL("../../eng/operation-scope-manifest.json", import.meta.url), "utf8"),
);
const protoText = readFileSync(
  new URL("../../public/proto/arcforges/publicapi/v1/connector.proto", import.meta.url),
  "utf8",
);

const expectedVectors = [
  ["definition-valid-oauth", "ConnectorDefinition", true],
  ["definition-valid-minimal-no-origins", "ConnectorDefinition", true],
  ["definition-bad-id-characters", "ConnectorDefinition", false],
  ["definition-uppercase-manifest-hash", "ConnectorDefinition", false],
  ["definition-short-manifest-hash", "ConnectorDefinition", false],
  ["definition-unknown-auth-kind", "ConnectorDefinition", false],
  ["definition-http-origin", "ConnectorDefinition", false],
  ["definition-origin-with-path", "ConnectorDefinition", false],
  ["definition-origin-with-credentials", "ConnectorDefinition", false],
  ["definition-too-many-origins", "ConnectorDefinition", false],
  ["definition-duplicate-scope", "ConnectorDefinition", false],
  ["definition-missing-package-version", "ConnectorDefinition", false],
  ["connection-valid-connected", "ConnectorConnection", true],
  ["connection-valid-failed-with-reason", "ConnectorConnection", true],
  ["connection-unknown-state", "ConnectorConnection", false],
  ["connection-empty-name", "ConnectorConnection", false],
  ["connection-name-too-long", "ConnectorConnection", false],
  ["connection-zero-connection-id", "ConnectorConnection", false],
  ["connection-missing-revision", "ConnectorConnection", false],
  ["connection-duplicate-scope", "ConnectorConnection", false],
  ["challenge-valid-oauth-url", "ConnectorChallenge", true],
  ["challenge-valid-personal-token-no-url", "ConnectorChallenge", true],
  ["challenge-http-url", "ConnectorChallenge", false],
  ["challenge-missing-expiry", "ConnectorChallenge", false],
  ["challenge-zero-flow-id", "ConnectorChallenge", false],
  ["proof-valid-callback-receipt", "ConnectorProof", true],
  ["proof-valid-personal-token", "ConnectorProof", true],
  ["proof-no-arm", "ConnectorProof", false],
  ["proof-empty-secret", "ConnectorProof", false],
  ["proof-oversize-secret", "ConnectorProof", false],
  ["begin-request-valid", "ConnectorServiceBeginConnectionRequest", true],
  ["begin-request-missing-name", "ConnectorServiceBeginConnectionRequest", false],
  ["begin-request-bad-definition-id", "ConnectorServiceBeginConnectionRequest", false],
  ["complete-request-valid", "ConnectorServiceCompleteConnectionRequest", true],
  ["complete-request-missing-proof", "ConnectorServiceCompleteConnectionRequest", false],
  ["revoke-request-valid", "ConnectorServiceRevokeConnectionRequest", true],
  ["revoke-request-zero-connection-id", "ConnectorServiceRevokeConnectionRequest", false],
  ["list-connections-value-valid", "ConnectorServiceListConnectionsValue", true],
  ["list-connections-value-over-page-bound", "ConnectorServiceListConnectionsValue", false],
];
const expectedMethods = [
  "ListDefinitions",
  "ListConnections",
  "BeginConnection",
  "CompleteConnection",
  "GetConnection",
  "RevokeConnection",
];
const expectedOperationIds = [
  "connector.listDefinitions",
  "connector.listConnections",
  "connector.beginConnection",
  "connector.completeConnection",
  "connector.getConnection",
  "connector.revokeConnection",
];

// ---------------------------------------------------------------- descriptor helpers

function hexBytes(hex) {
  assert.match(hex, /^[0-9a-f]{32}$/, "ids are 32 lower-case hex digits");
  return Uint8Array.from(hex.match(/../g).map((pair) => Number.parseInt(pair, 16)));
}

function typeOfField(field) {
  switch (field.fieldKind) {
    case "scalar":
      assert.equal(field.scalar, 9, `${field.name}: only string scalars are expected`);
      return "string";
    case "message":
      return field.message.typeName;
    case "list":
      assert.equal(field.listKind === "scalar" ? field.scalar : 9, 9);
      return field.listKind === "scalar" ? "repeated string" : `repeated ${field.message.typeName}`;
    default:
      return assert.fail(`${field.name}: unexpected field kind ${field.fieldKind}`);
  }
}

function describeFields(message) {
  return message.fields.map((field) => [field.jsonName, field.number, typeOfField(field)]);
}

function pairs(message) {
  return message.fields.map((field) => [field.jsonName, field.number]);
}

// A deliberately mismatched comparison must fail: prove the field-list comparison discriminates.
function sameFieldList(actual, expected) {
  try {
    assert.deepEqual(actual, expected);
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- tests

test("CON.25 decisions, operation export and authorization facts match the fixture", () => {
  assert.equal(fixture.schemaVersion, "con-25-connector.v1");
  assert.equal(fixture.evidenceClass, "offline-contract-only-no-owner-service-or-provider");
  assert.equal(fixture.service, ConnectorService.typeName);
  assert.equal(fixture.source, "public/proto/arcforges/publicapi/v1/connector.proto");
  assert.deepEqual(
    fixture.decisions.map((decision) => decision.id),
    [
      "revoke-expected-revision",
      "public-records-in-public-package",
      "foreground-and-tool-reachability",
      "idempotency-compatibility-classes",
      "no-owner-runtime",
    ],
  );
  assert.deepEqual(
    fixture.operations.map((operation) => operation.operationId),
    expectedOperationIds,
  );
  assert.deepEqual(
    operations.map((row) => row.operationId).sort(),
    [...expectedOperationIds].sort(),
  );
  const toolAllowlist = manifest.toolAllowlist;
  assert.ok(Array.isArray(toolAllowlist));
  for (const operation of fixture.operations) {
    const methodName = operation.rpc.split("/")[1];
    const row = operations.find((candidate) => candidate.operationId === operation.operationId);
    assert.ok(row, `${operation.operationId}: export row exists`);
    assert.equal(operation.rpc, `ConnectorService/${methodName}`);
    assert.equal(row.binding, `${ConnectorService.typeName}/${methodName}`);
    assert.equal(row.kind, "proto");
    assert.equal(row.source, fixture.source);
    assert.equal(row.scope, "assistant");
    assert.equal(operation.authorization.scope, "assistant");
    assert.equal(row.surface, "public");
    assert.equal(row.profile, "human-owner");
    assert.equal(row.idempotency, operation.authorization.idempotency);
    const authorization = operation.authorization;
    assert.deepEqual(row.authorization, {
      capability: authorization.capability,
      risk: authorization.risk,
      approval: authorization.approval,
      stepUp: authorization.stepUp,
      localPresence: authorization.localPresence,
      egress: authorization.egress,
      patEligible: authorization.patEligible,
      actorKinds: authorization.actorKinds,
    });
    assert.deepEqual(row.authorization.actorKinds, ["human"]);
    assert.equal(row.authorization.capability, null);
    assert.equal(row.authorization.patEligible, false);
    assert.equal(row.authorization.localPresence, false);
    assert.equal(authorization.toolReachable, false);
    assert.ok(
      !toolAllowlist.some(
        (entry) =>
          (typeof entry === "string" ? entry : entry?.operationId) === operation.operationId,
      ),
      `${operation.operationId}: not in the tool allowlist`,
    );
  }
  assert.equal(toolAllowlist.length, 0, "the tool allowlist stays empty");
  const byId = new Map(fixture.operations.map((operation) => [operation.operationId, operation]));
  const expectations = {
    "connector.listDefinitions": ["Q", "R1", "none", false, "none", "AO", false],
    "connector.listConnections": ["Q", "R1", "none", false, "none", "AO", false],
    "connector.getConnection": ["Q", "R1", "none", false, "none", "AO", false],
    "connector.beginConnection": [
      "CC",
      "R3",
      "foreground-human-consent",
      true,
      "definition-hash-bound-provider-origins-scopes",
      "FR",
      true,
    ],
    "connector.completeConnection": [
      "NI",
      "R3",
      "original-foreground-human-consent-flow",
      true,
      "definition-hash-bound-provider-origins-scopes",
      "FR",
      true,
    ],
    "connector.revokeConnection": [
      "DE",
      "R2",
      "foreground-human-confirmation",
      false,
      "definition-hash-bound-existing-provider-revocation",
      "FR",
      true,
    ],
  };
  for (const [operationId, expected] of Object.entries(expectations)) {
    const { authorization } = byId.get(operationId);
    assert.deepEqual(
      [
        authorization.idempotency,
        authorization.risk,
        authorization.approval,
        authorization.stepUp,
        authorization.egress,
        authorization.compatibility,
        authorization.foreground,
      ],
      expected,
      operationId,
    );
  }
});

test("CON.25 generated ConnectorService descriptor matches the fixture RPCs and tags", () => {
  assert.equal(ConnectorService.typeName, "arcforges.publicapi.v1.ConnectorService");
  assert.deepEqual(
    ConnectorService.methods.map((method) => method.name),
    expectedMethods,
  );
  assert.deepEqual(
    fixture.operations.map((operation) => operation.rpc.split("/")[1]),
    expectedMethods,
  );
  for (const [index, operation] of fixture.operations.entries()) {
    const method = ConnectorService.methods[index];
    assert.equal(method.methodKind, "unary");
    assert.equal(operation.rpc, `ConnectorService/${method.name}`);
    assert.equal(method.input.typeName, `arcforges.publicapi.v1.${operation.requestType}`);
    assert.equal(method.output.typeName, `arcforges.publicapi.v1.${operation.responseType}`);
    assert.deepEqual(pairs(method.input), operation.requestFields, `${method.name} request`);
    const meta = method.input.fields.find((field) => field.number === 1);
    assert.equal(meta?.name, "meta");
    assert.equal(meta.message?.typeName, "arcforges.foundation.v1.RequestMeta");
    assert.ok(method.input.fields.every((field) => field.number === 1 || field.number >= 10));
    assert.equal(method.input.oneofs.length, 0, "requests have no oneof");

    const responseMeta = method.output.fields.find((field) => field.number === 1);
    assert.equal(responseMeta?.name, "meta");
    assert.equal(responseMeta.message?.typeName, "arcforges.foundation.v1.ResponseMeta");
    const outcome = method.output.fields.filter((field) => field.number >= 2);
    assert.deepEqual(
      outcome.map((field) => [field.jsonName, field.number]),
      operation.outcomeFields,
      `${method.name} outcome`,
    );
    assert.ok(outcome.every((field) => field.oneof?.name === "outcome"));
    assert.deepEqual(
      method.output.fields.map((field) => field.number),
      [1, ...outcome.map((field) => field.number)],
    );
    assert.equal(outcome.find((field) => field.number === 2).name, "value");
    assert.equal(outcome.find((field) => field.number === 3).name, "error");
    assert.equal(
      outcome.find((field) => field.number === 3).message.typeName,
      "arcforges.foundation.v1.ArcError",
    );
    const encoded = outcome.find((field) => field.number === 4);
    const hasEncodedBody =
      operation.rpc.endsWith("/ListDefinitions") ||
      operation.rpc.endsWith("/ListConnections") ||
      operation.rpc.endsWith("/GetConnection");
    if (hasEncodedBody) {
      assert.equal(encoded?.jsonName, "encodedBody");
      assert.equal(encoded.message.typeName, "arcforges.foundation.v1.EncodedBodyRef");
    } else {
      assert.equal(encoded, undefined, `${method.name}: no encodedBody arm`);
    }
    const value = outcome.find((field) => field.number === 2);
    assert.equal(value.message.typeName, `arcforges.publicapi.v1.${operation.valueType}`);
    assert.deepEqual(pairs(value.message), operation.valueFields, `${method.name} value`);
    assert.ok(value.message.fields.every((field) => field.number >= 10));
  }
  const requestMetaTag2 = RequestMetaSchema.fields.find((field) => field.number === 2);
  assert.equal(requestMetaTag2.name, "expected_rev");
  assert.equal(requestMetaTag2.jsonName, "expectedRev");
  const revoke = ConnectorService.methods.find((method) => method.name === "RevokeConnection");
  assert.deepEqual(
    revoke.input.fields.map((field) => field.jsonName),
    ["meta", "connectionId"],
    "revoke request carries only meta and connectionId",
  );
  assert.ok(
    fixture.decisions.some((decision) => decision.id === "revoke-expected-revision"),
    "the revoke revision decision is recorded",
  );
});

test("CON.25 record descriptors match the fixture field lists and presence", () => {
  const schemas = {
    ConnectorDefinition: ConnectorDefinitionSchema,
    ConnectorConnection: ConnectorConnectionSchema,
    ConnectorChallenge: ConnectorChallengeSchema,
    ConnectorProof: ConnectorProofSchema,
  };
  assert.deepEqual(Object.keys(fixture.records), Object.keys(schemas));
  for (const [name, schema] of Object.entries(schemas)) {
    assert.equal(schema.typeName, `arcforges.publicapi.v1.${name}`);
    assert.deepEqual(describeFields(schema), fixture.records[name], name);
  }
  assert.deepEqual(
    ConnectorProofSchema.oneofs.map((oneof) => [
      oneof.name,
      oneof.fields.map((field) => field.jsonName),
    ]),
    [["proof", ["callbackReceipt", "personalToken"]]],
  );
  // singular string fields keep explicit presence (a required member is not conflated with "")
  for (const field of ConnectorDefinitionSchema.fields.filter((f) => f.fieldKind === "scalar")) {
    assert.equal(field.presence, 1, `ConnectorDefinition.${field.name} has explicit presence`);
  }
  assert.deepEqual(fixture.localTwin, {
    package: "arcforges.local.platform.v1",
    service: "ConnectorBrokerService",
    records: Object.keys(schemas),
    pageBound: 200,
    publicPageBound: 100,
  });
});

test("CON.25 field-list comparison is discriminating", () => {
  const expected = fixture.records.ConnectorChallenge;
  assert.ok(sameFieldList(describeFields(ConnectorChallengeSchema), expected));
  const renamed = structuredClone(expected);
  renamed[2][0] = "authorizationUri";
  assert.ok(!sameFieldList(describeFields(ConnectorChallengeSchema), renamed), "renamed field");
  const retagged = structuredClone(expected);
  retagged[3][1] = 9;
  assert.ok(!sameFieldList(describeFields(ConnectorChallengeSchema), retagged), "retagged field");
  const retyped = structuredClone(expected);
  retyped[1][2] = "string";
  assert.ok(!sameFieldList(describeFields(ConnectorChallengeSchema), retyped), "retyped field");
  const reordered = [...expected].reverse();
  assert.ok(!sameFieldList(describeFields(ConnectorChallengeSchema), reordered), "reordered");
});

test("CON.25 the public connector package imports no local schema and keeps the service shape", () => {
  const imports = [...protoText.matchAll(/^import\s+"([^"]+)";/gm)].map((match) => match[1]);
  assert.deepEqual(imports, ["arcforges/foundation/v1/foundation.proto"]);
  assert.ok(!/arcforges\.local\./.test(protoText), "no local package reference");
  assert.ok(!/internal\/proto|arcforges\/local\//.test(protoText), "no local import path");
  assert.ok(/^package arcforges\.publicapi\.v1;/m.test(protoText));
  const oneofs = [...protoText.matchAll(/^\s*oneof\s+(\w+)\s*\{/gm)].map((match) => match[1]);
  assert.deepEqual(oneofs, [
    "proof",
    "outcome",
    "outcome",
    "outcome",
    "outcome",
    "outcome",
    "outcome",
  ]);
  assert.ok(!/google\.protobuf\.(Any|Struct)/.test(protoText), "no Any/Struct");
  const rpcs = [...protoText.matchAll(/^\s*rpc\s+(\w+)\(/gm)].map((match) => match[1]);
  assert.deepEqual(rpcs, expectedMethods);
});

// ---------------------------------------------------------------- vectors

const metaTemplate = () =>
  create(RequestMetaSchema, {
    correlationId: create(IdSchema, { value: hexBytes("0f0e0d0c0b0a09080706050403020100") }),
  });

function id(hex) {
  return create(IdSchema, { value: hexBytes(hex) });
}

function instant(value) {
  return create(InstantSchema, {
    unixSeconds: BigInt(value.unixSeconds),
    nanos: value.nanos,
  });
}

function defined(init) {
  return Object.fromEntries(Object.entries(init).filter(([, v]) => v !== undefined));
}

function buildProof(value) {
  const init = {};
  if (value.callbackReceipt !== undefined) {
    init.proof = { case: "callbackReceipt", value: value.callbackReceipt };
  }
  if (value.personalToken !== undefined) {
    init.proof = { case: "personalToken", value: value.personalToken };
  }
  return create(ConnectorProofSchema, init);
}

function buildConnection(value) {
  return create(
    ConnectorConnectionSchema,
    defined({
      connectionId: value.connectionIdHex === undefined ? undefined : id(value.connectionIdHex),
      definitionId: value.definitionId,
      name: value.name,
      state: value.state,
      scopes: value.scopes,
      revision:
        value.revision === undefined
          ? undefined
          : create(RevisionSchema, { value: BigInt(value.revision) }),
      expiresAt: value.expiresAt === undefined ? undefined : instant(value.expiresAt),
      reason: value.reason,
    }),
  );
}

const builders = {
  ConnectorDefinition: (value) => create(ConnectorDefinitionSchema, defined({ ...value })),
  ConnectorConnection: buildConnection,
  ConnectorChallenge: (value) =>
    create(
      ConnectorChallengeSchema,
      defined({
        flowId: id(value.flowIdHex),
        connectionId: id(value.connectionIdHex),
        authorizationUrl: value.authorizationUrl,
        expiresAt: value.expiresAt === undefined ? undefined : instant(value.expiresAt),
      }),
    ),
  ConnectorProof: buildProof,
  ConnectorServiceBeginConnectionRequest: (value, withMeta = true) =>
    create(
      ConnectorServiceBeginConnectionRequestSchema,
      defined({
        meta: withMeta ? metaTemplate() : undefined,
        connectionId: id(value.connectionIdHex),
        definitionId: value.definitionId,
        name: value.name,
      }),
    ),
  ConnectorServiceCompleteConnectionRequest: (value, withMeta = true) =>
    create(
      ConnectorServiceCompleteConnectionRequestSchema,
      defined({
        meta: withMeta ? metaTemplate() : undefined,
        flowId: id(value.flowIdHex),
        proof: value.proof === undefined ? undefined : buildProof(value.proof),
      }),
    ),
  ConnectorServiceRevokeConnectionRequest: (value, withMeta = true) =>
    create(
      ConnectorServiceRevokeConnectionRequestSchema,
      defined({
        meta: withMeta ? metaTemplate() : undefined,
        connectionId: id(value.connectionIdHex),
      }),
    ),
  ConnectorServiceListConnectionsValue: (value) =>
    create(
      ConnectorServiceListConnectionsValueSchema,
      defined({
        items: value.items.map(buildConnection),
        page: value.page === undefined ? undefined : create(PageStateSchema, defined(value.page)),
      }),
    ),
};
const schemasByType = {
  ConnectorDefinition: ConnectorDefinitionSchema,
  ConnectorConnection: ConnectorConnectionSchema,
  ConnectorChallenge: ConnectorChallengeSchema,
  ConnectorProof: ConnectorProofSchema,
  ConnectorServiceBeginConnectionRequest: ConnectorServiceBeginConnectionRequestSchema,
  ConnectorServiceCompleteConnectionRequest: ConnectorServiceCompleteConnectionRequestSchema,
  ConnectorServiceRevokeConnectionRequest: ConnectorServiceRevokeConnectionRequestSchema,
  ConnectorServiceListConnectionsValue: ConnectorServiceListConnectionsValueSchema,
};

test("CON.25 every connector vector is consumed once through the generated shape validators", () => {
  const vectors = fixture.vectors;
  const ids = vectors.map((vector) => vector.id);
  assert.equal(new Set(ids).size, ids.length, "vector ids are unique");
  assert.deepEqual(
    [...ids].sort(),
    expectedVectors.map(([vectorId]) => vectorId).sort(),
    "only the authorized vectors exist",
  );
  const expectedById = new Map(
    expectedVectors.map(([vectorId, type, valid]) => [vectorId, { type, valid }]),
  );
  const consumed = new Set();
  let positives = 0;
  let negatives = 0;
  for (const vector of vectors) {
    assert.ok(!consumed.has(vector.id), `duplicate consumption: ${vector.id}`);
    consumed.add(vector.id);
    const expected = expectedById.get(vector.id);
    assert.ok(expected, `unknown vector ${vector.id}`);
    assert.equal(vector.type, expected.type, `${vector.id}: type`);
    assert.equal(vector.valid, expected.valid, `${vector.id}: validity`);
    assert.equal(typeof vector.why, "string");
    const build = builders[vector.type];
    const validate = shapes[`is${vector.type}`];
    assert.equal(typeof build, "function", `${vector.id}: builder`);
    assert.equal(typeof validate, "function", `${vector.id}: generated validator is${vector.type}`);
    const message = build(vector.value);
    assert.equal(validate(message), vector.valid, `${vector.id}: generated validator`);
    // protobuf bytes preserve presence and values for every vector, valid or not
    const schema = schemasByType[vector.type];
    const roundTripped = fromBinary(schema, toBinary(schema, message));
    assert.ok(equals(schema, message, roundTripped), `${vector.id}: protobuf round trip`);
    assert.equal(validate(roundTripped), vector.valid, `${vector.id}: validator after round trip`);
    if (vector.valid) positives++;
    else negatives++;
  }
  assert.deepEqual([...consumed].sort(), [...expectedById.keys()].sort(), "all consumed");
  assert.equal(positives, 12);
  assert.equal(negatives, 27);
});

test("CON.25 request vectors depend on RequestMeta and the revoke revision lives in meta.expectedRev", () => {
  for (const type of [
    "ConnectorServiceBeginConnectionRequest",
    "ConnectorServiceCompleteConnectionRequest",
    "ConnectorServiceRevokeConnectionRequest",
  ]) {
    const vector = fixture.vectors.find((candidate) => candidate.type === type && candidate.valid);
    assert.ok(vector, type);
    const validate = shapes[`is${type}`];
    assert.equal(validate(builders[type](vector.value)), true, `${type}: with meta`);
    assert.equal(validate(builders[type](vector.value, false)), false, `${type}: meta is required`);
  }
  const revoke = fixture.vectors.find((vector) => vector.id === "revoke-request-valid");
  const message = builders.ConnectorServiceRevokeConnectionRequest(revoke.value);
  message.meta.expectedRev = create(RevisionSchema, { value: 7n });
  assert.equal(shapes.isConnectorServiceRevokeConnectionRequest(message), true);
  assert.equal(shapes.isRequestMeta(message.meta), true);
  const round = fromBinary(
    ConnectorServiceRevokeConnectionRequestSchema,
    toBinary(ConnectorServiceRevokeConnectionRequestSchema, message),
  );
  assert.equal(round.meta.expectedRev.value, 7n);
  assert.deepEqual(
    Object.keys(revoke.value),
    ["connectionIdHex"],
    "the revoke vector carries only the connection id",
  );
});

test("CON.25 page bound and proof oneof are discriminated by the generated validators", () => {
  const valid = fixture.vectors.find((vector) => vector.id === "list-connections-value-valid");
  const over = fixture.vectors.find(
    (vector) => vector.id === "list-connections-value-over-page-bound",
  );
  assert.equal(over.value.items.length, 101);
  // exactly 100 items must be accepted (the public bound), 101 refused
  const hundred = structuredClone(over.value);
  hundred.items.length = 100;
  assert.equal(
    shapes.isConnectorServiceListConnectionsValue(
      builders.ConnectorServiceListConnectionsValue(hundred),
    ),
    true,
  );
  assert.equal(
    shapes.isConnectorServiceListConnectionsValue(
      builders.ConnectorServiceListConnectionsValue(over.value),
    ),
    false,
  );
  assert.equal(valid.value.items.length, 2);
  const both = create(ConnectorProofSchema, { proof: { case: "personalToken", value: "t" } });
  assert.equal(shapes.isConnectorProof(both), true);
  const none = create(ConnectorProofSchema, {});
  assert.equal(shapes.isConnectorProof(none), false);
});
