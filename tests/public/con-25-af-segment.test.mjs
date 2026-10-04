// SPDX-License-Identifier: Apache-2.0
// Canonical af-segment.v1 consumer: an independent canonical encoder and a strict reader that live
// only in this file (no production code, no protobuf JSON mapping, no JSON.stringify of the model).
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import { create, equals, fromBinary, toBinary } from "@bufbuild/protobuf";
import {
  DecimalSchema,
  IdSchema,
  InstantSchema,
  RationalSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import {
  MetadataEntrySchema,
  MetadataScalarSchema,
  ScopeTimeSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js";
import {
  SimulationDataSegmentSchema,
  SimulationEventSchema,
  SimulationGapSchema,
  SimulationSampleSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/simulation/v1/simulation_pb.js";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/con-25-af-segment.json", import.meta.url), "utf8"),
);

const expectedVectorIds = [
  "empty-segment-keeps-every-ordered-repeated-field",
  "numeric-digital-and-event-samples-in-delivered-order",
  "duplicate-delivery-differs-only-by-ordinal-and-fault-marker",
  "gap-and-fault-markers-with-and-without-channel",
  "binary64-bit-words-preserve-sign-and-extremes",
  "integral-extremes-use-exact-strings",
  "text-metadata-escapes-and-unicode",
];
const expectedRefusalIds = [
  "refuse-uppercase-uuid",
  "refuse-json-number-for-uint64",
  "refuse-leading-zero-uint64",
  "refuse-uint64-overflow",
  "refuse-negative-zero-sint64",
  "refuse-double-as-json-number",
  "refuse-uppercase-hex-double",
  "refuse-short-hex-double",
  "refuse-nan-bit-word",
  "refuse-infinity-bit-word",
  "refuse-unsorted-members",
  "refuse-missing-empty-repeated",
  "refuse-two-oneof-arms",
  "refuse-no-oneof-arm",
  "refuse-insignificant-whitespace",
  "refuse-null-for-absent-optional",
  "refuse-unknown-member",
  "refuse-duplicate-member",
  "refuse-wrong-encoding-profile",
  "refuse-wrong-execution-profile",
  "refuse-resource-metadata-arm",
  "refuse-out-of-order-ordinals",
  "refuse-duplicate-ordinal",
  "refuse-unknown-gap-kind",
  "refuse-zero-rate-denominator",
  "refuse-non-minimal-escape",
  "refuse-uppercase-escape-digits",
  "refuse-byte-order-mark",
];
// Refusals the strict *lexical* reader cannot tell apart from valid text on its own: only the
// byte-for-byte re-encode comparison refuses them.
const reencodeOnlyRefusals = [
  "refuse-insignificant-whitespace",
  "refuse-non-minimal-escape",
  "refuse-uppercase-escape-digits",
];

const U64_MAX = 18446744073709551615n;
const S64_MIN = -9223372036854775808n;
const S64_MAX = 9223372036854775807n;
const U32_MAX = 4294967295n;

class Refused extends Error {}
function refuse(message) {
  throw new Refused(message);
}

// ================================================================== canonical encoder

const ordinalCompare = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

function hex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function idText(id) {
  if (id?.value === undefined || id.value.length !== 16) refuse("Id is not 16 bytes");
  const h = hex(id.value);
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function doubleBits(value) {
  if (!Number.isFinite(value)) refuse("nonfinite double");
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, value, false);
  return view.getBigUint64(0, false).toString(16).padStart(16, "0");
}

