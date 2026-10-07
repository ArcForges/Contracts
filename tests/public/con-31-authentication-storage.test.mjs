// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { create, fromBinary, toBinary, clone } from "@bufbuild/protobuf";
import * as contracts from "../../src/internal/ts/operator-client/dist/index.js";
import { RevisionSchema } from "@arcforges/proto";
const fixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/internal/con-31-authentication-storage.json", import.meta.url),
    "utf8",
  ),
);
const policy = JSON.parse(
  await readFile(
    new URL("../../fixtures/internal/operator-provider-policy.json", import.meta.url),
    "utf8",
  ),
);

test("independent storage binary vectors preserve exact presence and oneof phases", () => {
  assert.equal(fixture.vectors.length, 44);
  const ids = new Set();
  for (const vector of fixture.vectors) {
    assert(!ids.has(vector.id));
    ids.add(vector.id);
    const schema = contracts[vector.message + "Schema"];
    assert(schema, vector.message);
    const bytes = Buffer.from(vector.wireHex, "hex");
    const parsed = fromBinary(schema, bytes);
    assert.equal(contracts["is" + vector.message](parsed), vector.valid, vector.id);
    assert.deepEqual(
      Buffer.from(toBinary(schema, parsed)),
      bytes,
      vector.id + " real serializer roundtrip",
    );
  }
});

test("original64-member passkey inventory is bounded sorted complete and distinct", () => {
  const vector = fixture.vectors.find((v) => v.id === "actual-step-up-original-passkey");
  const schema = contracts.StepUpMethodProofSnapshotSchema;
  const value = fromBinary(schema, Buffer.from(vector.wireHex, "hex"));
  const credential = value.credentials[0];
  value.credentials = Array.from({ length: 64 }, (_, i) => {
    const row = clone(contracts.AuthenticationCredentialReferenceSchema, credential);
    row.identityId.value = Uint8Array.from([i + 1, ...Array(15).fill(0)]);
    row.subjectSha256 = Uint8Array.from([i + 1, ...Array(31).fill(0)]);
    return row;
  });
  assert(contracts.isStepUpMethodProofSnapshot(value));
  assert(contracts.isStepUpMethodProofSnapshot(fromBinary(schema, toBinary(schema, value))));
  const changed = clone(schema, value);
  changed.credentials.push(clone(contracts.AuthenticationCredentialReferenceSchema, credential));
  assert.equal(contracts.isStepUpMethodProofSnapshot(changed), false);
  const reordered = clone(schema, value);
  [reordered.credentials[0], reordered.credentials[1]] = [
    reordered.credentials[1],
    reordered.credentials[0],
  ];
  assert.equal(contracts.isStepUpMethodProofSnapshot(reordered), false);
  const subject = clone(schema, value);
  subject.credentials[1].subjectSha256 = subject.credentials[0].subjectSha256.slice();
  assert.equal(contracts.isStepUpMethodProofSnapshot(subject), false);
});

test("wire unknown fields remain forward compatible but count toward encoded custody bound", () => {
  const vector = fixture.vectors.find((v) => v.id === "anonymous-browser-email");
  const original = Buffer.from(vector.wireHex, "hex");
  const small = Buffer.concat([original, Buffer.from("ca3e03aabbcc", "hex")]);
  const parsed = fromBinary(contracts.AuthenticationFlowPayloadSchema, small);
  assert(contracts.isAuthenticationFlowPayload(parsed));
  assert.deepEqual(Buffer.from(toBinary(contracts.AuthenticationFlowPayloadSchema, parsed)), small);
  const oversized = clone(contracts.AuthenticationFlowPayloadSchema, parsed);
  oversized.$unknown[0].data = new Uint8Array(131073);
  assert.equal(contracts.isAuthenticationFlowPayload(oversized), false);
});

test("credential references compare known facts consistently while preserving nested future unknowns", () => {
  const vector = fixture.vectors.find((v) => v.id === "actual-step-up-original-passkey");
  const schema = contracts.StepUpMethodProofSnapshotSchema;
  const value = fromBinary(schema, Buffer.from(vector.wireHex, "hex"));
  value.method = 3;
  const credential = value.credentials[0];
  credential.method = 3;
  delete credential.publicKeySha256;
  delete credential.userHandleSha256;
  value.methodProof.proof = {
    case: "password",
    value: create(contracts.PasswordFlowBindingSchema, {
      credential: clone(contracts.AuthenticationCredentialReferenceSchema, credential),
    }),
  };
  assert(contracts.isStepUpMethodProofSnapshot(value));
  const revisionSchema = RevisionSchema;
  const revisionWire = Buffer.concat([
    toBinary(revisionSchema, credential.revision),
    Buffer.from("ca3e03aabbcc", "hex"),
  ]);
  value.methodProof.proof.value.credential.revision = fromBinary(revisionSchema, revisionWire);
  assert(contracts.isStepUpMethodProofSnapshot(value));
  const copy = fromBinary(schema, toBinary(schema, value));
  assert(contracts.isStepUpMethodProofSnapshot(copy));
  assert.deepEqual(
    Buffer.from(toBinary(revisionSchema, copy.methodProof.proof.value.credential.revision)),
    revisionWire,
  );
  value.credentials[0].revision = fromBinary(revisionSchema, revisionWire);
  assert(contracts.isStepUpMethodProofSnapshot(value));
  value.methodProof.proof.value.credential.revision.value += 1n;
  assert.equal(contracts.isStepUpMethodProofSnapshot(value), false);
  value.methodProof.proof.value.credential.revision.value -= 1n;
  value.methodProof.proof.value.credential.revision.$unknown[0].data = new Uint8Array(131073);
  assert.equal(
    contracts.isStepUpMethodProofSnapshot(value),
    false,
    "nested Foundation unknown data is refused before serialization",
  );
});

test("independent trust-profile shape preserves nanoseconds, closed keys and policy ordering", () => {
  const bytes = new TextEncoder().encode(JSON.stringify(policy));
  const parsed = contracts.parseOperatorProviderPolicyJson(bytes);
  assert.equal(parsed.notAfter, "2026-10-07T00:00:00.123456790Z");
  assert(contracts.isOperatorProviderPolicy(policy));
  assert.equal(
    contracts.isOperatorProviderPolicy({ ...policy, notAfter: policy.capturedAt }),
    false,
  );
  assert.equal(
    contracts.isOperatorProviderPolicy({ ...policy, capturedAt: "2026-02-30T00:00:00Z" }),
    false,
  );
  assert.equal(
    contracts.isOperatorProviderPolicy({
      ...policy,
      realmId: "00000000-0000-0000-0000-000000000000",
    }),
    false,
  );
  assert.equal(
    contracts.isOperatorProviderPolicy({
      ...policy,
      policyIds: [...policy.policyIds, ...policy.policyIds],
    }),
    false,
  );
  assert.equal(contracts.isOperatorProviderPolicy({ ...policy, verified: true }), false);
  assert.throws(() =>
    contracts.parseOperatorProviderPolicyJson(
      new TextEncoder().encode(
        JSON.stringify(policy).replace('"version":"v1"', '"version":"v1","version":"v1"'),
      ),
    ),
  );
});
