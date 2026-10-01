// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { ScalarType, fromBinary, fromJson, toBinary } from "@bufbuild/protobuf";
import * as publicPackage from "@arcforges/proto";
import * as operatorClient from "@arcforges/operator-client";

const read = async (path) => readFile(new URL(`../../${path}`, import.meta.url), "utf8");
const fixture = JSON.parse(await read("fixtures/internal/con-14-operator.json"));
const exportRows = JSON.parse(await read("eng/operations/con-14.json")).operations;

const OPERATOR_SERVICE = "arcforges.operator.v1.OperatorService";
const ROLES = ["customerSupport", "recoverySpecialist", "operations", "trustSafety", "security"];
const METHODS = [
  "ListCases",
  "GetCase",
  "RequestAccess",
  "ApproveAccess",
  "EndAccess",
  "ReadDiagnostic",
  "ProposeEnforcement",
  "DecideEnforcement",
  "GetAppeal",
  "ResolveAppeal",
  "StageConfiguration",
  "ValidateConfiguration",
  "ApproveConfiguration",
  "ActivateConfiguration",
  "GetConfiguration",
  "SetKillSwitch",
  "StartBreakGlass",
  "EndBreakGlass",
  "ProposeAction",
  "ApproveAction",
  "GetProposal",
  "GrantEntitlement",
  "RevokeEntitlement",
  "IssueCompensation",
  "AdjustCompensation",
  "DecideRefund",
  "GetCatalogSubmission",
  "ReplyCase",
  "SetCaseState",
  "ReviewCatalogSubmission",
  "RevokeCatalogVersion",
];
const PROPOSAL_REF_METHODS = new Set([
  "ResolveAppeal",
  "SetKillSwitch",
  "ReviewCatalogSubmission",
  "RevokeCatalogVersion",
]);
// Independent Registry04 section 9.1 oracle (class, risk, approval, step-up, egress, roles).
const ORACLE = {
  "operator.listCases": ["ListCases", "Q", "R1", "none", false, "none", ["CS", "RS", "TS", "SE"]],
  "operator.getCase": ["GetCase", "Q", "R1", "none", false, "none", ["CS", "RS", "TS", "SE"]],
  "operator.requestAccess": [
    "RequestAccess",
    "CC",
    "R3",
    "foreground",
    true,
    "none",
    ["CS", "RS", "TS"],
  ],
  "operator.approveAccess": [
    "ApproveAccess",
    "IW",
    "R3",
    "secondOperatorAndOwnerConsent",
    true,
    "none",
    ["RS", "SE"],
  ],
  "operator.endAccess": [
    "EndAccess",
    "IW",
    "R2",
    "foreground",
    false,
    "none",
    ["CS", "RS", "TS", "SE"],
  ],
  "operator.readDiagnostic": [
    "ReadDiagnostic",
    "Q",
    "R3",
    "activeAccessGrant",
    true,
    "diagnosticToOperator",
    ["CS", "RS", "TS"],
  ],
  "operator.proposeEnforcement": [
    "ProposeEnforcement",
    "CC",
    "R3",
    "foreground",
    true,
    "none",
    ["TS"],
  ],
  "operator.decideEnforcement": [
    "DecideEnforcement",
    "IW",
    "R3",
    "secondOperator",
    true,
    "none",
    ["SE"],
  ],
  "operator.getAppeal": ["GetAppeal", "Q", "R1", "none", false, "none", ["TS", "SE"]],
  "operator.resolveAppeal": ["ResolveAppeal", "IW", "R3", "approvedProposal", true, "none", ["TS"]],
  "operator.stageConfiguration": [
    "StageConfiguration",
    "CC",
    "R3",
    "foreground",
    true,
    "none",
    ["OP"],
  ],
  "operator.validateConfiguration": [
    "ValidateConfiguration",
    "Q",
    "R3",
    "none",
    true,
    "none",
    ["OP"],
  ],
  "operator.approveConfiguration": [
    "ApproveConfiguration",
    "IW",
    "R3",
    "secondOperator",
    true,
    "none",
    ["SE"],
  ],
  "operator.activateConfiguration": [
    "ActivateConfiguration",
    "IW",
    "R3",
    "secondOperatorReceipt",
    true,
    "none",
    ["OP"],
  ],
  "operator.getConfiguration": ["GetConfiguration", "Q", "R2", "none", false, "none", ["OP", "SE"]],
  "operator.setKillSwitch": ["SetKillSwitch", "IW", "R3", "approvedProposal", true, "none", ["OP"]],
  "operator.startBreakGlass": [
    "StartBreakGlass",
    "CC",
    "R4",
    "alarmedIncident",
    true,
    "caseBoundRecovery",
    ["SE"],
  ],
  "operator.endBreakGlass": ["EndBreakGlass", "IW", "R2", "foreground", false, "none", ["SE"]],
  "operator.proposeAction": ["ProposeAction", "CC", "R3", "foreground", true, "none", "proposer"],
  "operator.approveAction": [
    "ApproveAction",
    "IW",
    "R3",
    "secondOperator",
    true,
    "none",
    "approver",
  ],
  "operator.getProposal": ["GetProposal", "Q", "R2", "none", false, "none", "proposerOrApprover"],
  "operator.grantEntitlement": [
    "GrantEntitlement",
    "CC",
    "R3",
    "approvedProposal",
    true,
    "none",
    ["CS", "RS"],
  ],
  "operator.revokeEntitlement": [
    "RevokeEntitlement",
    "DE",
    "R3",
    "approvedProposal",
    true,
    "none",
    ["CS", "RS"],
  ],
  "operator.issueCompensation": [
    "IssueCompensation",
    "CC",
    "R3",
    "approvedProposal",
    true,
    "none",
    ["CS"],
  ],
  "operator.adjustCompensation": [
    "AdjustCompensation",
    "IW",
    "R3",
    "approvedProposal",
    true,
    "none",
    ["CS"],
  ],
  "operator.decideRefund": [
    "DecideRefund",
    "IW",
    "R3",
    "approvedProposal",
    true,
    "paymentProvider",
    ["CS"],
  ],
  "operator.getCatalogSubmission": [
    "GetCatalogSubmission",
    "Q",
    "R2",
    "none",
    false,
    "none",
    ["TS", "SE"],
  ],
  "operator.replyCase": [
    "ReplyCase",
    "CC",
    "R2",
    "foreground",
    false,
    "caseOwnerNotification",
    ["CS", "RS", "TS", "SE"],
  ],
  "operator.setCaseState": [
    "SetCaseState",
    "IW",
    "R2",
    "foreground",
    false,
    "caseOwnerNotification",
    ["CS", "RS", "TS", "SE"],
  ],
  "catalog.review": [
    "ReviewCatalogSubmission",
    "IW",
    "R3",
    "approvedProposal",
    true,
    "none",
    ["TS"],
  ],
  "catalog.revoke": ["RevokeCatalogVersion", "DE", "R3", "approvedProposal", true, "none", ["TS"]],
};
const ABBREVIATION = {
  CS: "customerSupport",
  RS: "recoverySpecialist",
  OP: "operations",
  TS: "trustSafety",
  SE: "security",
};
const MUTATION_TABLE = {
  grant: ["operator.grantEntitlement", ["customerSupport", "recoverySpecialist"], "operations"],
  revokeGrant: [
    "operator.revokeEntitlement",
    ["customerSupport", "recoverySpecialist"],
    "security",
  ],
  issueCredit: ["operator.issueCompensation", ["customerSupport"], "operations"],
  adjustCredit: ["operator.adjustCompensation", ["customerSupport"], "operations"],
  refund: ["operator.decideRefund", ["customerSupport"], "operations"],
  catalogReview: ["catalog.review", ["trustSafety"], "security"],
  catalogRevoke: ["catalog.revoke", ["trustSafety"], "security"],
  appeal: ["operator.resolveAppeal", ["trustSafety"], "security"],
  kill: ["operator.setKillSwitch", ["operations"], "security"],
};