// Mutation switches exist only to prove the golden bytes are discriminating.
function makeEncoder(mutation = {}) {
  const text = (value) => {
    if (!value.isWellFormed()) refuse("unpaired surrogate");
    let out = '"';
    for (const char of value) {
      const code = char.codePointAt(0);
      if (char === '"') out += '\\"';
      else if (char === "\\") out += "\\\\";
      else if (code === 8) out += "\\b";
      else if (code === 9) out += "\\t";
      else if (code === 10) out += "\\n";
      else if (code === 12) out += "\\f";
      else if (code === 13) out += "\\r";
      else if (code < 0x20) out += `\\u${code.toString(16).padStart(4, "0")}`;
      else if (mutation.escapeNonAscii && code > 0x7e) {
        for (const unit of char.split("")) {
          out += `\\u${unit.charCodeAt(0).toString(16).padStart(4, "0")}`;
        }
      } else out += char;
    }
    return `${out}"`;
  };
  const u64 = (value) => {
    if (typeof value !== "bigint" || value < 0n || value > U64_MAX) refuse("uint64");
    return `"${value}"`;
  };
  const s64 = (value) => {
    if (typeof value !== "bigint" || value < S64_MIN || value > S64_MAX) refuse("sint64");
    return `"${value}"`;
  };
  const u32 = (value) => {
    if (!Number.isInteger(value) || value < 0 || value > Number(U32_MAX)) refuse("uint32");
    return `"${value}"`;
  };
  const dbl = (value) => (mutation.doubleToString ? String(value) : `"${doubleBits(value)}"`);
  const object = (members) => {
    const present = members.filter(([, value]) => value !== undefined);
    if (!mutation.noSort) present.sort(([a], [b]) => ordinalCompare(a, b));
    return `{${present.map(([name, value]) => `${text(name)}:${value}`).join(",")}}`;
  };
  const array = (items) =>
    items.length === 0 && mutation.omitEmpty ? undefined : `[${items.join(",")}]`;
  const required = (value, what) => {
    if (value === undefined) refuse(`missing ${what}`);
    return value;
  };
  const rational = (rate) =>
    object([
      ["denominator", u64(required(rate?.denominator, "denominator"))],
      ["numerator", s64(required(rate?.numerator, "numerator"))],
    ]);
  const time = (value) =>
    object([
      ["rate", rational(required(value?.rate, "rate"))],
      ["ticks", s64(required(value?.ticks, "ticks"))],
    ]);
  const scalar = (message) => {
    const arm = message?.value;
    switch (arm?.case) {
      case "text":
        return object([["text", text(arm.value)]]);
      case "boolean":
        return object([["boolean", arm.value ? "true" : "false"]]);
      case "integer":
        return object([["integer", s64(arm.value)]]);
      case "number":
        return object([["number", `"${doubleBits(arm.value)}"`]]);
      case "decimal":
        return object([
          ["decimal", object([["value", text(required(arm.value.value, "decimal"))]])],
        ]);
      case "instant":
        return object([
          [
            "instant",
            object([
              ["nanos", u32(required(arm.value.nanos, "nanos"))],
              ["unixSeconds", s64(required(arm.value.unixSeconds, "unixSeconds"))],
            ]),
          ],
        ]);
      default:
        return refuse(`metadata scalar arm ${arm?.case} is not representable`);
    }
  };
  const sample = (record) => {
    const arm = record.value;
    let member;
    switch (arm.case) {
      case "numeric":
        member = ["numeric", dbl(arm.value)];
        break;
      case "digital":
        member = ["digital", arm.value ? "true" : "false"];
        break;
      case "eventId":
        member = ["eventId", text(idText(arm.value))];
        break;
      default:
        return refuse("sample has no value arm");
    }
    return object([
      ["channelId", text(idText(record.channelId))],
      ["deliveredOrdinal", u64(required(record.deliveredOrdinal, "deliveredOrdinal"))],
      ["faultIds", array(record.faultIds.map((faultId) => text(idText(faultId))))],
      member,
      ["tick", u64(required(record.tick, "tick"))],
      ["time", time(required(record.time, "time"))],
    ]);
  };
  const event = (item) =>
    object([
      ["channelId", text(idText(item.channelId))],
      ["duration", item.duration === undefined ? undefined : time(item.duration)],
      ["eventId", text(idText(item.eventId))],
      ["faultId", item.faultId === undefined ? undefined : text(idText(item.faultId))],
      [
        "fields",
        array(
          item.fields.map((entry) =>
            object([
              ["name", text(required(entry.name, "name"))],
              ["value", scalar(required(entry.value, "value"))],
            ]),
          ),
        ),
      ],
      ["kind", text(required(item.kind, "kind"))],
      ["start", time(required(item.start, "start"))],
    ]);
  const gap = (item) =>
    object([
      ["channelId", item.channelId === undefined ? undefined : text(idText(item.channelId))],
      ["faultId", text(idText(item.faultId))],
      ["kind", text(required(item.kind, "kind"))],
      ["startTick", u64(required(item.startTick, "startTick"))],
      ["tickCount", u64(required(item.tickCount, "tickCount"))],
    ]);
  return (segment) =>
    object([
      ["encodingProfile", text(required(segment.encodingProfile, "encodingProfile"))],
      ["events", array(segment.events.map(event))],
      ["executionProfile", text(required(segment.executionProfile, "executionProfile"))],
      ["gaps", array(segment.gaps.map(gap))],
      ["records", array(segment.records.map(sample))],
      ["startTick", u64(required(segment.startTick, "startTick"))],
      ["tickCount", u64(required(segment.tickCount, "tickCount"))],
    ]);
}
const encodeSegment = makeEncoder();

// ================================================================== strict JSON parser

// Parses JSON text into {k:"obj"|"arr"|"str"|"num"|"lit"} nodes, keeping member order, refusing
// duplicate members, BOM, trailing data, lone surrogates and any non-JSON token.
function parseJson(text, { allowDuplicates = false } = {}) {
  if (text.charCodeAt(0) === 0xfeff) refuse("byte order mark");
  let at = 0;
  const skipSpace = () => {
    while (at < text.length && " \t\n\r".includes(text[at])) at++;
  };
  const expect = (char) => {
    if (text[at] !== char) refuse(`expected ${char} at ${at}`);
    at++;
  };
  const parseString = () => {
    expect('"');
    let out = "";
    for (;;) {
      if (at >= text.length) refuse("unterminated string");
      const char = text[at++];
      const code = char.charCodeAt(0);
      if (char === '"') break;
      if (code < 0x20) refuse("raw control character in string");
      if (char !== "\\") {
        out += char;
        continue;
      }
      const escape = text[at++];
      switch (escape) {
        case '"':
        case "\\":
        case "/":
          out += escape;
          break;
        case "b":
          out += "\b";
          break;
        case "f":
          out += "\f";
          break;
        case "n":
          out += "\n";
          break;
        case "r":
          out += "\r";
          break;
        case "t":
          out += "\t";
          break;
        case "u": {
          const digits = text.slice(at, at + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(digits)) refuse("bad unicode escape");
          out += String.fromCharCode(Number.parseInt(digits, 16));
          at += 4;
          break;
        }
        default:
          refuse("bad escape");
      }
    }
    if (!out.isWellFormed()) refuse("unpaired surrogate");
    return out;
  };
  const parseValue = (depth) => {
    if (depth > 64) refuse("nesting too deep");
    skipSpace();
    const char = text[at];
    if (char === "{") {
      at++;
      const members = [];
      const seen = new Set();
      skipSpace();
      if (text[at] === "}") {
        at++;
        return { k: "obj", m: members };
      }
      for (;;) {
        skipSpace();
        const name = parseString();
        if (seen.has(name) && !allowDuplicates) refuse(`duplicate member ${name}`);
        seen.add(name);
        skipSpace();
        expect(":");
        members.push([name, parseValue(depth + 1)]);
        skipSpace();
        if (text[at] === ",") {
          at++;
          continue;
        }
        expect("}");
        return { k: "obj", m: members };
      }
    }
    if (char === "[") {
      at++;
      const items = [];
      skipSpace();
      if (text[at] === "]") {
        at++;
        return { k: "arr", a: items };
      }
      for (;;) {
        items.push(parseValue(depth + 1));
        skipSpace();
        if (text[at] === ",") {
          at++;
          continue;
        }
        expect("]");
        return { k: "arr", a: items };
      }
    }
    if (char === '"') return { k: "str", s: parseString() };
    for (const literal of ["true", "false", "null"]) {
      if (text.startsWith(literal, at)) {
        at += literal.length;
        return { k: "lit", v: literal };
      }
    }
    const number = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/.exec(text.slice(at));
    if (number) {
      at += number[0].length;
      return { k: "num", raw: number[0] };
    }
    return refuse(`unexpected token at ${at}`);
  };
  const root = parseValue(0);
  skipSpace();
  if (at !== text.length) refuse("trailing data");
  return root;
}

