// SPDX-License-Identifier: Apache-2.0
import type { DescMessage, MessageShape } from "@bufbuild/protobuf";
import type { EncodedBodyRef, Instant } from "./gen/arcforges/foundation/v1/foundation_pb.js";
import { isEncodedBodyRef, isInstant } from "./shapes/gen/proto.js";
import { ContractSerializationError, decodeContract, wireLimits } from "./wire.js";

declare const crypto: {
  subtle: { digest(algorithm: string, data: Uint8Array): Promise<ArrayBuffer> };
};

/** Caller-owned binding to an authorized read operation and its immutable snapshot. */
export interface EncodedBodyExpectation {
  readonly messageType: string;
  readonly descriptorHash: string;
  readonly snapshotToken: string;
  readonly now: Instant;
}

/**
 * Checks shape, immutable identity, expiry, exact length and SHA256 before a fixed generated decode.
 * Fetching, resource ownership/revision admission, revocation and authorization remain caller-owned.
 */
export async function readEncodedBody<Desc extends DescMessage>(
  schema: Desc,
  reference: EncodedBodyRef,
  bytes: Uint8Array,
  expected: EncodedBodyExpectation,
): Promise<MessageShape<Desc>> {
  if (!isEncodedBodyRef(reference) || !isInstant(expected.now))
    throw new ContractSerializationError("invalid");
  if (bytes.byteLength > wireLimits.largeProjection)
    throw new ContractSerializationError("tooLarge");
  const expiry = reference.expiresAt!;
  if (
    reference.messageType !== expected.messageType ||
    schema.typeName !== expected.messageType ||
    reference.descriptorHash !== expected.descriptorHash ||
    reference.snapshotToken !== expected.snapshotToken ||
    reference.byteLength !== BigInt(bytes.byteLength) ||
    expiry.unixSeconds! < expected.now.unixSeconds! ||
    (expiry.unixSeconds === expected.now.unixSeconds && expiry.nanos! <= expected.now.nanos!)
  )
    throw new ContractSerializationError("invalid");
  // Capture all mutable inputs before the asynchronous digest can yield control.
  const contentHash = reference.resource!.contentHash!;
  const snapshot = new Uint8Array(bytes);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", snapshot));
  const actual = Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
  if (actual !== contentHash) throw new ContractSerializationError("invalid");
  return decodeContract(schema, snapshot, "largeProjection");
}
