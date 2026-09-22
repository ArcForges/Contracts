// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";

// Expectations remain independently authored in wp03-01.json. The inventory only
// checks that passing decoded examples cover the entire selected message/union
// surface; it never manufactures an example or decides its expected validity.
export function assertFoundationCoverage(inventory, output) {
  const records = new Map(inventory.records.map((record) => [record.name, record]));
  assert.equal(records.size, inventory.records.length, "Duplicate coverage inventory record");
  assert.deepEqual(
    [...new Set(output.map((item) => item.target))].sort(),
    [...records.keys()].sort(),
    "Every selected message must have a positive decoded exchange example",
  );

  const expectedBranches = new Set();
  for (const record of records.values()) {
    for (const field of record.fields) {
      if (field.oneof) expectedBranches.add(`${record.name}.${field.oneof}.${field.name}`);
    }
  }
  const observedBranches = new Set();

  function visit(name, value, path) {
    assert.ok(
      value !== null && typeof value === "object" && !Array.isArray(value),
      `${path}: decoded record expected`,
    );
    const record = records.get(name);
    assert.ok(record, `${path}: unknown selected record ${name}`);
    for (const field of record.fields) {
      if (!Object.hasOwn(value, field.name) || value[field.name] === null) continue;
      const child = value[field.name];
      if (field.oneof) observedBranches.add(`${name}.${field.oneof}.${field.name}`);
      if (!records.has(field.wireType)) continue;
      const childPath = `${path}.${field.name}`;
      if (field.presence === "repeated") {
        assert.ok(Array.isArray(child), `${childPath}: decoded repeated field expected`);
        for (const [index, item] of child.entries()) {
          visit(field.wireType, item, `${childPath}[${index}]`);
        }
      } else {
        visit(field.wireType, child, childPath);
      }
    }
  }

  for (const item of output) visit(item.target, item.json, item.id);
  assert.deepEqual(
    [...observedBranches].sort(),
    [...expectedBranches].sort(),
    "Every selected oneof branch must survive a positive semantic round trip",
  );
}
