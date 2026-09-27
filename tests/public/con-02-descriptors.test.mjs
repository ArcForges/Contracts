// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import * as foundation from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import {
  ContextProviderSchema,
  ContextDescriptorSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/descriptors_pb.js";
import { SayHelloResponseSchema } from "../../src/public/ts/proto/dist/gen/arcforges/hello/v1/hello_pb.js";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";
import { readEncodedBody } from "../../src/public/ts/proto/dist/encoded-body.js";
import { wireLimits } from "../../src/public/ts/proto/dist/wire.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/con-02-descriptors.json", import.meta.url), "utf8"),
);
test("independent exact field/enum wire vectors round-trip", () => {
  for (const [key, schema, validate] of [
    ["operationBinding", foundation.OperationBindingSchema, shapes.isOperationBinding],
    ["actionDescriptor", foundation.ActionDescriptorSchema, shapes.isActionDescriptor],
    ["contextProvider", ContextProviderSchema, shapes.isContextProvider],
    ["featureSet", foundation.FeatureSetSchema, shapes.isFeatureSet],
  ]) {
    const bytes = Buffer.from(fixture.wire[key], "hex");
    const message = fromBinary(schema, bytes);
    assert.equal(validate(message), true, key);
    assert.deepEqual(Buffer.from(toBinary(schema, message)), bytes);
  }
  const binding = fromBinary(
    foundation.OperationBindingSchema,
    Buffer.from(fixture.wire.operationBinding, "hex"),
  );
  assert.equal(binding.protocol, 6);
  binding.protocol = 99;
  assert.equal(shapes.isOperationBinding(binding), false);
});
test("canonical SemVer keeps exact build identity and compares unbounded integer precedence", () => {
  for (const version of fixture.validVersions)
    assert.equal(
      shapes.isContractVersion(
        create(foundation.ContractVersionSchema, { key: "foundation", version }),
      ),
      true,
      version,
    );
  for (const version of [...fixture.invalidVersions, "1.0.0+" + "x".repeat(123)])
    assert.equal(
      shapes.isContractVersion(
        create(foundation.ContractVersionSchema, { key: "foundation", version }),
      ),
      false,
      version,
    );
  for (const row of fixture.compatibility) {
    const contract = { key: "foundation", version: row.version };
    assert.equal(
      shapes.isContractCompatibility(
        create(foundation.ContractCompatibilitySchema, {
          contract,
          minReadable: row.minimum,
          minWritable: row.minimum,
        }),
      ),
      row.valid,
      JSON.stringify(row),
    );
  }
  assert.equal(
    shapes.isContractVersion(
      create(foundation.ContractVersionSchema, { key: "not+key", version: "1.0.0+build" }),
    ),
    false,
  );
});
test("descriptor bounds, uniqueness and distinct health/readiness are enforced", () => {
  const provider = fromBinary(
    ContextProviderSchema,
    Buffer.from(fixture.wire.contextProvider, "hex"),
  );
  provider.maxItems = 201;
  assert.equal(shapes.isContextProvider(provider), false);
  provider.maxItems = 1;
  provider.maxBytes = 262145;
  assert.equal(shapes.isContextProvider(provider), false);
  assert.equal(
    shapes.isFeatureSet(create(foundation.FeatureSetSchema, { features: ["a", "a"] })),
    false,
  );
  assert.equal(
    shapes.isInstanceReadiness(
      create(foundation.InstanceReadinessSchema, { acceptsWork: false, reasons: [] }),
    ),
    true,
  );
  const contract = {
    contract: { key: "k", version: "1.0.0" },
    minReadable: "1.0.0",
    minWritable: "1.0.0",
  };
  assert.equal(
    shapes.isCompatibilityDescriptor(
      create(foundation.CompatibilityDescriptorSchema, {
        foundation: contract,
        contracts: [contract, contract],
        capabilities: [],
        features: { features: [] },
      }),
    ),
    false,
  );
});

