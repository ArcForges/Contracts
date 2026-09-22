// SPDX-License-Identifier: Apache-2.0
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import type { DescMessage, MessageShape } from "@bufbuild/protobuf";
import {
  RevisionSchema,
  NativeContentRevSchema,
  LocalNotesVersionSchema,
  DecimalSchema,
} from "./gen/arcforges/foundation/v1/foundation_pb.js";
import type {
  Revision,
  NativeContentRev,
  LocalNotesVersion,
  Decimal,
} from "./gen/arcforges/foundation/v1/foundation_pb.js";
export * from "./values/gen/identifiers.js";

declare const valueBrand: unique symbol;
type Branded<T, Name extends string> = T & { readonly [valueBrand]: Name };
export type CloudRevision = Branded<bigint, "CloudRevision">;
export type NativeRevision = Branded<bigint, "NativeRevision">;
export type DeliverySequence = Branded<bigint, "DeliverySequence">;
export type OpaqueCursor = Branded<string, "OpaqueCursor">;
export type ExactDecimal = Branded<string, "ExactDecimal">;
export type LocalNotesToken = Readonly<{
  acknowledgedRevision: bigint;
  headLocalSequence: bigint;
}> & { readonly [valueBrand]: "LocalNotesToken" };
const i64min = -9223372036854775808n;
const i64max = 9223372036854775807n;
const u64max = 18446744073709551615n;

export function parseInt64(value: string): bigint {
  if (typeof value !== "string" || /^(0|-?[1-9][0-9]*)$/.exec(value)?.[0] !== value)
    throw new TypeError("Invalid canonical int64");
  const result = BigInt(value);
  if (result < i64min || result > i64max) throw new RangeError("int64 overflow");
  return result;
}
export function parseUInt64(value: string): bigint {
  if (typeof value !== "string" || /^(0|[1-9][0-9]*)$/.exec(value)?.[0] !== value)
    throw new TypeError("Invalid canonical uint64");
  const result = BigInt(value);
  if (result > u64max) throw new RangeError("uint64 overflow");
  return result;
}
function unsigned(value: bigint): bigint {
  if (typeof value !== "bigint" || value < 0n || value > u64max)
    throw new RangeError("Invalid uint64");
  return value;
}
export function cloudRevision(value: bigint): CloudRevision {
  if (typeof value !== "bigint" || value <= 0n || value > i64max)
    throw new RangeError("Committed revision must be a positive int64");
  return value as CloudRevision;
}
export function cloudRevisionFromWire(value: Revision): CloudRevision {
  return cloudRevision(value.value!);
}
export function cloudRevisionToWire(value: CloudRevision): Revision {
  return create(RevisionSchema, { value: cloudRevision(value) });
}
export function newRootPrecondition(): Revision {
  return create(RevisionSchema, { value: 0n });
}
export function nativeRevision(value: bigint): NativeRevision {
  return unsigned(value) as NativeRevision;
}
export function nativeRevisionFromWire(value: NativeContentRev): NativeRevision {
  return nativeRevision(value.value!);
}
export function nativeRevisionToWire(value: NativeRevision): NativeContentRev {
  return create(NativeContentRevSchema, { value: nativeRevision(value) });
}
export function deliverySequence(value: bigint): DeliverySequence {
  return unsigned(value) as DeliverySequence;
}
export function localNotesToken(
  acknowledgedRevision: bigint,
  headLocalSequence: bigint,
): LocalNotesToken {
  if (
    typeof acknowledgedRevision !== "bigint" ||
    acknowledgedRevision < 0n ||
    acknowledgedRevision > i64max
  )
    throw new RangeError("Invalid acknowledged revision");
  return Object.freeze({
    acknowledgedRevision,
    headLocalSequence: unsigned(headLocalSequence),
  }) as LocalNotesToken;
}
export function localNotesFromWire(value: LocalNotesVersion): LocalNotesToken {
  return localNotesToken(value.ackedRev?.value!, value.headLocalSeq!);
}
export function localNotesToWire(value: LocalNotesToken): LocalNotesVersion {
  const checked = localNotesToken(value.acknowledgedRevision, value.headLocalSequence);
  return create(LocalNotesVersionSchema, {
    ackedRev: create(RevisionSchema, { value: checked.acknowledgedRevision }),
    headLocalSeq: checked.headLocalSequence,
  });
}
export function opaqueCursor(value: string): OpaqueCursor {
  if (typeof value !== "string" || !validUnicode(value))
    throw new TypeError("Invalid cursor Unicode");
  let bytes = 0;
  for (const scalar of value) {
    const point = scalar.codePointAt(0)!;
    bytes += point <= 0x7f ? 1 : point <= 0x7ff ? 2 : point <= 0xffff ? 3 : 4;
  }
  if (bytes > 4096) throw new RangeError("Cursor too long");
  return value as OpaqueCursor;
}
export function exactDecimal(value: string): ExactDecimal {
  if (
    typeof value !== "string" ||
    /^-?(0|[1-9][0-9]*)(\.[0-9]{1,9})?$/.exec(value)?.[0] !== value ||
    (value.startsWith("-") && !/[1-9]/.test(value)) ||
    value.replace(/[-.]/g, "").replace(/^0+/, "").length > 28
  )
    throw new TypeError("Invalid exact decimal");
  return value as ExactDecimal;
}
export function notesDecimal(value: string): ExactDecimal {
  const result = exactDecimal(value);
  if (value.includes(".") && value.endsWith("0")) throw new TypeError("Noncanonical Notes decimal");
  return result;
}
export function decimalFromWire(value: Decimal): ExactDecimal {
  return exactDecimal(value.value!);
}
export function decimalToWire(value: ExactDecimal): Decimal {
  return create(DecimalSchema, { value: exactDecimal(value) });
}
export function decimalParts(
  value: ExactDecimal,
): Readonly<{ coefficient: bigint; scale: number }> {
  const checked = exactDecimal(value);
  const point = checked.indexOf(".");
  return Object.freeze({
    coefficient: BigInt(checked.replace(".", "")),
    scale: point < 0 ? 0 : checked.length - point - 1,
  });
}
export function decimalFromCoefficient(coefficient: bigint, scale: number): ExactDecimal {
  if (typeof coefficient !== "bigint" || !Number.isInteger(scale) || scale < 0 || scale > 9)
    throw new RangeError("Invalid exact coefficient/scale");
  const digits = (coefficient < 0n ? -coefficient : coefficient)
    .toString()
    .padStart(scale + 1, "0");
  const value = scale === 0 ? digits : `${digits.slice(0, -scale)}.${digits.slice(-scale)}`;
  return exactDecimal(coefficient < 0n ? `-${value}` : value);
}

