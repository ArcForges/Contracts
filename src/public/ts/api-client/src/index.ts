// SPDX-License-Identifier: Apache-2.0
import { HelloService } from "@arcforges/proto";
import { createClient } from "@connectrpc/connect";
import { createGrpcWebTransport } from "@connectrpc/connect-web";
import type { GrpcWebTransportOptions } from "@connectrpc/connect-web";

/** Creates the example client using the caller's gRPC-Web endpoint and fetch. */
export function createHelloClient(options: GrpcWebTransportOptions) {
  return createClient(HelloService, createGrpcWebTransport(options));
}