const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const id = {
  value: Uint8Array.from([0, 17, 34, 51, 68, 85, 102, 119, 136, 153, 170, 187, 204, 221, 238, 255]),
};
test("capability effects and nested context/health dimensions retain their constraints", () => {
  const roundTrip = (schema, value) => fromBinary(schema, toBinary(schema, value));
  const health = create(foundation.HealthSnapshotSchema, {
    instanceId: id,
    observedAt: { unixSeconds: 1n, nanos: 0 },
    health: 3,
    readiness: { acceptsWork: true, reasons: [] },
  });
  assert.equal(shapes.isHealthSnapshot(roundTrip(foundation.HealthSnapshotSchema, health)), true);
  health.health = 99;
  assert.equal(roundTrip(foundation.HealthSnapshotSchema, health).health, 99);
  assert.equal(shapes.isHealthSnapshot(health), false);
  const context = create(ContextDescriptorSchema, {
    key: "selection",
    provider: "provider",
    kind: "selection",
    titleKey: "title",
    context: { source: { kind: "scopeMetadata", id }, lifetime: 4 },
    observedAt: { unixSeconds: 1n, nanos: 0 },
  });
  assert.equal(shapes.isContextDescriptor(roundTrip(ContextDescriptorSchema, context)), true);
  context.context.revision = create(foundation.RevisionSchema, { value: 0n });
  assert.equal(shapes.isContextDescriptor(context), false);
  const capability = create(foundation.CapabilityDescriptorSchema, {
    key: "read",
    version: "1.0.0",
    requestSchema: "Request",
    responseSchema: "Response",
    risk: "R1",
    locality: 2,
    idempotency: "query",
    exclusive: false,
    egress: "none",
    approval: "none",
    binding: fromBinary(
      foundation.OperationBindingSchema,
      Buffer.from(fixture.wire.operationBinding, "hex"),
    ),
    execution: 2,
    effect: 1,
    retry: 1,
    cancel: { accepted: true, beforeDispatchOnly: true },
    checkpoint: false,
    limits: {
      maxInputBytes: 1n,
      maxOutputBytes: 1n,
      maxDurationMs: 1n,
      maxConcurrency: 1,
      maxContextItems: 64,
    },
  });
  assert.equal(
    shapes.isCapabilityDescriptor(roundTrip(foundation.CapabilityDescriptorSchema, capability)),
    true,
  );
  capability.writes.push("resource");
  assert.equal(shapes.isCapabilityDescriptor(capability), false);
  capability.writes = [];
  capability.limits.maxContextItems = 65;
  assert.equal(shapes.isCapabilityDescriptor(capability), false);
});
function reference(bytes) {
  return create(foundation.EncodedBodyRefSchema, {
    resource: {
      resource: {
        realmId: id,
        resourceId: id,
        ownerAppId: "arcscope",
        resourceKind: "projection",
        availability: 1,
      },
      revision: { case: "cloud", value: { value: 1n } },
      contentHash: hash(bytes),
    },
    messageType: SayHelloResponseSchema.typeName,
    descriptorHash: "a".repeat(64),
    byteLength: BigInt(bytes.length),
    snapshotToken: "bound-snapshot",
    expiresAt: { unixSeconds: 200n, nanos: 1 },
  });
}
const expectation = () => ({
  messageType: SayHelloResponseSchema.typeName,
  descriptorHash: "a".repeat(64),
  snapshotToken: "bound-snapshot",
  now: create(foundation.InstantSchema, { unixSeconds: 200n, nanos: 0 }),
});
test("encoded reference mismatches refuse before malformed protobuf can be decoded", async () => {
  const bytes = Uint8Array.from([255]);
  for (const mutate of [
    (r) => (r.messageType = "wrong"),
    (r) => (r.descriptorHash = "b".repeat(64)),
    (r) => (r.snapshotToken = "wrong"),
    (r) => (r.byteLength = 2n),
    (r) => (r.expiresAt.nanos = 0),
    (r) => (r.resource.contentHash = "b".repeat(64)),
    (r) => (r.resource.contentHash = undefined),
  ]) {
    const bound = reference(bytes);
    mutate(bound);
    await assert.rejects(
      readEncodedBody(SayHelloResponseSchema, bound, bytes, expectation()),
      (e) => e.failure === "invalid",
    );
  }
  await assert.rejects(
    readEncodedBody(SayHelloResponseSchema, reference(bytes), bytes, expectation()),
    (e) => e.failure === "malformed",
  );
});
test("async verification reads an owned immutable byte and reference snapshot", async () => {
  const bytes = toBinary(SayHelloResponseSchema, create(SayHelloResponseSchema, { message: "A" }));
  const bound = reference(bytes);
  const pending = readEncodedBody(SayHelloResponseSchema, bound, bytes, expectation());
  bytes.fill(255);
  bound.resource.contentHash = "0".repeat(64);
  bound.expiresAt.nanos = 0;
  assert.equal((await pending).message, "A");
});
test("exact64MiB large projection passes;64MiB+1 refuses", async () => {
  const bytes = new Uint8Array(wireLimits.largeProjection).fill(65);
  bytes.set([10, 251, 255, 255, 31]);
  assert.equal(
    (await readEncodedBody(SayHelloResponseSchema, reference(bytes), bytes, expectation())).message
      .length,
    wireLimits.largeProjection - 5,
  );
  const tooLarge = new Uint8Array(wireLimits.largeProjection + 1);
  const bound = reference(Uint8Array.of(0));
  await assert.rejects(
    readEncodedBody(SayHelloResponseSchema, bound, tooLarge, expectation()),
    (e) => e.failure === "tooLarge",
  );
});
