// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import test from "node:test";
import * as content from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js";
import * as foundation from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import { readFile } from "node:fs/promises";

test("retired product messages cannot reappear in generated public exports", async () => {
  const inventory = JSON.parse(
    await readFile(new URL("../../eng/foundation-inventory.json", import.meta.url), "utf8"),
  );
  for (const name of inventory.retirement.messages) {
    assert.equal(Object.hasOwn(content, name + "Schema"), false, name);
    assert.equal(Object.hasOwn(foundation, name + "Schema"), false, name);
  }
  assert.ok(content.StructuredValueSchema);
});
