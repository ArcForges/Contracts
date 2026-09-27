// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  canonicalSemanticJson,
  canonicalSemanticHash,
} from "../../src/public/ts/proto/dist/semantic-hash.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/con-17-compat-hash.json", import.meta.url), "utf8"),
);
for (const vector of fixture.vectors) {
  test("semantic hash: " + vector.id, async () => {
    const paths = new Set(vector.nfcPaths ?? []);
    assert.equal(canonicalSemanticJson(vector.input, paths), vector.canonical);
    assert.equal(await canonicalSemanticHash(vector.input, paths), vector.sha256);
  });
}
for (const vector of fixture.invalid) {
  test("semantic refusal: " + vector.id, () => {
    assert.throws(() => canonicalSemanticJson(vector.input, new Set(vector.nfcPaths ?? [])));
  });
}
test("depth and raw surrogate refusal", () => {
  assert.throws(() =>
    canonicalSemanticJson(
      '{"schemaVersion":"example.v1","value":"' + String.fromCharCode(0xd800) + '"}',
    ),
  );
  assert.throws(() =>
    canonicalSemanticJson(
      '{"schemaVersion":"example.v1","value":' + "[".repeat(33) + "null" + "]".repeat(33) + "}",
    ),
  );
});
test("owner revision changes command semantic identity", async () => {
  const command =
    '{"schemaVersion":"example-command.v1","operationId":"setValue","realm":"official","workspaceId":"00112233-4455-6677-8899-aabbccddeeff","actorId":"11223344-5566-7788-99aa-bbccddeeff00","revisionKind":"cloud","revisionValue":"1","fields":{"value":null}}';
  assert.notEqual(
    await canonicalSemanticHash(command),
    await canonicalSemanticHash(command.replace('"revisionValue":"1"', '"revisionValue":"2"')),
  );
});
