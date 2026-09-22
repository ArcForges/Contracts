// SPDX-License-Identifier: Apache-2.0
import { fromBinary, toBinary } from "@bufbuild/protobuf";
import type { DescMessage, MessageShape } from "@bufbuild/protobuf";

/** The registry's fixed decode and encode bounds. */
export const wireLimits = Object.freeze({
  unaryMessage: 4 * 1024 * 1024,
  helperMessage: 4 * 1024 * 1024,
  inlinePage: 256 * 1024,
  streamFrame: 32 * 1024,
  largeProjection: 64 * 1024 * 1024,
  /** Message levels permitted below the root message. */
  nestedMessageLevels: 100,
} as const);

/** Selected transport size classes from the wire registry. */
export type WireLimit = Exclude<keyof typeof wireLimits, "nestedMessageLevels">;

/** Why a bounded contract encode or decode was refused. */
export type ContractSerializationFailure = "tooLarge" | "tooDeep" | "malformed" | "invalid";

/** A typed refusal from a bounded contract codec; the message never carries payload content. */
export class ContractSerializationError extends Error {
  readonly failure: ContractSerializationFailure;
  constructor(failure: ContractSerializationFailure, options?: { cause?: unknown }) {
    super(`Contract serialization refused: ${failure}.`, options);
    this.name = "ContractSerializationError";
    this.failure = failure;
  }
}

/**
 * protobuf-es read options matching the C# decoder: unknown fields are retained
 * and the root plus 100 nested message levels are admitted (protobuf-es counts the root).
 */
export const contractBinaryReadOptions = Object.freeze({
  readUnknownFields: true,
  recursionLimit: wireLimits.nestedMessageLevels + 1,
});

/** Decodes one complete message or throws a typed refusal. */
export function decodeContract<Desc extends DescMessage>(
  schema: Desc,
  bytes: Uint8Array,
  limit: WireLimit,
): MessageShape<Desc> {
  if (bytes.byteLength > wireLimits[limit]) throw new ContractSerializationError("tooLarge");
  try {
    return fromBinary(schema, bytes, contractBinaryReadOptions);
  } catch (error) {
    // protobuf-es reports recursion exhaustion through its fixed depth message.
    const deep = error instanceof Error && error.message.includes("maximum recursion depth");
    throw new ContractSerializationError(deep ? "tooDeep" : "malformed", { cause: error });
  }
}

/** Encodes a message only when its serialized size fits the selected class. */
export function encodeContract<Desc extends DescMessage>(
  schema: Desc,
  message: MessageShape<Desc>,
  limit: WireLimit,
): Uint8Array {
  const bytes = toBinary(schema, message, { writeUnknownFields: true });
  if (bytes.byteLength > wireLimits[limit]) throw new ContractSerializationError("tooLarge");
  return bytes;
}
