// SPDX-License-Identifier: Apache-2.0
// Independent fixture acceptance and lossless typed roundtrip against built generated codecs.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
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
  assert.deepEqual(
    [...new Set(fixture.codecCases.map((row) => row.schema))].sort(),
    Object.keys(codecs).sort(),
  );
});

for (const row of fixture.codecCases) {
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
