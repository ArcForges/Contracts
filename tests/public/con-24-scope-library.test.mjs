// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const fixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/public/con-24-scope-library.json", import.meta.url),
    "utf8",
  ),
);
const operations = JSON.parse(
  await readFile(new URL("../../eng/operations/con-24.json", import.meta.url), "utf8"),
).operations;
const expectedIds = [
  "projects-use-project-metadata-and-visible-live-sessions-in-one-snapshot",
  "projects-order-equal-commit-times-by-project-id-descending",
  "sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate",
  "sessions-missing-or-hidden-project-returns-not-found",
  "sessions-next-page-rechecks-current-access",
  "get-session-returns-only-committed-metadata-with-cloud-revision-and-time",
  "get-session-unresolved-parent-is-not-reassigned-or-exposed",
  "get-session-tombstone-returns-gone",
  "projects-order-updated-at-primary-before-project-id",
  "sessions-order-updated-at-then-session-id-descending",
];

function fieldNames(message) {
  return message.fields.map((field) => [field.jsonName, field.number]);
}

function messageType(field) {
  return field.fieldKind.case === "message" ? field.fieldKind.message.typeName : undefined;
}

function compareDescending(left, right) {
  return left === right ? 0 : left > right ? -1 : 1;
}

function compareUpdatedAtDescending(left, right) {
  return (
    compareDescending(BigInt(left.unixSeconds), BigInt(right.unixSeconds)) ||
    compareDescending(left.nanos, right.nanos)
  );
}

function orderByUpdatedAtThenIdDescending(rows, idField) {
  return [...rows].sort(
    (left, right) =>
      compareUpdatedAtDescending(left.updatedAt, right.updatedAt) ||
      compareDescending(left[idField], right[idField]),
  );
}

test("CON.24 operation bindings match the fixture RPCs without generated outputs", () => {
  assert.equal(fixture.operations.length, 3);
  assert.equal(operations.length, 3);
  for (const row of operations) {
    const operation = fixture.operations.find(
      (candidate) => candidate.operationId === row.operationId,
    );
    assert.ok(operation, `${row.operationId}: fixture operation exists`);
    const methodName = operation.rpc.split("/")[1];
    assert.equal(row.binding, `arcforges.publicapi.v1.ScopeService/${methodName}`);
    assert.equal(row.source, "public/proto/arcforges/publicapi/v1/scope.proto");
  }
});