// ================================================================== strict profile reader

function members(node, required, optional = []) {
  if (node.k !== "obj") refuse("expected an object");
  const names = node.m.map(([name]) => name);
  for (let index = 1; index < names.length; index++) {
    if (!(names[index - 1] < names[index])) refuse("members are not strictly ascending");
  }
  const allowed = new Set([...required, ...optional]);
  for (const name of names) if (!allowed.has(name)) refuse(`unknown member ${name}`);
  const map = new Map(node.m);
  for (const name of required) if (!map.has(name)) refuse(`missing member ${name}`);
  return map;
}

function str(node) {
  if (node?.k !== "str") refuse("expected a string");
  return node.s;
}
function arr(node) {
  if (node?.k !== "arr") refuse("expected an array");
  return node.a;
}
function intString(node, pattern, min, max) {
  const value = str(node);
  if (!pattern.test(value)) refuse(`not canonical integer text: ${value}`);
  const parsed = BigInt(value);
  if (parsed < min || parsed > max) refuse("integer out of range");
  return parsed;
}
const uint64 = (node) => intString(node, /^(0|[1-9][0-9]*)$/, 0n, U64_MAX);
const sint64 = (node) => intString(node, /^(0|-?[1-9][0-9]*)$/, S64_MIN, S64_MAX);
const uint32 = (node) => Number(intString(node, /^(0|[1-9][0-9]*)$/, 0n, U32_MAX));
const readId = (node) => {
  const value = str(node);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)) {
    refuse("Id is not a lower-case hyphenated UUID");
  }
  return create(IdSchema, { value: bytesOfUuid(value) });
};
function readDouble(node) {
  const value = str(node);
  if (!/^[0-9a-f]{16}$/.test(value)) refuse("double is not 16 lower-case hex digits");
  const bits = BigInt(`0x${value}`);
  if (((bits >> 52n) & 0x7ffn) === 0x7ffn) refuse("nonfinite double");
  const view = new DataView(new ArrayBuffer(8));
  view.setBigUint64(0, bits, false);
  return view.getFloat64(0, false);
}
function readBool(node) {
  if (node?.k !== "lit" || (node.v !== "true" && node.v !== "false")) refuse("expected a bool");
  return node.v === "true";
}

function readTime(node) {
  const m = members(node, ["rate", "ticks"]);
  const rate = members(m.get("rate"), ["denominator", "numerator"]);
  const denominator = uint64(rate.get("denominator"));
  const numerator = sint64(rate.get("numerator"));
  if (denominator < 1n) refuse("rate denominator must be positive");
  if (numerator <= 0n) refuse("rate numerator must be positive");
  return create(ScopeTimeSchema, {
    ticks: sint64(m.get("ticks")),
    rate: create(RationalSchema, { numerator, denominator }),
  });
}

function readScalar(node) {
  if (node.k !== "obj" || node.m.length !== 1) refuse("metadata scalar needs exactly one arm");
  const [[arm, value]] = node.m;
  switch (arm) {
    case "text":
      return create(MetadataScalarSchema, { value: { case: "text", value: str(value) } });
    case "boolean":
      return create(MetadataScalarSchema, { value: { case: "boolean", value: readBool(value) } });
    case "integer":
      return create(MetadataScalarSchema, { value: { case: "integer", value: sint64(value) } });
    case "number":
      return create(MetadataScalarSchema, { value: { case: "number", value: readDouble(value) } });
    case "decimal": {
      const decimal = members(value, ["value"]);
      return create(MetadataScalarSchema, {
        value: {
          case: "decimal",
          value: create(DecimalSchema, { value: str(decimal.get("value")) }),
        },
      });
    }
    case "instant": {
      const instant = members(value, ["nanos", "unixSeconds"]);
      return create(MetadataScalarSchema, {
        value: {
          case: "instant",
          value: create(InstantSchema, {
            unixSeconds: sint64(instant.get("unixSeconds")),
            nanos: uint32(instant.get("nanos")),
          }),
        },
      });
    }
    default:
      return refuse(`metadata arm ${arm} is not representable in af-segment.v1`);
  }
}

