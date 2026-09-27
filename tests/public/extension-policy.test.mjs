// SPDX-License-Identifier: Apache-2.0
// Independent fixture acceptance and lossless typed roundtrip against built generated codecs.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createHash } from "node:crypto";
import {
  tryParseExtensionManifestJson,
  serializeExtensionManifestJson,
  tryParseExtensionWorkflowJson,
  serializeExtensionWorkflowJson,
  tryParseDeclarativePanelJson,
  serializeDeclarativePanelJson,
  tryParsePolicyBodyJson,
  serializePolicyBodyJson,
} from "@arcforges/api-client";
import {
  tryParseConfigurationDocumentJson,
  serializeConfigurationDocumentJson,
} from "../../src/internal/ts/ai-internal/dist/gen/http.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/con-12-extension-policy.json", import.meta.url)),
);
const privateFixture = JSON.parse(
  readFileSync(new URL("../../fixtures/internal/con-12-configuration.json", import.meta.url)),
);
const codecCases = [...fixture.codecCases, ...privateFixture.codecCases];
test("length-prefixed SHA256 bucket and allocation boundary vectors", () => {
  for (const row of fixture.bucketVectors) {
    const input = Buffer.concat(
      row.components.map((component) => {
        const bytes = Buffer.from(component, "utf8");
        const length = Buffer.alloc(4);
        length.writeUInt32BE(bytes.length);
        return Buffer.concat([length, bytes]);
      }),
    );
    const digest = createHash("sha256").update(input).digest();
    assert.equal(input.toString("hex"), row.inputHex);
    assert.equal(digest.toString("hex"), row.sha256);
    assert.equal(Number(digest.readBigUInt64BE() % 10000n), row.bucket);
  }
  for (const row of fixture.allocationVectors)
    assert.equal(row.bucket < row.allocation, row.included);
});
const codecs = {
  ExtensionManifest: {
    parse: tryParseExtensionManifestJson,
    serialize: serializeExtensionManifestJson,
  },
  ExtensionWorkflow: {
    parse: tryParseExtensionWorkflowJson,
    serialize: serializeExtensionWorkflowJson,
  },
  DeclarativePanel: {
    parse: tryParseDeclarativePanelJson,
    serialize: serializeDeclarativePanelJson,
  },
  PolicyBody: { parse: tryParsePolicyBodyJson, serialize: serializePolicyBodyJson },
  ConfigurationDocument: {
    parse: tryParseConfigurationDocumentJson,
    serialize: serializeConfigurationDocumentJson,
  },
};

test("extension/policy independent vectors exercise every generated root", () => {
  assert.ok(Array.isArray(fixture.codecCases));
  assert.ok(Array.isArray(privateFixture.codecCases));
  assert.ok(fixture.codecCases.every((row) => row.schema !== "ConfigurationDocument"));
  assert.ok(privateFixture.codecCases.every((row) => row.schema === "ConfigurationDocument"));
  assert.deepEqual(
    [...new Set(codecCases.map((row) => row.schema))].sort(),
    Object.keys(codecs).sort(),
  );
});

for (const row of codecCases) {
  test(`extension/policy codec: ${row.id}`, () => {
    const codec = codecs[row.schema];
    assert.ok(codec, `Unknown schema ${row.schema}`);
    const result = codec.parse(new TextEncoder().encode(JSON.stringify(row.value)));
    assert.equal(result.ok, row.valid, `${row.id}: independent acceptance differs`);
    if (!row.valid) return;
    const encoded = codec.serialize(result.value);
    const second = codec.parse(encoded);
    assert.equal(second.ok, true, `${row.id}: generated serialization refused itself`);
    assert.deepEqual(second.value, row.value, `${row.id}: typed roundtrip changed the document`);
    assert.deepEqual(
      codec.serialize(second.value),
      encoded,
      `${row.id}: serialization is not stable`,
    );
  });
}