test("CON.24 generated Scope API and operation authorization match the public fixture", async () => {
  const { ScopeService } =
    await import("../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/scope_pb.js");
  const { ScopeProjectSummarySchema, ScopeSessionSummarySchema } =
    await import("../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js");
  assert.equal(fixture.evidenceClass, "offline-contract-only-no-owner-service-or-live-workspace");
  assert.deepEqual(fixture.authorization, {
    scope: "product-owner",
    risk: "R1",
    idempotency: "Q",
    compatibility: "AO",
    capability: null,
    approval: "none",
    stepUp: false,
    localPresence: false,
    egress: "none",
    patEligible: false,
    actorKinds: ["human"],
  });

  assert.equal(ScopeService.typeName, "arcforges.publicapi.v1.ScopeService");
  assert.deepEqual(
    fixture.operations.map((operation) => operation.rpc),
    ["ScopeService/ListProjects", "ScopeService/ListSessions", "ScopeService/GetSession"],
  );
  assert.deepEqual(
    ScopeService.methods.map((method) => method.name),
    ["ListProjects", "ListSessions", "GetSession"],
  );
  for (const method of ScopeService.methods) {
    assert.equal(method.methodKind, "unary");
    assert.equal(method.input.fields.find((field) => field.number === 1)?.name, "meta");
    assert.equal(
      messageType(method.input.fields.find((field) => field.number === 1)),
      "arcforges.foundation.v1.RequestMeta",
    );
    assert.equal(
      messageType(method.output.fields.find((field) => field.number === 1)),
      "arcforges.foundation.v1.ResponseMeta",
    );
    assert.ok(method.input.fields.every((field) => field.number === 1 || field.number >= 10));
    assert.deepEqual(
      method.output.fields.filter((field) => field.number >= 2).map((field) => field.number),
      [2, 3, 4],
    );
    assert.ok(
      method.output.fields
        .filter((field) => field.number >= 2)
        .every((field) => field.oneof?.name === "outcome"),
    );
    assert.equal(
      messageType(method.output.fields.find((field) => field.number === 4)),
      "arcforges.foundation.v1.EncodedBodyRef",
    );
  }
  assert.deepEqual(fieldNames(ScopeProjectSummarySchema), [
    ["projectId", 1],
    ["name", 2],
    ["sessionCount", 3],
    ["updatedAt", 4],
    ["revision", 5],
  ]);
  assert.deepEqual(fieldNames(ScopeSessionSummarySchema), [
    ["sessionId", 1],
    ["projectId", 2],
    ["name", 3],
    ["findingCount", 4],
    ["reportCount", 5],
    ["tags", 6],
    ["updatedAt", 7],
    ["revision", 8],
  ]);
  assert.deepEqual(operations.map((row) => row.operationId).sort(), [
    "scope.getSession",
    "scope.listProjects",
    "scope.listSessions",
  ]);
  assert.equal(fixture.operations.length, 3);
  for (const operation of fixture.operations) {
    const methodName = operation.rpc.split("/")[1];
    const method = ScopeService.methods.find((candidate) => candidate.name === methodName);
    assert.ok(method, `${operation.operationId}: generated RPC exists`);
    assert.equal(method.input.typeName, `arcforges.publicapi.v1.${operation.requestType}`);
    assert.deepEqual(
      method.input.fields.map((field) => field.jsonName),
      operation.requestFields,
    );
    const valueField = method.output.fields.find((field) => field.number === 2);
    assert.equal(messageType(valueField), `arcforges.publicapi.v1.${operation.valueType}`);
    assert.deepEqual(
      valueField.fieldKind.message.fields.map((field) => field.jsonName),
      operation.valueFields,
    );
    assert.equal(method.output.typeName, `arcforges.publicapi.v1.${operation.responseType}`);
    assert.deepEqual(
      method.output.fields.filter((field) => field.number >= 2).map((field) => field.jsonName),
      operation.outcomeFields,
    );
  }
  for (const row of operations) {
    const operation = fixture.operations.find(
      (candidate) => candidate.operationId === row.operationId,
    );
    assert.ok(operation, `${row.operationId}: fixture operation exists`);
    const methodName = operation.rpc.split("/")[1];
    assert.equal(row.binding, `${ScopeService.typeName}/${methodName}`);
    assert.equal(row.source, "public/proto/arcforges/publicapi/v1/scope.proto");
    assert.equal(row.scope, fixture.authorization.scope);
    assert.equal(row.surface, "public");
    assert.equal(row.profile, "human-owner");
    assert.equal(row.idempotency, fixture.authorization.idempotency);
    assert.deepEqual(row.authorization, {
      capability: fixture.authorization.capability,
      risk: fixture.authorization.risk,
      approval: fixture.authorization.approval,
      stepUp: fixture.authorization.stepUp,
      localPresence: fixture.authorization.localPresence,
      egress: fixture.authorization.egress,
      patEligible: fixture.authorization.patEligible,
      actorKinds: fixture.authorization.actorKinds,
    });
  }
});