function readSample(node) {
  const arms = ["numeric", "digital", "eventId"];
  const present = arms.filter((arm) => node.k === "obj" && node.m.some(([name]) => name === arm));
  if (present.length !== 1) refuse("a sample needs exactly one value arm");
  const m = members(node, [
    "channelId",
    "deliveredOrdinal",
    "faultIds",
    "tick",
    "time",
    present[0],
  ]);
  let value;
  if (present[0] === "numeric") value = { case: "numeric", value: readDouble(m.get("numeric")) };
  else if (present[0] === "digital") value = { case: "digital", value: readBool(m.get("digital")) };
  else value = { case: "eventId", value: readId(m.get("eventId")) };
  return create(SimulationSampleSchema, {
    channelId: readId(m.get("channelId")),
    deliveredOrdinal: uint64(m.get("deliveredOrdinal")),
    faultIds: arr(m.get("faultIds")).map(readId),
    tick: uint64(m.get("tick")),
    time: readTime(m.get("time")),
    value,
  });
}

function readEvent(node) {
  const m = members(
    node,
    ["channelId", "eventId", "fields", "kind", "start"],
    ["duration", "faultId"],
  );
  const init = {
    eventId: readId(m.get("eventId")),
    channelId: readId(m.get("channelId")),
    start: readTime(m.get("start")),
    kind: str(m.get("kind")),
    fields: arr(m.get("fields")).map((entry) => {
      const e = members(entry, ["name", "value"]);
      return create(MetadataEntrySchema, {
        name: str(e.get("name")),
        value: readScalar(e.get("value")),
      });
    }),
  };
  if (m.has("duration")) init.duration = readTime(m.get("duration"));
  if (m.has("faultId")) init.faultId = readId(m.get("faultId"));
  return create(SimulationEventSchema, init);
}

const gapKinds = new Set(["drop", "disconnect", "malformed"]);
function readGap(node) {
  const m = members(node, ["faultId", "kind", "startTick", "tickCount"], ["channelId"]);
  const kind = str(m.get("kind"));
  if (!gapKinds.has(kind)) refuse(`unknown gap kind ${kind}`);
  const init = {
    faultId: readId(m.get("faultId")),
    kind,
    startTick: uint64(m.get("startTick")),
    tickCount: uint64(m.get("tickCount")),
  };
  if (m.has("channelId")) init.channelId = readId(m.get("channelId"));
  return create(SimulationGapSchema, init);
}

// reader options only exist to prove which check is load bearing
function readSegment(text, { skipReencode = false, encoder = encodeSegment } = {}) {
  const root = parseJson(text);
  const m = members(root, [
    "encodingProfile",
    "events",
    "executionProfile",
    "gaps",
    "records",
    "startTick",
    "tickCount",
  ]);
  const encodingProfile = str(m.get("encodingProfile"));
  if (encodingProfile !== "af-segment.v1") refuse("encodingProfile");
  const executionProfile = str(m.get("executionProfile"));
  if (executionProfile !== "af-sim.v1") refuse("executionProfile");
  const records = arr(m.get("records")).map(readSample);
  for (let index = 1; index < records.length; index++) {
    if (!(records[index - 1].deliveredOrdinal < records[index].deliveredOrdinal)) {
      refuse("records must be strictly ascending by deliveredOrdinal");
    }
  }
  const segment = create(SimulationDataSegmentSchema, {
    encodingProfile,
    executionProfile,
    startTick: uint64(m.get("startTick")),
    tickCount: uint64(m.get("tickCount")),
    records,
    events: arr(m.get("events")).map(readEvent),
    gaps: arr(m.get("gaps")).map(readGap),
  });
  if (!skipReencode && encoder(segment) !== text) refuse("not byte-for-byte canonical");
  return segment;
}

function accepts(text, options) {
  try {
    readSegment(text, options);
    return true;
  } catch (error) {
    if (error instanceof Refused) return false;
    throw error;
  }
}

// ================================================================== fixture model -> generated message

