// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fromJson, fromBinary, toBinary } from "@bufbuild/protobuf";
import { contractServices } from "../../src/public/ts/proto/dist/services/gen/catalog.js";
import { PageRequestSchema } from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import {
  AstNodeSchema,
  CsvReplaySchemaSchema,
  FaultSpecSchema,
  GeneratorSpecSchema,
  PulseSpecSchema,
  ScenarioSpecSchema,
  SimulationProfileSchema,
  SimulationRunSchema,
  StepPointSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/simulation/v1/simulation_pb.js";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/con-21-simulation.json", import.meta.url), "utf8"),
);
const operationMetadata = JSON.parse(
  readFileSync(new URL("../../eng/operations/con-21.json", import.meta.url), "utf8"),
);
const generatorRequiredFieldsByKind = new Map([
  ["constant", ["offset"]],
  ["sine", ["offset", "amplitude", "frequencyHz", "phaseCycles"]],
  ["square", ["offset", "amplitude", "frequencyHz", "phaseCycles", "dutyRatio"]],
  ["triangle", ["offset", "amplitude", "frequencyHz", "phaseCycles"]],
  ["sawtooth", ["offset", "amplitude", "frequencyHz", "phaseCycles"]],
  ["noise", ["offset", "amplitude"]],
  ["randomWalk", ["offset", "walkStep"]],
  ["pulse", ["offset", "pulses"]],
  ["stepSequence", ["offset", "steps"]],
  ["csv", []],
]);
const generatorParameterFields = ["offset", "amplitude", "frequencyHz", "phaseCycles", "dutyRatio", "walkStep", "pulses", "steps"];

function tryShape(schema, validate, value) {
  try {
    return validate(fromJson(schema, value));
  } catch {
    return false;
  }
}

function generatorParametersValid(value) {
  const expectedFields = generatorRequiredFieldsByKind.get(value.kind);
  if (expectedFields === undefined) return false;
  const actualFields = Object.keys(value).filter((field) => field !== "channelId" && field !== "kind").sort();
  const sortedExpectedFields = [...expectedFields].sort();
  if (
    actualFields.length !== sortedExpectedFields.length ||
    actualFields.some((field, index) => field !== sortedExpectedFields[index])
  ) {
    return false;
  }
  if (["pulse", "stepSequence"].includes(value.kind)) {
    const list = value.kind === "pulse" ? value.pulses : value.steps;
    if (!Array.isArray(list) || list.length === 0) return false;
  }
  if (
    ["sine", "square", "triangle", "sawtooth"].includes(value.kind) &&
    (!Object.hasOwn(value, "frequencyHz") ||
      !Number.isFinite(value.frequencyHz) ||
      value.frequencyHz <= 0)
  ) {
    return false;
  }
  if (
    value.kind === "square" &&
    (!Object.hasOwn(value, "dutyRatio") ||
      !Number.isFinite(value.dutyRatio) ||
      value.dutyRatio <= 0 ||
      value.dutyRatio >= 1)
  ) {
    return false;
  }
  return true;
}

test("generated SimulationService catalogue is exactly the independent 13-operation fixture", () => {
  assert.equal(fixture.operationCount, 13);
  assert.equal(new Set(fixture.operations.map((item) => item.operationId)).size, 13);
  assert.deepEqual(
    fixture.operations.map((item) => item.method),
    [
      "ListDefinitions",
      "GetDefinition",
      "CreateDefinition",
      "PublishScenarioVersion",
      "StartRun",
      "PauseRun",
      "ResumeRun",
      "CancelRun",
      "GetRun",
      "ListRuns",
      "ListSegments",
      "GetSegmentTicket",
      "PollState",
    ],
  );
  assert.equal(operationMetadata.operations.length, fixture.operationCount);
  const service = contractServices.find((item) => item.typeName === fixture.service);
  assert.ok(
    service,
    "SimulationService is registered in the generated TypeScript package catalogue",
  );
  const expected = fixture.operations.map(
    (item) => item.method[0].toLowerCase() + item.method.slice(1),
  );
  assert.deepEqual(
    service.methods.map((item) => item.name),
    expected,
  );

  for (const item of fixture.operations) {
    const metadata = operationMetadata.operations.find(
      (row) => row.operationId === item.operationId,
    );
    assert.ok(metadata, `operation scope row exists for ${item.operationId}`);
    const profile = fixture.operationProfile;
    assert.equal(metadata.binding, `${fixture.service}/${item.method}`);
    for (const key of ["kind", "source", "scope", "surface", "profile", "sourceRule"]) {
      assert.equal(metadata[key], profile[key], `${item.operationId}: ${key}`);
    }
    assert.equal(metadata.idempotency, item.class, `${item.operationId}: idempotency`);
    const expectedRisk = item.class === "Q" || item.class === "NI" ? "R1" : "R2";
    const expectedCompatibility = item.class === "Q" ? "AO" : "FR";
    assert.equal(item.risk, expectedRisk, `${item.operationId}: risk`);
    assert.equal(item.compatibility, expectedCompatibility, `${item.operationId}: compatibility`);
    assert.deepEqual(
      metadata.authorization,
      {
        capability: profile.capability,
        risk: item.risk,
        approval: profile.approval,
        stepUp: profile.stepUp,
        localPresence: profile.localPresence,
        egress: profile.egress,
        patEligible: profile.patEligible,
        actorKinds: profile.actorKinds,
      },
      `${item.operationId}: exact authorization`,
    );
  }
});