test("CON.24 public vectors are consumed exactly once with their independent expected facts", () => {
  const vectors = fixture.vectors;
  const ids = vectors.map((vector) => vector.id);
  assert.equal(new Set(ids).size, ids.length, "vector ids are unique");
  assert.deepEqual(
    [...ids].sort(),
    [...expectedIds].sort(),
    "only the ten authorized vectors exist",
  );
  const consumed = new Set();
  for (const vector of vectors) {
    assert.ok(!consumed.has(vector.id), `duplicate consumption: ${vector.id}`);
    consumed.add(vector.id);
    switch (vector.id) {
      case expectedIds[0]: {
        assert.equal(vector.operationId, "scope.listProjects");
        assert.equal(vector.expected.projectIdHex, vector.source.projectMetadata.projectIdHex);
        assert.equal(vector.expected.name, vector.source.projectMetadata.name);
        assert.equal(vector.expected.sessionCount, 2);
        assert.equal(
          vector.source.sessionsInListSnapshot.filter((session) => session.live && session.visible)
            .length,
          vector.expected.sessionCount,
        );
        assert.deepEqual(vector.expected.updatedAt, vector.source.projectUpdatedAt);
        assert.equal(vector.expected.revision, vector.source.projectRevision);
        assert.deepEqual(vector.expected.mustNotUse, ["session.name", "max(session.revision)"]);
        break;
      }
      case expectedIds[1]: {
        assert.equal(vector.operationId, "scope.listProjects");
        assert.equal(vector.source.projects.length, 3);
        assert.equal(
          new Set(
            vector.source.projects.map(
              (project) => `${project.updatedAt.unixSeconds}:${project.updatedAt.nanos}`,
            ),
          ).size,
          1,
          "the ordering vector must use equal commit times",
        );
        const derivedVisibleProjectIds = vector.source.projects
          .filter((project) => project.hasVisibleLiveSessions === true)
          .map((project) => project.projectIdHex)
          .sort((left, right) => (left === right ? 0 : left > right ? -1 : 1));
        assert.deepEqual(
          derivedVisibleProjectIds,
          vector.expectedProjectIdsHex,
          "expected project order derives from visible source projects",
        );
        assert.deepEqual(vector.expectedProjectIdsHex, [
          "00000000000000000000000000000002",
          "00000000000000000000000000000001",
        ]);
        assert.equal(
          vector.source.projects.filter((project) => project.hasVisibleLiveSessions).length,
          2,
        );
        break;
      }
      case expectedIds[2]: {
        assert.equal(vector.operationId, "scope.listSessions");
        const visible = vector.source.sessionsInListSnapshot.filter(
          (session) => session.live && session.visible,
        );
        assert.equal(visible.length, 1);
        assert.deepEqual(
          vector.expectedItems,
          visible.map(({ live, visible: _visible, ...row }) => row),
        );
        assert.equal(vector.expectedItems[0].findingCount, 2);
        assert.equal(vector.expectedItems[0].reportCount, 1);
        assert.deepEqual(vector.expectedItems[0].tagsHex, ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]);
        break;
      }
      case expectedIds[3]:
        assert.equal(vector.operationId, "scope.listSessions");
        assert.equal(vector.source.projectVisibleToOwner, false);
        assert.deepEqual(vector.expected, { errorCode: "state.not_found", itemsExposed: false });
        break;
      case expectedIds[4]:
        assert.equal(vector.operationId, "scope.listSessions");
        assert.equal(vector.source.accessRevokedAfterPreviousPage, true);
        assert.equal(vector.source.cursorBoundToPriorAuthorizedSnapshot, true);
        assert.deepEqual(vector.expected, {
          accessRecheckedOnThisRequest: true,
          priorSnapshotDoesNotRestoreRevokedAccess: true,
        });
        break;
      case expectedIds[5]:
        assert.equal(vector.operationId, "scope.getSession");
        assert.equal(vector.expected.sessionType, "ScopeMetadata");
        assert.equal(vector.expected.revision, 9);
        assert.deepEqual(vector.expected.committedAt, {
          unixSeconds: "1790593200",
          nanos: 500000000,
        });
        assert.equal(vector.expected.rawCaptureBytesPresent, false);
        break;
      case expectedIds[6]:
        assert.equal(vector.operationId, "scope.getSession");
        assert.equal(vector.source.parentProjectResolved, false);
        assert.equal(vector.source.parentProjectTombstoned, false);
        assert.deepEqual(vector.expected, {
          visible: false,
          errorCode: "state.not_found",
          reassigned: false,
        });
        break;
      case expectedIds[7]:
        assert.equal(vector.operationId, "scope.getSession");
        assert.equal(vector.source.sessionTombstoned, true);
        assert.deepEqual(vector.expected, { visible: false, errorCode: "state.gone" });
        break;
      case expectedIds[8]: {
        assert.equal(vector.operationId, "scope.listProjects");
        const sourceProjects = vector.source.projects;
        assert.equal(sourceProjects.length, 3);
        assert.ok(sourceProjects.every((project) => project.hasVisibleLiveSessions));
        assert.equal(
          new Set(
            sourceProjects.map(
              (project) => `${project.updatedAt.unixSeconds}:${project.updatedAt.nanos}`,
            ),
          ).size,
          3,
          "the primary-order vector uses distinct commit instants",
        );
        const actual = orderByUpdatedAtThenIdDescending(sourceProjects, "projectIdHex").map(
          (project) => project.projectIdHex,
        );
        assert.deepEqual(actual, vector.expectedProjectIdsHex);
        assert.deepEqual(actual, [
          "00000000000000000000000000000001",
          "00000000000000000000000000000002",
          "00000000000000000000000000000003",
        ]);
        break;
      }
      case expectedIds[9]: {
        assert.equal(vector.operationId, "scope.listSessions");
        const sourceRows = vector.source.sessionsInListSnapshot.filter(
          (session) => session.live && session.visible,
        );
        assert.equal(sourceRows.length, 4);
        const timestampKeys = sourceRows.map(
          (session) => `${session.updatedAt.unixSeconds}:${session.updatedAt.nanos}`,
        );
        assert.equal(new Set(timestampKeys).size, 3);
        assert.equal(
          timestampKeys.filter((key) => key === "1790593200:100000000").length,
          2,
          "the tie-break pair shares the exact updatedAt",
        );
        const actual = orderByUpdatedAtThenIdDescending(sourceRows, "sessionIdHex").map(
          (session) => session.sessionIdHex,
        );
        assert.deepEqual(actual, vector.expectedSessionIdsHex);
        assert.deepEqual(actual, [
          "00000000000000000000000000000001",
          "00000000000000000000000000000004",
          "00000000000000000000000000000002",
          "00000000000000000000000000000003",
        ]);
        break;
      }
      default:
        assert.fail(`unknown vector ${vector.id}`);
    }
  }
  assert.deepEqual(
    [...consumed].sort(),
    [...expectedIds].sort(),
    "every fixture vector is consumed once",
  );
});