function bytesOfUuid(uuid) {
  const h = uuid.replaceAll("-", "");
  assert.match(h, /^[0-9a-f]{32}$/);
  return Uint8Array.from(h.match(/../g).map((pair) => Number.parseInt(pair, 16)));
}
const modelId = (uuid) => create(IdSchema, { value: bytesOfUuid(uuid) });
function modelTime(time) {
  return create(ScopeTimeSchema, {
    ticks: BigInt(time.ticks),
    rate: create(RationalSchema, {
      numerator: BigInt(time.rate.numerator),
      denominator: BigInt(time.rate.denominator),
    }),
  });
}
function modelScalar(value) {
  const [arm] = Object.keys(value);
  const raw = value[arm];
  switch (arm) {
    case "text":
    case "boolean":
      return create(MetadataScalarSchema, { value: { case: arm, value: raw } });
    case "integer":
      return create(MetadataScalarSchema, { value: { case: "integer", value: BigInt(raw) } });
    case "number":
      return create(MetadataScalarSchema, { value: { case: "number", value: Number(raw) } });
    case "decimal":
      return create(MetadataScalarSchema, {
        value: { case: "decimal", value: create(DecimalSchema, { value: raw }) },
      });
    case "instant":
      return create(MetadataScalarSchema, {
        value: {
          case: "instant",
          value: create(InstantSchema, {
            unixSeconds: BigInt(raw.unixSeconds),
            nanos: Number(raw.nanos),
          }),
        },
      });
    default:
      return assert.fail(`unknown model arm ${arm}`);
  }
}
function modelSegment(model) {
  return create(SimulationDataSegmentSchema, {
    encodingProfile: model.encodingProfile,
    executionProfile: model.executionProfile,
    startTick: BigInt(model.startTick),
    tickCount: BigInt(model.tickCount),
    records: model.records.map((record) => {
      const [arm] = Object.keys(record.value);
      const raw = record.value[arm];
      const value =
        arm === "numeric"
          ? { case: "numeric", value: Number(raw) }
          : arm === "digital"
            ? { case: "digital", value: raw }
            : { case: "eventId", value: modelId(raw) };
      return create(SimulationSampleSchema, {
        channelId: modelId(record.channelId),
        tick: BigInt(record.tick),
        deliveredOrdinal: BigInt(record.deliveredOrdinal),
        time: modelTime(record.time),
        value,
        faultIds: record.faultIds.map(modelId),
      });
    }),
    events: model.events.map((event) => {
      const init = {
        eventId: modelId(event.eventId),
        channelId: modelId(event.channelId),
        start: modelTime(event.start),
        kind: event.kind,
        fields: event.fields.map((entry) =>
          create(MetadataEntrySchema, { name: entry.name, value: modelScalar(entry.value) }),
        ),
      };
      if (event.duration !== undefined) init.duration = modelTime(event.duration);
      if (event.faultId !== undefined) init.faultId = modelId(event.faultId);
      return create(SimulationEventSchema, init);
    }),
    gaps: model.gaps.map((gap) => {
      const init = {
        faultId: modelId(gap.faultId),
        kind: gap.kind,
        startTick: BigInt(gap.startTick),
        tickCount: BigInt(gap.tickCount),
      };
      if (gap.channelId !== undefined) init.channelId = modelId(gap.channelId);
      return create(SimulationGapSchema, init);
    }),
  });
}

const sha256Hex = (text) => createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
const vectorById = (id) => fixture.vectors.find((vector) => vector.id === id);
const refusalById = (id) => fixture.refusals.find((refusal) => refusal.id === id);
const clone = (message) => {
  const roundTripped = fromBinary(
    SimulationDataSegmentSchema,
    toBinary(SimulationDataSegmentSchema, message),
  );
  return roundTripped;
};

// ================================================================== tests

test("CON.25 af-segment fixture ids are the exact authorized sets", () => {
  assert.equal(fixture.schemaVersion.length > 0, true);
  assert.equal(fixture.profile.id, "af-segment.v1");
  assert.equal(fixture.profile.executionProfile, "af-sim.v1");
  const vectorIds = fixture.vectors.map((vector) => vector.id);
  assert.equal(new Set(vectorIds).size, vectorIds.length, "vector ids are unique");
  assert.deepEqual([...vectorIds].sort(), [...expectedVectorIds].sort());
  const refusalIds = fixture.refusals.map((refusal) => refusal.id);
  assert.equal(new Set(refusalIds).size, refusalIds.length, "refusal ids are unique");
  assert.deepEqual([...refusalIds].sort(), [...expectedRefusalIds].sort());
  assert.equal(new Set(fixture.vectors.map((vector) => vector.canonicalJson)).size, 7);
});

test("CON.25 af-segment ENCODE: every positive vector matches the golden text, length and SHA-256", () => {
  const consumed = new Set();
  for (const vector of fixture.vectors) {
    assert.ok(!consumed.has(vector.id), `duplicate consumption ${vector.id}`);
    consumed.add(vector.id);
    assert.ok(expectedVectorIds.includes(vector.id), `unknown vector ${vector.id}`);
    const message = modelSegment(vector.segment);
    assert.equal(encodeSegment(message), vector.canonicalJson, `${vector.id}: canonical text`);
    assert.equal(
      Buffer.byteLength(vector.canonicalJson, "utf8"),
      vector.utf8Bytes,
      `${vector.id}: utf8 byte length`,
    );
    assert.equal(sha256Hex(vector.canonicalJson), vector.sha256, `${vector.id}: sha256`);
    assert.equal(vector.canonicalJson.charCodeAt(0), 0x7b, "no byte order mark");
    assert.equal(
      shapes.isSimulationDataSegment(message),
      true,
      `${vector.id}: generated validator`,
    );

    // presence semantics survive protobuf bytes: optional, oneof and repeated members
    const round = clone(message);
    assert.ok(
      equals(SimulationDataSegmentSchema, message, round),
      `${vector.id}: protobuf round trip`,
    );
    assert.equal(
      encodeSegment(round),
      vector.canonicalJson,
      `${vector.id}: encode after round trip`,
    );
    assert.equal(shapes.isSimulationDataSegment(round), true);
    // the canonical text is not protobuf output and is not JSON.stringify of the generated message
    assert.notEqual(
      Buffer.from(toBinary(SimulationDataSegmentSchema, message)).toString("utf8"),
      vector.canonicalJson,
    );
  }
  assert.deepEqual([...consumed].sort(), [...expectedVectorIds].sort());
});