test("profile, run state/extent and AST vectors pass through generated closed shapes", () => {
  assert.deepEqual(
    fixture.profile.vectors.map((item) => item.id),
    [
      "minimum-profile",
      "maximum-batch-profile",
      "zero-sample-count-refused",
      "zero-batch-refused",
      "oversized-batch-refused",
      "zero-rate-denominator-refused",
      "unsupported-execution-profile-refused",
    ],
  );
  for (const item of fixture.profile.vectors) {
    const value = item.value;
    const valid = tryShape(SimulationProfileSchema, shapes.isSimulationProfile, value);
    assert.equal(valid, item.valid, item.id);
    if (!valid) continue;
    const message = fromJson(SimulationProfileSchema, value);
    const bytes = toBinary(SimulationProfileSchema, message);
    assert.deepEqual(
      toBinary(SimulationProfileSchema, fromBinary(SimulationProfileSchema, bytes)),
      bytes,
      item.id,
    );
  }

  const states = new Set(fixture.states);
  const extents = new Set(fixture.extents);
  assert.deepEqual(fixture.stateRejected, ["active", "completed", "cancelled", "unknown"]);
  assert.deepEqual(fixture.extentRejected, ["terminal", "full", "unknown"]);
  assert.equal(
    fixture.stateRejected.some((value) => states.has(value)),
    false,
  );
  assert.equal(
    fixture.extentRejected.some((value) => extents.has(value)),
    false,
  );
  assert.deepEqual(
    fixture.runExtentVectors.map((item) => item.id),
    [
      "active-partial-prefix",
      "succeeded-complete-range",
      "canceled-partial-range",
      "unknown-state-refused",
      "unsupported-extent-refused",
    ],
  );
  for (const item of fixture.runExtentVectors) {
    const valid = tryShape(SimulationRunSchema, shapes.isSimulationRun, {
      ...fixture.runShapeBase,
      state: item.state,
      extent: item.extent,
      logicalEnd: item.logicalEnd,
    });
    assert.equal(valid, item.valid, item.id);
  }

  assert.deepEqual(
    fixture.astVectors.map((item) => item.id),
    [
      "constant-expression",
      "variable-expression",
      "unary-expression",
      "binary-expression",
      "function-expression",
      "unrecognized-expression",
      "missing-expression",
      "multiple-oneof-arms-refused",
    ],
  );
  for (const item of fixture.astVectors) {
    const valid = tryShape(AstNodeSchema, shapes.isAstNode, item.value);
    assert.equal(valid, item.valid, item.id);
  }
});