const service = operatorClient.contractServices.find(
  (candidate) => candidate.typeName === OPERATOR_SERVICE,
);

test("CON.14 exports exactly one internal OperatorService with the 31 Registry04 methods", () => {
  assert.equal(operatorClient.contractServices.length, 1);
  assert.ok(service, "missing OperatorService");
  assert.deepEqual(
    service.methods.map((method) => method.name),
    METHODS,
  );
  for (const method of service.methods) assert.equal(method.methodKind, "unary", method.name);
});

test("CON.14 request envelopes carry meta, tag-100 context, exact tag-101 proposal refs and the GetCase tag-102 page", () => {
  for (const method of service.methods) {
    assert.equal(method.input.typeName, `${OPERATOR_SERVICE}${method.name}Request`);
    assert.equal(method.output.typeName, `${OPERATOR_SERVICE}${method.name}Response`);
    const request = new Map(method.input.fields.map((field) => [field.number, field]));
    assert.equal(request.get(1)?.message?.typeName, "arcforges.foundation.v1.RequestMeta");
    for (let tag = 2; tag <= 9; tag += 1)
      assert.equal(request.has(tag), false, `${method.name}:${tag}`);
    assert.equal(request.get(100)?.name, "context", method.name);
    assert.equal(request.get(100)?.message?.typeName, "arcforges.operator.v1.OperatorCallContext");
    assert.equal(request.has(101), PROPOSAL_REF_METHODS.has(method.name), `${method.name} tag 101`);
    if (request.has(101)) {
      assert.equal(request.get(101).name, "proposal");
      assert.equal(request.get(101).message.typeName, "arcforges.operator.v1.OperatorProposalRef");
    }
    assert.equal(request.has(102), method.name === "GetCase", `${method.name} tag 102`);
    if (request.has(102)) {
      assert.equal(request.get(102).name, "messages");
      assert.equal(request.get(102).message.typeName, "arcforges.foundation.v1.PageRequest");
    }
    const response = new Map(method.output.fields.map((field) => [field.number, field]));
    assert.equal(response.get(1)?.message?.typeName, "arcforges.foundation.v1.ResponseMeta");
    assert.equal(response.get(2)?.oneof?.name, "outcome", method.name);
    assert.equal(response.get(3)?.oneof?.name, "outcome", method.name);
    assert.equal(response.get(3)?.message?.typeName, "arcforges.foundation.v1.ArcError");
    for (let tag = 4; tag <= 9; tag += 1)
      assert.equal(response.has(tag), false, `${method.name}:${tag}`);
  }
});

