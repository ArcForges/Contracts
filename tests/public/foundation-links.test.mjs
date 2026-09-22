// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { create } from "@bufbuild/protobuf";
import { LinkSpecSchema } from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js";
import { isLinkSpec } from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

function valid(url) {
  return isLinkSpec(create(LinkSpecSchema, { kind: "external", url }));
}

test("link validation preserves explicit schemes, authority and optional URL parts", () => {
  for (const url of [
    "http://example.test",
    "https://example.test/a?b=c#d",
    "http://!",
    "http://!/?#",
    "mailto:user@example.test",
    "mailto:user@example.test?subject=hello",
  ]) {
    assert.equal(valid(url), true, url);
  }
  for (const url of [
    "",
    "http://",
    "https:///path",
    "http://?query",
    "http://#fragment",
    "mailto:",
    "HTTPS://example.test",
    "javascript:alert(1)",
  ]) {
    assert.equal(valid(url), false, url);
  }
  const whitespace = [
    "\t",
    "\n",
    "\v",
    "\f",
    "\r",
    " ",
    "\u0085",
    "\u00a0",
    "\u1680",
    "\u2000",
    "\u2001",
    "\u2002",
    "\u2003",
    "\u2004",
    "\u2005",
    "\u2006",
    "\u2007",
    "\u2008",
    "\u2009",
    "\u200a",
    "\u2028",
    "\u2029",
    "\u202f",
    "\u205f",
    "\u3000",
    "\ufeff",
  ];
  for (const separator of whitespace) {
    for (const url of [
      "http://example.test" + separator,
      "https://example" + separator + ".test/path",
      "mailto:user@example.test" + separator,
    ]) {
      assert.equal(valid(url), false, JSON.stringify(url));
    }
  }
});

test("long malformed authorities terminate without regex backtracking", () => {
  const code = `
    import assert from 'node:assert/strict';
    import { create } from '@bufbuild/protobuf';
    import { LinkSpecSchema } from ${JSON.stringify(new URL("../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js", import.meta.url).href)};
    import { isLinkSpec } from ${JSON.stringify(new URL("../../src/public/ts/proto/dist/shapes/gen/proto.js", import.meta.url).href)};
    const authority = 'http://' + '!'.repeat(100000);
    assert.equal(isLinkSpec(create(LinkSpecSchema, { kind: 'external', url: authority })), true);
    for (const suffix of ['\\n', '\\u0085', '\\ufeff']) {
      assert.equal(isLinkSpec(create(LinkSpecSchema, { kind: 'external', url: authority + suffix })), false);
    }
  `;
  const result = spawnSync(process.execPath, ["--input-type=module", "--eval", code], {
    cwd: new URL("../../", import.meta.url),
    timeout: 5000,
    encoding: "utf8",
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});
