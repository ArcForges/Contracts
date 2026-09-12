// SPDX-License-Identifier: Apache-2.0
import { createHelloClient } from "@arcforges/api-client";
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { Code, ConnectError } from "@connectrpc/connect";
import { SayHelloRequestSchema } from "@arcforges/proto";
import type { SayHelloRequest } from "@arcforges/proto";

export async function verify(baseUrl: string, cases: Array<{ name: string; message: string }>) {
  const client = createHelloClient({ baseUrl });
  for (const item of cases) {
    const request: SayHelloRequest = create(SayHelloRequestSchema, { name: item.name });
    const decoded = fromBinary(SayHelloRequestSchema, toBinary(SayHelloRequestSchema, request));
    const reply = await client.sayHello(decoded, { timeoutMs: 5000 });
    if (reply.message !== item.message) throw new Error("gRPC-Web reply mismatch");
  }
  try {
    await client.sayHello({ name: "" }, { timeoutMs: 5000 });
  } catch (error) {
    if (error instanceof ConnectError && error.code === Code.InvalidArgument) return;
    throw error;
  }
  throw new Error("Empty name must fail with a decoded gRPC-Web error trailer");
}