test("CON.14 keeps OperatorService and its records out of the public TypeScript package", () => {
  assert.equal(
    publicPackage.contractServices.some((candidate) => candidate.typeName === OPERATOR_SERVICE),
    false,
  );
  for (const name of [
    "OperatorService",
    "OperatorCallContextSchema",
    "OperatorProposalRefSchema",
  ]) {
    assert.equal(name in publicPackage, false, name);
    assert.equal(name in operatorClient, true, name);
  }
});

test("CON.14 authorization export, role matrix and Registry04 oracle agree exactly", () => {
  const matrix = fixture.operationMatrix;
  assert.deepEqual(fixture.roleVocabulary, ROLES);
  assert.equal(matrix.length, 31);
  assert.equal(exportRows.length, 31);
  assert.deepEqual(
    matrix.map((row) => row.operationId),
    Object.keys(ORACLE),
  );
  assert.equal(Object.keys(ORACLE).filter((id) => id.startsWith("operator.")).length, 29);
  assert.deepEqual(
    Object.keys(ORACLE).filter((id) => id.startsWith("catalog.")),
    ["catalog.review", "catalog.revoke"],
  );
  assert.deepEqual(
    Object.values(ORACLE).map((row) => row[0]),
    METHODS,
  );
  for (const row of matrix) {
    const [method, cls, risk, approval, stepUp, egress, roles] = ORACLE[row.operationId];
    assert.equal(row.method, method);
    assert.equal(row.class, cls);
    assert.equal(row.risk, risk);
    assert.equal(row.approval, approval);
    assert.equal(row.stepUp, stepUp);
    assert.equal(row.egress, egress);
    if (typeof roles === "string") {
      assert.equal(row.roles, null, row.operationId);
      assert.equal(row.payloadBoundRoles, roles, row.operationId);
    } else {
      assert.deepEqual(
        row.roles,
        roles.map((abbreviation) => ABBREVIATION[abbreviation]),
        row.operationId,
      );
      assert.equal("payloadBoundRoles" in row, false, row.operationId);
    }
    const exported = exportRows.find((candidate) => candidate.operationId === row.operationId);
    assert.ok(exported, `export for ${row.operationId}`);
    assert.equal(exported.binding, `${OPERATOR_SERVICE}/${method}`);
    assert.equal(exported.kind, "proto");
    assert.equal(exported.source, "internal/proto/arcforges/operator/v1/operator.proto");
    assert.equal(exported.scope, "operator");
    assert.equal(exported.surface, "operator");
    assert.equal(exported.profile, "operator");
    assert.equal(exported.idempotency, cls);
    assert.deepEqual(exported.authorization, {
      capability: null,
      risk,
      approval,
      stepUp,
      localPresence: false,
      egress,
      patEligible: false,
      actorKinds: ["operator"],
    });
  }
});