test("Registry04 scalar presence and optionality vectors use generated simulation shapes", () => {
  const vectors = fixture.presenceVectors;
  const groups = [
    [
      "pulseSpec",
      PulseSpecSchema,
      shapes.isPulseSpec,
      ["pulse-value-zero-present", "pulse-missing-value-refused"],
    ],
    [
      "stepPoint",
      StepPointSchema,
      shapes.isStepPoint,
      ["step-value-zero-present", "step-missing-value-refused"],
    ],
    [
      "faultSpec",
      FaultSpecSchema,
      shapes.isFaultSpec,
      [
        "fault-channel-omitted-accepted",
        "fault-missing-everyTicks-refused",
        "fault-missing-probabilityPpm-refused",
        "fault-reorder-window-minimum-accepted",
        "fault-reorder-window-maximum-accepted",
        "fault-reorder-window-zero-refused",
        "fault-reorder-window-1025-refused",
      ],
    ],
    [
      "csvReplaySchema",
      CsvReplaySchemaSchema,
      shapes.isCsvReplaySchema,
      [
        "csv-timestampUnit-omitted-accepted",
        "csv-tab-delimiter-accepted",
        "csv-semicolon-delimiter-accepted",
        "csv-unsupported-encoding-refused",
        "csv-unsupported-delimiter-refused",
        "csv-4096-columns-accepted",
        "csv-4097-columns-refused",
      ],
    ],
  ];
  for (const [key, schema, validate, expectedIds] of groups) {
    const entries = vectors[key];
    assert.deepEqual(
      entries.map((item) => item.id),
      expectedIds,
      `${key}: exact presence vectors`,
    );
    for (const item of entries) {
      const value =
        key === "csvReplaySchema"
          ? {
              ...item.value,
              columns: Array.from(
                { length: item.columnsCount ?? item.value.columns.length },
                (_, column) => ({ ...fixture.csvColumnTemplate, column }),
              ),
            }
          : item.value;
      const valid = tryShape(schema, validate, value);
      assert.equal(valid, item.valid, item.id);
      if (!valid) continue;
      const message = fromJson(schema, value);
      const bytes = toBinary(schema, message);
      assert.deepEqual(
        toBinary(schema, fromBinary(schema, bytes)),
        bytes,
        `${item.id}: binary round-trip`,
      );
    }
  }

  const generatorVectors = fixture.generatorParameterVectors;
  assert.deepEqual(
    generatorVectors.map((item) => item.id),
    [
      "constant-frequency-omitted-accepted",
      "sine-frequency-minimum-positive-accepted",
      "sine-frequency-zero-refused",
      "sine-frequency-omitted-refused-by-kind",
      "triangle-frequency-positive-accepted",
      "sawtooth-frequency-positive-accepted",
      "square-duty-minimum-positive-accepted",
      "square-duty-zero-refused",
      "square-duty-maximum-below-one-accepted",
      "square-duty-one-refused",
      "square-duty-omitted-refused-by-kind",
      "sine-duty-omitted-accepted",
    ],
  );
  for (const item of generatorVectors) {
    const shapeValid = tryShape(GeneratorSpecSchema, shapes.isGeneratorSpec, item.value);
    assert.equal(shapeValid, item.shapeValid, `${item.id}: generated shape`);
    assert.equal(
      generatorParametersValid(item.value),
      item.parameterValid,
      `${item.id}: kind-specific parameters`,
    );
  }

  const parameterMatrix = fixture.generatorParameterMatrix;
  assert.deepEqual(
    parameterMatrix.map(({ id, kind, requiredFields }) => [id, kind, requiredFields]),
    [
      ["constant-exact-parameters", "constant", ["offset"]],
      ["sine-exact-parameters", "sine", ["offset", "amplitude", "frequencyHz", "phaseCycles"]],
      ["square-exact-parameters", "square", ["offset", "amplitude", "frequencyHz", "phaseCycles", "dutyRatio"]],
      ["triangle-exact-parameters", "triangle", ["offset", "amplitude", "frequencyHz", "phaseCycles"]],
      ["sawtooth-exact-parameters", "sawtooth", ["offset", "amplitude", "frequencyHz", "phaseCycles"]],
      ["noise-exact-parameters", "noise", ["offset", "amplitude"]],
      ["random-walk-exact-parameters", "randomWalk", ["offset", "walkStep"]],
      ["pulse-exact-parameters", "pulse", ["offset", "pulses"]],
      ["step-sequence-exact-parameters", "stepSequence", ["offset", "steps"]],
      ["csv-exact-parameters", "csv", []],
    ],
  );
  const parameterValues = new Map(parameterMatrix.map((item) => [item.kind, item.value]));
  const fieldExamples = Object.fromEntries(
    generatorParameterFields.map((field) => [field, parameterMatrix.find((item) => Object.hasOwn(item.value, field)).value[field]]),
  );
  for (const item of parameterMatrix) {
    assert.equal(item.value.kind, item.kind, `${item.id}: kind binding`);
    assert.deepEqual(item.requiredFields, generatorRequiredFieldsByKind.get(item.kind), `${item.id}: required-field oracle`);
    assert.equal(tryShape(GeneratorSpecSchema, shapes.isGeneratorSpec, item.value), true, `${item.id}: generated shape`);
    assert.equal(generatorParametersValid(item.value), true, `${item.id}: exact kind parameters`);
    const bytes = toBinary(GeneratorSpecSchema, fromJson(GeneratorSpecSchema, item.value));
    assert.deepEqual(toBinary(GeneratorSpecSchema, fromBinary(GeneratorSpecSchema, bytes)), bytes, `${item.id}: binary round-trip`);
    for (const field of item.requiredFields) {
      const missing = structuredClone(item.value);
      delete missing[field];
      assert.equal(generatorParametersValid(missing), false, `${item.id}: missing ${field}`);
    }
    for (const field of generatorParameterFields.filter((field) => !item.requiredFields.includes(field))) {
      const unrelated = structuredClone(item.value);
      unrelated[field] = structuredClone(fieldExamples[field]);
      assert.equal(generatorParametersValid(unrelated), false, `${item.id}: unrelated ${field}`);
    }
    if (item.kind === "pulse" || item.kind === "stepSequence") {
      const empty = structuredClone(item.value);
      empty[item.kind === "pulse" ? "pulses" : "steps"] = [];
      assert.equal(generatorParametersValid(empty), false, `${item.id}: empty repeated list is not supplied`);
    }
  }

  const csvMappingVectors = fixture.csvGeneratorMappingVectors;
  assert.deepEqual(csvMappingVectors.map((item) => item.id), [
    "csv-source-and-schema-present-accepted",
    "csv-source-omitted-refused",
    "csv-schema-omitted-refused",
    "csv-source-and-schema-omitted-refused",
  ]);
  const csvScenario = fixture.csvScenarioTemplate;
  const csvGenerator = parameterValues.get("csv");
  for (const item of csvMappingVectors) {
    const value = {
      duration: csvScenario.duration,
      executionProfile: csvScenario.executionProfile,
      generators: [csvGenerator],
      ...(item.sourcePresent ? { csv: csvScenario.source } : {}),
      ...(item.schemaPresent ? { csvSchema: csvScenario.schema } : {}),
    };
    const shapeValid = tryShape(ScenarioSpecSchema, shapes.isScenarioSpec, value);
    assert.equal(shapeValid, item.shapeValid, `${item.id}: generated scenario shape`);
    assert.equal(Object.hasOwn(value, "csv"), item.sourcePresent, `${item.id}: CSV source field presence`);
    assert.equal(Object.hasOwn(value, "csvSchema"), item.schemaPresent, `${item.id}: CSV schema field presence`);
    const parameterValid = generatorParametersValid(csvGenerator) && item.sourcePresent && item.schemaPresent;
    assert.equal(parameterValid, item.parameterValid, `${item.id}: CSV source/schema mapping`);
    if (shapeValid) {
      const bytes = toBinary(ScenarioSpecSchema, fromJson(ScenarioSpecSchema, value));
      assert.deepEqual(toBinary(ScenarioSpecSchema, fromBinary(ScenarioSpecSchema, bytes)), bytes, `${item.id}: binary round-trip`);
    }
  }
});

test("listRuns page bounds and workspace snapshot declarations are exact", () => {
  assert.deepEqual(
    fixture.listRuns.pageLimits.map((item) => item.id),
    ["default", "minimum", "maximum", "zero", "above-maximum"],
  );
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
  assert.deepEqual(pageStateBinds, [
    "realm",
    "workspace",
    "actor",
    "recoveryGeneration",
    "filters",
    "sort",
    "schema",
    "snapshot",
  ]);
  assert.equal(fixture.listRuns.includesRetainedPartialAndTerminalRuns, true);
  assert.equal(fixture.listRuns.requiresKnownRunId, false);
  assert.equal(fixture.listRuns.requiresTerminalNotification, false);
});
