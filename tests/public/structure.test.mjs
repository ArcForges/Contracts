// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fromJson } from "@bufbuild/protobuf";
import * as foundation from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import * as events from "../../src/public/ts/proto/dist/gen/arcforges/events/v1/events_pb.js";
import * as publicChecks from "../../src/public/ts/proto/dist/shapes/gen/proto.js";
import * as operator from "../../src/internal/ts/operator-client/dist/gen/arcforges/operator/v1/operator_pb.js";
import * as operatorChecks from "../../src/internal/ts/operator-client/dist/shapes/gen/proto.js";
import { isPartReceipt, isPackageInventory } from "../../src/public/ts/api-client/dist/gen/http.js";
import { isCommitReceipt } from "../../src/internal/ts/ai-internal/dist/gen/http.js";

let count = 0;
for (const visibility of ["public", "internal"]) {
  const fixture = JSON.parse(
    await readFile(new URL(`../../fixtures/${visibility}/wp03-00.json`, import.meta.url), "utf8"),
  );
  for (const item of fixture.cases) {
    const http = {
      PartReceipt: isPartReceipt,
      PackageInventory: isPackageInventory,
      CommitReceipt: isCommitReceipt,
    }[item.target];
    if (http) {
      assert.equal(http(item.value), item.valid, item.id);
      count++;
      continue;
    }
    // Extension and local IPC are C#-only. The C# unit suite covers their same independent cases.
    if (
      item.target.startsWith("arcforges.extensions.") ||
      item.target.startsWith("arcforges.local.")
    )
      continue;
    const name = item.target.split(".").at(-1);
    const schemas = item.target.startsWith("arcforges.operator.")
      ? operator
      : item.target.startsWith("arcforges.events.")
        ? events
        : foundation;
    const checks = item.target.startsWith("arcforges.operator.") ? operatorChecks : publicChecks;
    assert.ok(schemas[`${name}Schema`], `Missing explicit fixture schema ${item.target}`);
    assert.equal(
      typeof checks[`is${name}`],
      "function",
      `Missing generated validator ${item.target}`,
    );
    let actual;
    try {
      actual = checks[`is${name}`](fromJson(schemas[`${name}Schema`], item.value));
    } catch {
      actual = false;
    }
    assert.equal(actual, item.valid, item.id);
    count++;
  }
}
console.log(`Validated ${count} independent TypeScript shape fixtures.`);