test("CON.25 af-segment ENCODE: presence and bit-level facts hold in the golden bytes", () => {
  const binary = vectorById("binary64-bit-words-preserve-sign-and-extremes");
  const message = modelSegment(binary.segment);
  assert.ok(Object.is(message.records[0].value.value, -0), "-0 parsed to negative zero");
  assert.equal(message.records[2].value.value, 5e-324);
  assert.match(binary.canonicalJson, /"numeric":"8000000000000000"/);
  assert.match(binary.canonicalJson, /"numeric":"0000000000000001"/);
  assert.match(binary.canonicalJson, /"numeric":"7fefffffffffffff"/);
  const round = clone(message);
  assert.ok(Object.is(round.records[0].value.value, -0), "negative zero survives protobuf bytes");
  assert.ok(Object.is(round.records[1].value.value, 0));

  const gaps = modelSegment(vectorById("gap-and-fault-markers-with-and-without-channel").segment);
  assert.equal(gaps.records[0].value.case, "digital");
  assert.equal(gaps.records[0].value.value, false, "explicit digital false is a selected arm");
  assert.equal(clone(gaps).records[0].value.case, "digital");
  assert.equal(gaps.gaps[1].channelId, undefined);
  assert.equal(clone(gaps).gaps[1].channelId, undefined, "absent optional channelId stays absent");
  assert.ok(gaps.events[0].duration === undefined && clone(gaps).events[0].duration === undefined);
  assert.match(
    vectorById("gap-and-fault-markers-with-and-without-channel").canonicalJson,
    /"digital":false/,
  );

  const empty = modelSegment(
    vectorById("empty-segment-keeps-every-ordered-repeated-field").segment,
  );
  const emptyRound = clone(empty);
  assert.deepEqual(
    [emptyRound.records.length, emptyRound.events.length, emptyRound.gaps.length],
    [0, 0, 0],
  );
  assert.equal(emptyRound.startTick, 0n, "explicit zero startTick keeps presence");
  assert.equal(
    encodeSegment(emptyRound),
    '{"encodingProfile":"af-segment.v1","events":[],"executionProfile":"af-sim.v1","gaps":[],"records":[],"startTick":"0","tickCount":"0"}',
  );

  const unicode = vectorById("text-metadata-escapes-and-unicode");
  const text = modelSegment(unicode.segment).events[0].fields[0].value.value.value;
  assert.equal(text, 'a"b\\c\n\t\u0001\u001b\u007fé中😀');
  assert.ok(unicode.canonicalJson.includes("\\u0001\\u001b\u007fé中😀"));
  assert.ok(unicode.canonicalJson.includes('\\"b\\\\c\\n\\t'));
  assert.ok(
    unicode.utf8Bytes > unicode.canonicalJson.length,
    "non-ASCII is literal multi-byte UTF-8",
  );

  const integral = modelSegment(vectorById("integral-extremes-use-exact-strings").segment);
  assert.equal(integral.records[1].tick, U64_MAX);
  assert.equal(integral.records[0].time.ticks, S64_MIN);
  assert.equal(integral.records[1].time.ticks, S64_MAX);
});

test("CON.25 af-segment STRICT READ: every positive text is accepted and re-encodes byte-identically", () => {
  for (const vector of fixture.vectors) {
    const read = readSegment(vector.canonicalJson);
    assert.equal(encodeSegment(read), vector.canonicalJson, `${vector.id}: re-encode`);
    assert.ok(
      equals(SimulationDataSegmentSchema, read, modelSegment(vector.segment)),
      `${vector.id}: model`,
    );
    assert.equal(
      shapes.isSimulationDataSegment(read),
      true,
      `${vector.id}: validator on read message`,
    );
    assert.ok(
      equals(SimulationDataSegmentSchema, read, clone(read)),
      `${vector.id}: read message survives protobuf bytes`,
    );
    // the reader's parse tree re-serializes (independently of the encoder) to the very same text
    assert.equal(
      emit(parseJson(vector.canonicalJson)),
      vector.canonicalJson,
      `${vector.id}: parse tree`,
    );
  }
});

// minimal tree printer used to prove the parser is lossless for canonical text
function emit(node) {
  switch (node.k) {
    case "obj":
      return `{${node.m.map(([name, value]) => `${emitString(name)}:${emit(value)}`).join(",")}}`;
    case "arr":
      return `[${node.a.map(emit).join(",")}]`;
    case "str":
      return emitString(node.s);
    case "num":
      return node.raw;
    default:
      return node.v;
  }
}
function emitString(value) {
  let out = '"';
  for (const char of value) {
    const code = char.codePointAt(0);
    if (char === '"') out += '\\"';
    else if (char === "\\") out += "\\\\";
    else if (code === 8) out += "\\b";
    else if (code === 9) out += "\\t";
    else if (code === 10) out += "\\n";
    else if (code === 12) out += "\\f";
    else if (code === 13) out += "\\r";
    else if (code < 0x20) out += `\\u${code.toString(16).padStart(4, "0")}`;
    else out += char;
  }
  return `${out}"`;
}

test("CON.25 af-segment STRICT READ: every refusal text is refused", () => {
  const consumed = new Set();
  for (const refusal of fixture.refusals) {
    assert.ok(!consumed.has(refusal.id), `duplicate consumption ${refusal.id}`);
    consumed.add(refusal.id);
    assert.ok(expectedRefusalIds.includes(refusal.id), `unknown refusal ${refusal.id}`);
    assert.equal(typeof refusal.reason, "string");
    assert.equal(accepts(refusal.canonicalJson), false, `${refusal.id}: must be refused`);
    assert.ok(
      !fixture.vectors.some((vector) => vector.canonicalJson === refusal.canonicalJson),
      `${refusal.id}: is not a positive text`,
    );
  }
  assert.deepEqual([...consumed].sort(), [...expectedRefusalIds].sort());
});