/** Decodes compatible read data, retaining unknown fields; strict validation decides mutation suitability. */
export function readProjection<T extends DescMessage>(
  schema: T,
  bytes: Uint8Array,
  validate: (value: unknown) => boolean,
): Readonly<{ message: MessageShape<T>; knownProfile: boolean }> {
  const message = fromBinary(schema, bytes);
  return Object.freeze({ message, knownProfile: validate(message) });
}
/** Re-emits a generated projection, including its inert unknown fields. */
export function preserveProjection<T extends DescMessage>(
  schema: T,
  message: MessageShape<T>,
): Uint8Array {
  return toBinary(schema, message);
}

function validUnicode(text: string): boolean {
  for (let i = 0; i < text.length; i++) {
    const first = text.charCodeAt(i);
    if (first < 0xd800 || first > 0xdfff) continue;
    if (first > 0xdbff || ++i >= text.length) return false;
    const second = text.charCodeAt(i);
    if (second < 0xdc00 || second > 0xdfff) return false;
  }
  return true;
}
export type RationalValue = Readonly<{ numerator: bigint; denominator: bigint }> & {
  readonly [valueBrand]: "RationalValue";
};
export function rationalValue(numerator: bigint, denominator: bigint): RationalValue {
  if (
    typeof numerator !== "bigint" ||
    numerator < i64min ||
    numerator > i64max ||
    typeof denominator !== "bigint" ||
    denominator <= 0n ||
    denominator > u64max
  )
    throw new RangeError("Invalid rational components");
  let a = numerator < 0n ? -numerator : numerator;
  let b = denominator;
  while (b !== 0n) {
    const remainder = a % b;
    a = b;
    b = remainder;
  }
  if (a !== 1n) throw new TypeError("Rational is not reduced");
  return Object.freeze({ numerator, denominator }) as RationalValue;
}
export function convertTicksExact(
  ticks: bigint,
  sourceRate: RationalValue,
  targetRate: RationalValue,
): bigint {
  if (typeof ticks !== "bigint" || ticks < i64min || ticks > i64max)
    throw new RangeError("Invalid signed ticks");
  const source = rationalValue(sourceRate.numerator, sourceRate.denominator);
  const target = rationalValue(targetRate.numerator, targetRate.denominator);
  if (source.numerator <= 0n || target.numerator <= 0n)
    throw new RangeError("Timebase must be positive");
  const numerator = ticks * target.numerator * source.denominator;
  const denominator = source.numerator * target.denominator;
  const result = numerator / denominator;
  if (numerator % denominator !== 0n || result < i64min || result > i64max)
    throw new RangeError("Time is not representable");
  return result;
}