test("CON.14 typed mutation protocol binds each variant to its executing operation and distinct approver", () => {
  const rolesByOperation = new Map(
    fixture.operationMatrix.map((row) => [row.operationId, row.roles]),
  );
  const vectors = new Map(fixture.mutationVectors.map((vector) => [vector.variant, vector]));
  assert.deepEqual([...vectors.keys()], Object.keys(MUTATION_TABLE));
  const mutationFields = operatorClient.OperatorMutationSchema.fields.map(
    (field) => field.localName,
  );
  assert.deepEqual(mutationFields, Object.keys(MUTATION_TABLE));
  for (const [variant, [operation, proposers, approver]] of Object.entries(MUTATION_TABLE)) {
    const vector = vectors.get(variant);
    assert.equal(vector.executingOperation, operation, variant);
    assert.deepEqual(vector.proposerRoles, proposers, variant);
    assert.equal(vector.distinctApproverRole, approver, variant);
    assert.deepEqual(rolesByOperation.get(operation), proposers, `${variant} executor roles`);
    assert.equal(proposers.includes(approver), false, `${variant} approver is a distinct duty`);
    assert.equal(ROLES.includes(approver), true, variant);
    assert.deepEqual(vector.expectedProposalLifecycle, ["pending", "approved", "executed"]);
    assert.equal(vector.runtimeAcceptanceProven, false);
  }
});

test("CON.14 protocol, negative and lost-receipt vectors stay declarative and complete", () => {
  const protocol = fixture.protocolExpectations;
  assert.equal(protocol.proposalLifetimeMinutes, 15);
  assert.deepEqual(protocol.proposalStates, [
    "pending",
    "approved",
    "rejected",
    "expired",
    "invalidated",
    "executed",
  ]);
  assert.equal(protocol.changedContentWithReusedCommand, "refuse with command.reused_identifier");
  assert.deepEqual(fixture.negativeVectors.map((vector) => vector.id).sort(), [
    "changed-configuration-invalidates-approval",
    "changed-content-with-reused-command-refused",
    "changed-proposal-hash-refused",
    "concurrent-consumption-happens-at-most-once",
    "expired-proposal-refused",
    "non-operator-caller-refused",
    "revoked-required-role-invalidates-approval",
    "same-identity-cannot-propose-and-approve",
    "stale-owner-revision-refused",
    "stale-proposal-revision-refused",
  ]);
  assert.deepEqual(
    fixture.lostReceiptVectors.map((vector) => vector.id),
    ["lost-response-same-command-replays-original-receipt"],
  );
  for (const vector of [
    ...fixture.negativeVectors,
    ...fixture.lostReceiptVectors,
    ...fixture.mutationVectors,
  ]) {
    assert.equal(vector.runtimeAcceptanceProven, false, vector.id ?? vector.variant);
  }
});

test("CON.14 shape vectors are independently checked against generated validators and binary round trips", () => {
  const ids = new Set();
  let positives = 0;
  let negatives = 0;
  for (const entry of fixture.shapeCases) {
    assert.equal(ids.has(entry.id), false, `duplicate ${entry.id}`);
    ids.add(entry.id);
    const schema = operatorClient[`${entry.target}Schema`];
    const validate = operatorClient[`is${entry.target}`];
    assert.ok(schema && validate, `target ${entry.target}`);
    const json = JSON.parse(JSON.stringify(entry.value));
    if (json.canonicalJson?.generatedBytes !== undefined) {
      json.canonicalJson = Buffer.alloc(json.canonicalJson.generatedBytes).toString("base64");
    }
    const value = fromJson(schema, json);
    assert.equal(validate(value), entry.valid, entry.id);
    if (entry.valid) {
      positives += 1;
      assert.equal(
        validate(fromBinary(schema, toBinary(schema, value))),
        true,
        `${entry.id} binary round trip`,
      );
    } else {
      negatives += 1;
    }
  }
  assert.ok(positives >= 20 && negatives >= 30, `positives=${positives} negatives=${negatives}`);
});

const SCALARS = {
  Key: ScalarType.STRING,
  Text: ScalarType.STRING,
  Hash: ScalarType.STRING,
  ReasonCode: ScalarType.STRING,
  bool: ScalarType.BOOL,
  uint64: ScalarType.UINT64,
  sint64: ScalarType.SINT64,
  bytes: ScalarType.BYTES,
};
const FOUNDATION = new Set([
  "Id",
  "Revision",
  "Instant",
  "AggregateRef",
  "Decimal",
  "PageRequest",
  "PageState",
  "Receipt",
  "TransferTicket",
  "ArcError",
  "RequestMeta",
]);
const PUBLICAPI = new Set(["SupportCase", "Grant", "CreditLot", "RefundView"]);
const CATALOG = new Set(["CatalogSubmissionView", "CatalogVersionView"]);
const OPERATOR_ENUMS = new Set([
  "OperatorProposalState",
  "OperatorRefundDecision",
  "OperatorGrantSource",
  "OperatorGrantKind",
  "SupportCaseState",
]);