test("CON.25 af-segment reader discrimination: the lexical checks and the re-encode comparison are each load bearing", () => {
  // Without the byte comparison only the lexical-only refusals slip through.
  const slipped = fixture.refusals
    .filter((refusal) => accepts(refusal.canonicalJson, { skipReencode: true }))
    .map((refusal) => refusal.id);
  assert.deepEqual(slipped.sort(), [...reencodeOnlyRefusals].sort());
  // An encoder that does not sort members makes the byte comparison refuse canonical text.
  const unsorted = makeEncoder({ noSort: true });
  assert.equal(
    fixture.vectors.some((vector) => !accepts(vector.canonicalJson, { encoder: unsorted })),
    true,
  );
  // An encoder that is too lenient would accept the whitespace text only if the comparison were absent.
  const whitespace = refusalById("refuse-insignificant-whitespace").canonicalJson;
  assert.equal(accepts(whitespace), false);
  assert.equal(accepts(whitespace, { skipReencode: true }), true);
});

test("CON.25 af-segment flipping a refusal to canonical form makes it accepted", () => {
  const lowerUuids = (text) =>
    text.replace(
      /[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}/g,
      (m) => m.toLowerCase(),
    );
  const lowerHexWords = (text) =>
    text.replace(/"(?:numeric|number)":"([0-9A-F]{16})"/g, (m) => m.toLowerCase());
  const removeSpaceOutsideStrings = (text) => {
    let out = "";
    let inString = false;
    for (let index = 0; index < text.length; index++) {
      const char = text[index];
      if (inString) {
        out += char;
        if (char === "\\") out += text[++index];
        else if (char === '"') inString = false;
      } else if (char === '"') {
        inString = true;
        out += char;
      } else if (char !== " ") out += char;
    }
    return out;
  };
  const repairs = {
    "refuse-uppercase-uuid": lowerUuids,
    "refuse-uppercase-hex-double": lowerHexWords,
    "refuse-uppercase-escape-digits": (text) =>
      text.replace(/\\u00[0-9A-F]{2}/g, (m) => m.toLowerCase()),
    "refuse-insignificant-whitespace": removeSpaceOutsideStrings,
    "refuse-unsorted-members": (text) =>
      text.replace(
        '{"events":[],"encodingProfile":"af-segment.v1",',
        '{"encodingProfile":"af-segment.v1","events":[],',
      ),
    "refuse-wrong-encoding-profile": (text) => text.replace("af-segment.v2", "af-segment.v1"),
    "refuse-wrong-execution-profile": (text) => text.replace("af-sim.v2", "af-sim.v1"),
    "refuse-duplicate-member": (text) => text.replace('"gaps":[],"gaps":[],', '"gaps":[],'),
    "refuse-unknown-member": (text) => text.replace('"zzz":"1",', ""),
    "refuse-missing-empty-repeated": (text) =>
      text.replace('"executionProfile":"af-sim.v1",', '"executionProfile":"af-sim.v1","gaps":[],'),
    "refuse-null-for-absent-optional": (text) => text.replace('"duration":null,', ""),
    "refuse-leading-zero-uint64": (text) => text.replace(/"(0)(\d+)"/, '"$2"'),
  };
  let repaired = 0;
  for (const [id, repair] of Object.entries(repairs)) {
    const text = refusalById(id).canonicalJson;
    assert.equal(accepts(text), false, `${id}: refused as published`);
    const fixed = repair(text);
    assert.notEqual(fixed, text, `${id}: the repair changed the text`);
    assert.equal(accepts(fixed), true, `${id}: accepted once canonical`);
    repaired++;
  }
  assert.equal(repaired, 12);
  // JSON number for an uint64 and the oneof pair are repaired structurally.
  const twoArms = refusalById("refuse-two-oneof-arms").canonicalJson;
  assert.equal(
    accepts(twoArms.replace(/,"digital":(true|false)/, "").replace(/"digital":(true|false),/, "")),
    true,
  );
});

test("CON.25 af-segment strict parser refuses non-canonical JSON on its own", () => {
  assert.throws(() => parseJson('{"a":"1","a":"2"}'), Refused);
  assert.equal(parseJson('{"a":"1","a":"2"}', { allowDuplicates: true }).m.length, 2);
  for (const bad of [
    "﻿{}",
    "{} ",
    "{}x",
    "{'a':1}",
    '{"a":01}',
    '{"a":NaN}',
    '{"a":"\\ud800"}',
    '{"a":"\\x"}',
    '{"a":"\u0001"}',
    '{"a":"x}',
    '{"a":[1,]}',
  ]) {
    if (bad === "{} ") {
      // trailing whitespace is JSON-valid; the byte comparison refuses it
      assert.equal(accepts(bad), false);
      continue;
    }
    assert.throws(() => parseJson(bad), Refused, `parser must refuse ${JSON.stringify(bad)}`);
  }
  // wrong JSON types where a string is required
  const text = vectorById("empty-segment-keeps-every-ordered-repeated-field").canonicalJson;
  assert.equal(accepts(text.replace('"startTick":"0"', '"startTick":0')), false);
  assert.equal(accepts(text.replace('"startTick":"0"', '"startTick":null')), false);
  assert.equal(accepts(text.replace('"events":[]', '"events":{}')), false);
  assert.equal(accepts(text.replace('"startTick":"0"', '"startTick":"+0"')), false);
  assert.equal(accepts(text.replace('"startTick":"0"', '"startTick":"-0"')), false);
  assert.equal(
    accepts(text.replace('"startTick":"0"', '"startTick":"18446744073709551616"')),
    false,
  );
  assert.equal(accepts(text), true);
  // a hex double is refused as a JSON number or padded text, and 0x7ff exponents are nonfinite
  const numeric = vectorById(
    "duplicate-delivery-differs-only-by-ordinal-and-fault-marker",
  ).canonicalJson;
  assert.equal(accepts(numeric), true);
  for (const word of ["7ff8000000000000", "fff0000000000000", "7ff0000000000001"]) {
    assert.equal(accepts(numeric.replaceAll("400a000000000000", word)), false, word);
  }
});

