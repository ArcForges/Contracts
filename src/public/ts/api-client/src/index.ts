// SPDX-License-Identifier: Apache-2.0
import { contractBinaryReadOptions, HelloService } from "@arcforges/proto";
import { createClient } from "@connectrpc/connect";
import type { Transport } from "@connectrpc/connect";
import { createGrpcWebTransport } from "@connectrpc/connect-web";
import type { GrpcWebTransportOptions } from "@connectrpc/connect-web";

/** Caller-owned endpoint, fetch, interceptors and timeout; the wire format is fixed. */
export type PublicGrpcWebTransportOptions = Omit<
  GrpcWebTransportOptions,
  "useBinaryFormat" | "jsonOptions" | "binaryOptions"
>;

/**
 * Creates the public business transport: binary gRPC-Web only, unknown fields
 * retained and the shared nesting bound. JSON selection is refused.
 */
export function createPublicGrpcWebTransport(options: PublicGrpcWebTransportOptions): Transport {
  const selected = options as GrpcWebTransportOptions;
  if (
    selected.useBinaryFormat !== undefined ||
    selected.jsonOptions !== undefined ||
    selected.binaryOptions !== undefined
  ) {
    throw new TypeError(
      "Public ArcForges business calls use binary gRPC-Web with fixed codec options.",
    );
  }
  return createGrpcWebTransport({
    ...options,
    useBinaryFormat: true,
    binaryOptions: { ...contractBinaryReadOptions, writeUnknownFields: true },
  });
}

/** Creates the example client using the caller's gRPC-Web endpoint and fetch. */
export function createHelloClient(options: PublicGrpcWebTransportOptions) {
  return createClient(HelloService, createPublicGrpcWebTransport(options));
}

export * from "./gen/http.js";
