// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { HelloService, SayHelloRequestSchema } from "@arcforges/proto";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/hello.json", import.meta.url)),
);
test("the generated service preserves the public wire identity", () => {
  assert.equal(HelloService.typeName, "arcforges.hello.v1.HelloService");
  assert.equal(HelloService.method.sayHello.name, "SayHello");
});
test("protobuf roundtrips shared ASCII and Unicode fixtures", () => {
  for (const { name } of fixture.cases) {
    const message = create(SayHelloRequestSchema, { name });
    assert.equal(
      fromBinary(SayHelloRequestSchema, toBinary(SayHelloRequestSchema, message)).name,
      name,
    );
  }
});
test("the field number and malformed payload behavior remain explicit", () => {
  assert.deepEqual(
    toBinary(SayHelloRequestSchema, create(SayHelloRequestSchema, { name: "A" })),
    new Uint8Array([0x0a, 0x01, 0x41]),
  );
  assert.throws(() => fromBinary(SayHelloRequestSchema, new Uint8Array([0x0a, 0x05, 0x41])));
});