test("CON.25 af-segment encoder mutations are caught by the golden bytes", () => {
  const mutations = {
    "members left unsorted": { noSort: true },
    "double printed with toString": { doubleToString: true },
    "non-ASCII escaped": { escapeNonAscii: true },
    "empty repeated members omitted": { omitEmpty: true },
  };
  for (const [name, mutation] of Object.entries(mutations)) {
    const mutated = makeEncoder(mutation);
    const differing = fixture.vectors.filter((vector) => {
      try {
        return mutated(modelSegment(vector.segment)) !== vector.canonicalJson;
      } catch (error) {
        if (error instanceof Refused) return true;
        throw error;
      }
    });
    assert.ok(differing.length > 0, `${name}: at least one golden vector must catch the mutation`);
    // the faithful encoder still matches all of them
    assert.equal(
      fixture.vectors.every(
        (vector) => encodeSegment(modelSegment(vector.segment)) === vector.canonicalJson,
      ),
      true,
    );
  }
  // a signed zero collapsed to +0 is also caught
  const binary = vectorById("binary64-bit-words-preserve-sign-and-extremes");
  const collapsed = modelSegment(binary.segment);
  collapsed.records[0].value.value = 0;
  assert.notEqual(encodeSegment(collapsed), binary.canonicalJson);
  // a digital false that lost its arm is not representable
  const gaps = modelSegment(vectorById("gap-and-fault-markers-with-and-without-channel").segment);
  gaps.records[0].value = { case: undefined };
  assert.throws(() => encodeSegment(gaps), Refused);
  // an out-of-range uint64 cannot be encoded
  const range = modelSegment(
    vectorById("empty-segment-keeps-every-ordered-repeated-field").segment,
  );
  range.startTick = U64_MAX + 1n;
  assert.throws(() => encodeSegment(range), Refused);
  // a resource scalar arm is not representable
  const resource = modelSegment(
    vectorById("numeric-digital-and-event-samples-in-delivered-order").segment,
  );
  resource.events[0].fields[0].value.value = { case: "resource", value: undefined };
  assert.throws(() => encodeSegment(resource), Refused);
  // an unpaired surrogate is refused by the encoder
  const lone = modelSegment(vectorById("text-metadata-escapes-and-unicode").segment);
  lone.events[0].fields[0].value.value = { case: "text", value: "\ud800" };
  assert.throws(() => encodeSegment(lone), Refused);
  // a nonfinite numeric is refused by the encoder
  const nan = modelSegment(
    vectorById("duplicate-delivery-differs-only-by-ordinal-and-fault-marker").segment,
  );
  nan.records[0].value = { case: "numeric", value: Number.NaN };
  assert.throws(() => encodeSegment(nan), Refused);
});

test("CON.25 af-segment generated validator rejects invalid built messages", () => {
  const base = modelSegment(vectorById("gap-and-fault-markers-with-and-without-channel").segment);
  assert.equal(shapes.isSimulationDataSegment(base), true);
  const mutate = (change) => {
    const copy = clone(base);
    change(copy);
    return shapes.isSimulationDataSegment(copy);
  };
  assert.equal(
    mutate(() => {}),
    true,
    "unmodified clone is valid",
  );
  assert.equal(
    mutate((m) => (m.gaps[0].kind = "explode")),
    false,
    "unknown gap kind",
  );
  assert.equal(
    mutate((m) => (m.gaps[0].kind = "drop")),
    true,
    "known gap kind",
  );
  assert.equal(
    mutate((m) => (m.encodingProfile = "af-segment.v2")),
    false,
    "wrong encoding profile",
  );
  assert.equal(
    mutate((m) => (m.executionProfile = "af-sim.v2")),
    false,
    "wrong execution profile",
  );
  assert.equal(
    mutate((m) => (m.records[0].channelId = create(IdSchema, { value: new Uint8Array(16) }))),
    false,
    "zero Id",
  );
  assert.equal(
    mutate((m) => (m.records[0].value = { case: undefined })),
    false,
    "missing oneof arm",
  );
  assert.equal(
    mutate((m) => (m.records[0].value = { case: "numeric", value: Number.NaN })),
    false,
    "NaN numeric",
  );
  assert.equal(
    mutate((m) => (m.records[0].value = { case: "numeric", value: Number.POSITIVE_INFINITY })),
    false,
    "infinite numeric",
  );
  assert.equal(
    mutate((m) => (m.startTick = undefined)),
    false,
    "missing startTick",
  );
  assert.equal(
    mutate((m) => (m.events[0].kind = "")),
    false,
    "empty event kind",
  );
  assert.equal(
    mutate((m) => (m.gaps[0].faultId = undefined)),
    false,
    "gap without faultId",
  );
  assert.equal(
    mutate((m) => (m.records[0].deliveredOrdinal = undefined)),
    false,
    "missing ordinal",
  );
});
