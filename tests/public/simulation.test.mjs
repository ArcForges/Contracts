// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fromJson, fromBinary, toBinary } from "@bufbuild/protobuf";
import { contractServices } from "../../src/public/ts/proto/dist/services/gen/catalog.js";
import { PageRequestSchema } from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import {
  AstNodeSchema,
  SimulationProfileSchema,
  SimulationRunSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/simulation/v1/simulation_pb.js";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/con-21-simulation.json", import.meta.url), "utf8"),
);
const operationMetadata = JSON.parse(
  readFileSync(new URL("../../eng/operations/con-21.json", import.meta.url), "utf8"),
);

function tryShape(schema, validate, value) {
  try {
    return validate(fromJson(schema, value));
  } catch {
    return false;
  }
}

test("generated SimulationService catalogue is exactly the independent 13-operation fixture", () => {
  assert.equal(fixture.operationCount, 13);
  assert.equal(new Set(fixture.operations.map((item) => item.operationId)).size, 13);
  assert.deepEqual(fixture.operations.map((item) => item.method), [
    "ListDefinitions", "GetDefinition", "CreateDefinition", "PublishScenarioVersion", "StartRun", "PauseRun",
    "ResumeRun", "CancelRun", "GetRun", "ListRuns", "ListSegments", "GetSegmentTicket", "PollState",
  ]);
  assert.equal(operationMetadata.operations.length, fixture.operationCount);
  const service = contractServices.find((item) => item.typeName === fixture.service);
  assert.ok(service, "SimulationService is registered in the generated TypeScript package catalogue");
  const expected = fixture.operations.map((item) => item.method[0].toLowerCase() + item.method.slice(1));
  assert.deepEqual(service.methods.map((item) => item.name), expected);

  for (const item of fixture.operations) {
    const metadata = operationMetadata.operations.find((row) => row.operationId === item.operationId);
    assert.ok(metadata, `operation scope row exists for ${item.operationId}`);
    const profile = fixture.operationProfile;
    assert.equal(metadata.binding, `${fixture.service}/${item.method}`);
    for (const key of ["kind", "source", "scope", "surface", "profile", "sourceRule"]) {
      assert.equal(metadata[key], profile[key], `${item.operationId}: ${key}`);
    }
    assert.equal(metadata.idempotency, item.class, `${item.operationId}: idempotency`);
    assert.deepEqual(metadata.authorization, {
      capability: profile.capability,
      risk: item.risk,
      approval: profile.approval,
      stepUp: profile.stepUp,
      localPresence: profile.localPresence,
      egress: profile.egress,
      patEligible: profile.patEligible,
      actorKinds: profile.actorKinds,
    }, `${item.operationId}: exact authorization`);
  }
});

test("profile, run state/extent and AST vectors pass through generated closed shapes", () => {
  assert.deepEqual(fixture.profile.vectors.map((item) => item.id), [
    "minimum-profile", "maximum-batch-profile", "zero-sample-count-refused", "zero-batch-refused",
    "oversized-batch-refused", "zero-rate-denominator-refused", "unsupported-execution-profile-refused",
  ]);
  for (const item of fixture.profile.vectors) {
    const value = item.value;
    const valid = tryShape(SimulationProfileSchema, shapes.isSimulationProfile, value);
    assert.equal(valid, item.valid, item.id);
    if (!valid) continue;
    const message = fromJson(SimulationProfileSchema, value);
    const bytes = toBinary(SimulationProfileSchema, message);
    assert.deepEqual(toBinary(SimulationProfileSchema, fromBinary(SimulationProfileSchema, bytes)), bytes, item.id);
  }

  const states = new Set(fixture.states);
  const extents = new Set(fixture.extents);
  assert.deepEqual(fixture.stateRejected, ["active", "completed", "cancelled", "unknown"]);
  assert.deepEqual(fixture.extentRejected, ["terminal", "full", "unknown"]);
  assert.equal(fixture.stateRejected.some((value) => states.has(value)), false);
  assert.equal(fixture.extentRejected.some((value) => extents.has(value)), false);
  assert.deepEqual(fixture.runExtentVectors.map((item) => item.id), [
    "active-partial-prefix", "succeeded-complete-range", "canceled-partial-range", "unknown-state-refused", "unsupported-extent-refused",
  ]);
  for (const item of fixture.runExtentVectors) {
    const valid = tryShape(SimulationRunSchema, shapes.isSimulationRun, {
      ...fixture.runShapeBase,
      state: item.state,
      extent: item.extent,
      logicalEnd: item.logicalEnd,
    });
    assert.equal(valid, item.valid, item.id);
  }

  assert.deepEqual(fixture.astVectors.map((item) => item.id), [
    "constant-expression", "variable-expression", "unary-expression", "binary-expression", "function-expression",
    "unrecognized-expression", "missing-expression", "multiple-oneof-arms-refused",
  ]);
  for (const item of fixture.astVectors) {
    const valid = tryShape(AstNodeSchema, shapes.isAstNode, item.value);
    assert.equal(valid, item.valid, item.id);
  }
});

test("listRuns page bounds and workspace snapshot declarations are exact", () => {
  assert.deepEqual(fixture.listRuns.pageLimits.map((item) => item.id), ["default", "minimum", "maximum", "zero", "above-maximum"]);
  for (const item of fixture.listRuns.pageLimits) {
    const value = item.limit === null ? {} : { limit: item.limit };
    assert.equal(tryShape(PageRequestSchema, shapes.isPageRequest, value), item.valid, item.id);
  }
  const { authorization, filters, order, pageStateBinds } = fixture.listRuns;
  assert.deepEqual(authorization, {
    membership: "current-workspace",
    role: "read",
    productId: "arcscope",
    recheckEveryPage: true,
  });
  assert.deepEqual(filters, ["exact scenarioVersionId", "exact simulation_run state"]);
  assert.deepEqual(order, ["createdAt descending", "runId descending"]);
  assert.deepEqual(pageStateBinds, ["realm", "workspace", "actor", "recoveryGeneration", "filters", "sort", "schema", "snapshot"]);
  assert.equal(fixture.listRuns.includesRetainedPartialAndTerminalRuns, true);
  assert.equal(fixture.listRuns.requiresKnownRunId, false);
  assert.equal(fixture.listRuns.requiresTerminalNotification, false);
});