function assertFields(desc, rows, label) {
  const expected = rows.map((row) => row.split(" ")).sort((a, b) => Number(a[0]) - Number(b[0]));
  assert.deepEqual(
    desc.fields.map((field) => field.number).sort((a, b) => a - b),
    expected.map(([number]) => Number(number)),
    `${label} exact field numbers`,
  );
  for (const [number, name, token] of expected) {
    const field = desc.fields.find((candidate) => candidate.number === Number(number));
    const where = `${label}.${name}`;
    const repeated = token.endsWith("[]");
    const base = token.replace(/[?]|\[\]/g, "");
    assert.equal(field.jsonName, name, `${where} JSON name`);
    assert.equal(field.fieldKind === "list", repeated, `${where} repeated`);
    const element = repeated ? field.listKind : field.fieldKind;
    if (base in SCALARS) {
      assert.equal(element, "scalar", where);
      assert.equal(field.scalar, SCALARS[base], `${where} scalar type`);
    } else if (OPERATOR_ENUMS.has(base) || base === "CatalogReviewDecision") {
      assert.equal(element, "enum", where);
      const owner =
        base === "CatalogReviewDecision" ? "arcforges.catalog.v1." : "arcforges.operator.v1.";
      assert.equal(field.enum.typeName, owner + base, `${where} enum type`);
    } else {
      const owner = FOUNDATION.has(base)
        ? "arcforges.foundation.v1."
        : PUBLICAPI.has(base)
          ? "arcforges.publicapi.v1."
          : CATALOG.has(base)
            ? "arcforges.catalog.v1."
            : "arcforges.operator.v1.";
      assert.equal(element, "message", where);
      assert.equal(field.message.typeName, owner + base, `${where} message type`);
    }
    if (!repeated && element !== "message" && !field.oneof) {
      assert.equal(field.proto.proto3Optional, true, `${where} explicit presence`);
    }
  }
}

test("CON.14 records, method requests, values and enums equal the Registry04 field tables", () => {
  const oracle = fixture.registryOracle;
  assert.equal(Object.keys(oracle.records).length, 18);
  for (const [name, rows] of Object.entries(oracle.records)) {
    assertFields(operatorClient[`${name}Schema`], rows, name);
  }
  assert.deepEqual(Object.keys(oracle.methods), METHODS);
  for (const [name, entry] of Object.entries(oracle.methods)) {
    const method = service.methods.find((candidate) => candidate.name === name);
    assertFields(method.input, ["1 meta RequestMeta", ...entry.request], `${name}Request`);
    const value = method.output.fields.find((field) => field.number === 2).message;
    assert.equal(value.typeName, `${OPERATOR_SERVICE}${name}Value`);
    assertFields(value, entry.value, `${name}Value`);
  }
  assert.deepEqual(Object.keys(oracle.enums), [
    "OperatorProposalState",
    "OperatorRefundDecision",
    "OperatorGrantSource",
    "OperatorGrantKind",
    "SupportCaseState",
  ]);
  for (const [name, values] of Object.entries(oracle.enums)) {
    const prefix = name.replace(/([a-z])([A-Z])/g, "$1_$2").toUpperCase();
    const camel = (value) => value.replace(/([a-z])([A-Z])/g, "$1_$2").toUpperCase();
    const desc = operatorClient[`${name}Schema`];
    assert.deepEqual(
      desc.values.map((value) => [value.name, value.number]),
      [
        [`${prefix}_UNSPECIFIED`, 0],
        ...values.map((value, index) => [`${prefix}_${camel(value)}`, index + 1]),
      ],
      `${name} enum names and numbers`,
    );
  }
});

test("CON.14 AdjustCredit delta is sint64 ZigZag on the wire", () => {
  const schema = operatorClient.OperatorAdjustCreditInputSchema;
  const field = schema.fields.find((candidate) => candidate.number === 2);
  assert.equal(field.scalar, ScalarType.SINT64);
  const bytes = toBinary(schema, fromJson(schema, { deltaMicro: "-1" }));
  // field 2, varint, ZigZag(-1) = 1; an int64 encoding would be a 10-byte two's-complement varint.
  assert.deepEqual([...bytes], [0x10, 0x01]);
  assert.equal(fromBinary(schema, bytes).deltaMicro, -1n);
});
