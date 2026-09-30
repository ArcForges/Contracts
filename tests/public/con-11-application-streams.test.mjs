// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import * as application from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/application_pb.js";
import * as events from "../../src/public/ts/proto/dist/gen/arcforges/events/v1/events_pb.js";
import * as content from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js";
import * as foundation from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";

const fixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/public/con-11-application-streams.json", import.meta.url),
    "utf8",
  ),
);
const operations = JSON.parse(
  await readFile(new URL("../../eng/operations/con-11.json", import.meta.url), "utf8"),
).operations;
const files = [
  application.file_arcforges_publicapi_v1_application,
  events.file_arcforges_events_v1_events,
  content.file_arcforges_publicapi_v1_content,
  foundation.file_arcforges_foundation_v1_foundation,
];
const messages = files.flatMap((file) => file.messages);
const seen = new Set();
const id = { value: Uint8Array.from({ length: 16 }, (_, i) => i) };

function testId(suffix) {
  const value = id.value.slice();
  value[15] = suffix;
  return { value };
}

function consume(vector) {
  assert.equal(seen.has(vector.id), false, `fixture vector consumed only once: ${vector.id}`);
  seen.add(vector.id);
}

function messageDescriptor(name) {
  const descriptor = messages.find((message) => message.typeName.split(".").at(-1) === name);
  assert.ok(descriptor, `generated descriptor exists: ${name}`);
  return descriptor;
}

function messageSchema(name) {
  const key = `${name}Schema`;
  const descriptor = [application, events, content, foundation]
    .map((module) => module[key])
    .find((value) => value !== undefined);
  assert.ok(descriptor, `generated message schema exists: ${name}`);
  return descriptor;
}

function assertFields(name, expected, label = name) {
  const actual = messageDescriptor(name)
    .fields.map((field) => [field.localName, field.number])
    .sort((left, right) => left[1] - right[1]);
  assert.deepEqual(
    actual,
    [...expected].sort((left, right) => left[1] - right[1]),
    `exact field names/tags: ${label}`,
  );
}

function assertServiceMethods(file, expectedByService) {
  assert.deepEqual(
    file.services.map((service) => service.typeName).sort(),
    [...expectedByService.keys()].sort(),
  );
  for (const service of file.services) {
    const actual = service.methods.map((method) => method.name).sort();
    assert.deepEqual(
      actual,
      [...expectedByService.get(service.typeName)].sort(),
      `exact service method set: ${service.typeName}`,
    );
  }
}

function chunkWithData(dataBytes) {
  const data = new Uint8Array(dataBytes);
  return create(events.OutputChunkSchema, {
    execution: { taskId: id },
    offset: 1n,
    data,
    chunkHash: createHash("sha256").update(data).digest("hex"),
    kind: "text",
    attemptId: id,
    streamId: id,
  });
}

function frameWithData(dataBytes) {
  return create(events.StreamFrameSchema, {
    meta: { correlationId: id },
    position: { cursor: "c", sequence: 1n, generation: 1n },
    frame: { case: "output", value: chunkWithData(dataBytes) },
  });
}

function exactBinarySize(target, build, maximumInput) {
  let low = 0;
  let high = maximumInput;
  while (low <= high) {
    const candidate = Math.floor((low + high) / 2);
    const bytes = build(candidate);
    if (bytes.length === target) return bytes;
    if (bytes.length < target) low = candidate + 1;
    else high = candidate - 1;
  }
  assert.fail(`could not construct exact protobuf byte length ${target}`);
}

function archiveWithText(textLength) {
  const record = create(application.HistoryArchiveRecordSchema, {
    record: {
      case: "message",
      value: {
        ordinal: 0n,
        createdAt: { unixSeconds: 1n },
        message: {
          messageId: testId(1),
          conversationId: testId(2),
          branchId: testId(3),
          role: "user",
          parts: [{ text: "x".repeat(textLength) }],
          state: "complete",
          revision: { value: 1n },
        },
      },
    },
  });
  return toBinary(application.HistoryArchiveRecordSchema, record);
}

test("CON.11 generated RPC catalogues and all independently-authored descriptor vectors match", () => {
  const rpcVectors = fixture.rpcVectors;
  assert.equal(rpcVectors.length, 14);
  assert.equal(operations.length, 14);
  assert.equal(new Set(operations.map((row) => row.operationId)).size, 14);
  assertServiceMethods(
    application.file_arcforges_publicapi_v1_application,
    new Map([
      ["arcforges.publicapi.v1.ApplicationService", ["List", "Heartbeat", "Disconnect"]],
      [
        "arcforges.publicapi.v1.HistoryService",
        ["BeginImport", "FinalizeImport", "GetImport", "CancelImport"],
      ],
    ]),
  );
  assertServiceMethods(
    events.file_arcforges_events_v1_events,
    new Map([
      [
        "arcforges.events.v1.ExecutionService",
        ["StartTransientTurn", "ReadOutput", "WatchOutput", "AcknowledgeOutput", "PurgeTransient"],
      ],
      ["arcforges.events.v1.EventService", ["Poll", "Watch"]],
    ]),
  );

  const methods = new Map(
    files.flatMap((file) =>
      file.services.flatMap((service) =>
        service.methods.map((method) => [`${service.typeName}/${method.name}`, method]),
      ),
    ),
  );
  for (const vector of rpcVectors) {
    consume(vector);
    const binding = `${vector.service}/${vector.method}`;
    const method = methods.get(binding);
    assert.ok(method, `generated RPC exists: ${binding}`);
    assert.equal(method.input.typeName.split(".").at(-1), vector.input, `request type: ${binding}`);
    assert.equal(
      method.output.typeName.split(".").at(-1),
      vector.output,
      `response type: ${binding}`,
    );
    assertFields(vector.input, vector.inputFields, `${binding} request`);
    const row = operations.find((candidate) => candidate.operationId === vector.operationId);
    assert.ok(row, `distinct operation export row: ${vector.operationId}`);
    assert.equal(row.binding, binding);
    assert.equal(
      row.source,
      vector.service.startsWith("arcforges.publicapi.")
        ? "public/proto/arcforges/publicapi/v1/application.proto"
        : "public/proto/arcforges/events/v1/events.proto",
    );
    assert.equal(row.kind, "proto");
    assert.equal(row.surface, "public");
    if (vector.operationId === "events.poll") {
      const auth = row.authorization;
      assert.equal(row.scope, fixture.pollProfile.scope);
      assert.equal(row.idempotency, fixture.pollProfile.idempotency);
      assert.equal(fixture.pollProfile.compatibility, "AO");
      assert.equal(auth.capability, fixture.pollProfile.capability);
      assert.equal(auth.risk, fixture.pollProfile.risk);
      assert.equal(auth.approval, fixture.pollProfile.approval);
      assert.equal(auth.stepUp, fixture.pollProfile.stepUp);
      assert.equal(auth.localPresence, fixture.pollProfile.localPresence);
      assert.equal(auth.egress, fixture.pollProfile.egress);
      assert.equal(auth.patEligible, fixture.pollProfile.patEligible);
      assert.deepEqual(auth.actorKinds, fixture.pollProfile.actorKinds);
      assert.equal(
        fixture.pollProfile.retry,
        "sameCursorPureQuery; authorizationRefusalWaitsForNewSession; unavailableUsesRetryAfterBackoff",
      );
      assert.equal(
        fixture.pollProfile.noCursor,
        "emptyPageWithSignedHighWaterCursorAndResetRequired",
      );
    }
    if (
      [
        "application.list",
        "history.getImport",
        "execution.readOutput",
        "execution.watchOutput",
        "events.watch",
      ].includes(vector.operationId)
    )
      assert.equal(
        row.authorization.egress,
        "none",
        `authorized response is not a new egress destination: ${vector.operationId}`,
      );
    if (vector.operationId === "execution.startTransientTurn")
      assert.equal(
        row.authorization.egress,
        "existingAdmissionContextPolicyToSelectedCloudOrWorkersAiRoute",
      );
    if (vector.operationId === "history.beginImport")
      assert.equal(row.authorization.egress, "thisApplicationAdmittedCloudHistoryDestinationOnly");
    if (vector.operationId === "history.finalizeImport")
      assert.equal(row.authorization.egress, "recordedBeginConsentDestinationAndSnapshotOnly");
  }

  for (const vector of fixture.messageFieldVectors) {
    consume(vector);
    const expectedFields =
      vector.message === "Event"
        ? [
            ...vector.fields,
            ...fixture.eventPayloadVectors.map((payload) => [payload.field, payload.tag]),
          ]
        : vector.fields;
    assertFields(vector.message, expectedFields, vector.id);
    if (vector.oneofFields) {
      const descriptor = messageDescriptor(vector.message);
      for (const [name, fields] of Object.entries(vector.oneofFields)) {
        const oneof = descriptor.oneofs.find((candidate) => candidate.name === name);
        assert.ok(oneof, `oneof exists: ${vector.id}/${name}`);
        assert.deepEqual(
          oneof.fields.map((field) => field.localName),
          fields,
          `closed oneof: ${vector.id}/${name}`,
        );
      }
    }
  }

  const eventPayloads = fixture.eventPayloadVectors;
  const event = messageDescriptor("Event");
  assert.deepEqual(
    event.oneofs
      .find((oneof) => oneof.name === "payload")
      .fields.map((field) => [field.localName, field.number]),
    eventPayloads.map((vector) => [vector.field, vector.tag]),
  );
  for (const vector of eventPayloads) {
    consume(vector);
    assertFields(vector.message, vector.fields, vector.id);
    const value = create(messageSchema(vector.message), {});
    const encoded = toBinary(
      events.EventSchema,
      create(events.EventSchema, {
        payload: { case: vector.field, value },
      }),
    );
    assert.equal(
      fromBinary(events.EventSchema, encoded).payload.case,
      vector.field,
      `generated event oneof round trip: ${vector.id}`,
    );
  }

  const readProjectionIds = new Set(fixture.unaryOutcomeProfile.readProjectionOperationIds);
  for (const vector of rpcVectors.filter((candidate) => candidate.streamType === "unary")) {
    const response = messageDescriptor(vector.output);
    const outcome = response.oneofs.find((oneof) => oneof.name === "outcome");
    assert.ok(outcome, `unary outcome oneof: ${vector.output}`);
    const expected = [
      ["value", 2],
      ["error", 3],
    ];
    if (readProjectionIds.has(vector.operationId)) expected.push(["encodedBody", 4]);
    assert.deepEqual(
      outcome.fields.map((field) => [field.localName, field.number]),
      expected,
      `closed outcome alternatives: ${vector.operationId}`,
    );
  }
});

test("CON.11 aggregate and serialized-byte boundary fixtures round-trip at and over their limits", () => {
  for (const vector of fixture.aggregateBoundaryVectors.transcriptPartTotals) {
    consume(vector);
    const messages = vector.perMessageCounts.map((count, index) =>
      create(application.TranscriptMessageSchema, {
        messageId: testId(index + 1),
        ordinal: BigInt(index),
        role: 1,
        parts: Array.from({ length: count }, () =>
          create(content.MessagePartSchema, { text: "x" }),
        ),
      }),
    );
    const wire = toBinary(
      application.TranscriptWindowSchema,
      create(application.TranscriptWindowSchema, {
        branchId: testId(3),
        branchRevision: 1n,
        messages,
        firstOrdinal: 0n,
        lastOrdinal: BigInt(messages.length - 1),
        windowHash: "a".repeat(64),
      }),
    );
    const parsed = fromBinary(application.TranscriptWindowSchema, wire);
    const actual = parsed.messages.reduce((total, message) => total + message.parts.length, 0);
    assert.equal(
      actual,
      vector.perMessageCounts.reduce((total, count) => total + count, 0),
    );
    assert.equal(actual <= vector.limit, vector.valid, vector.id);
    assert.ok(wire.byteLength > 0);
  }

  for (const vector of fixture.aggregateBoundaryVectors.archiveRecordBytes) {
    consume(vector);
    const wire = exactBinarySize(vector.serializedBytes, archiveWithText, vector.serializedBytes);
    const parsed = fromBinary(application.HistoryArchiveRecordSchema, wire);
    assert.equal(parsed.record.case, "message");
    assert.equal(
      toBinary(application.HistoryArchiveRecordSchema, parsed).byteLength,
      vector.serializedBytes,
    );
    assert.equal(wire.byteLength <= vector.limit, vector.valid, vector.id);
  }

  for (const vector of fixture.aggregateBoundaryVectors.outputChunkBytes) {
    consume(vector);
    const wire = exactBinarySize(
      vector.serializedBytes,
      (length) => toBinary(events.OutputChunkSchema, chunkWithData(length)),
      32768,
    );
    assert.equal(
      fromBinary(events.OutputChunkSchema, wire).data.byteLength <= vector.limit,
      vector.valid,
      vector.id,
    );
    assert.equal(wire.byteLength, vector.serializedBytes);
  }
  for (const vector of fixture.aggregateBoundaryVectors.streamFrameBytes) {
    consume(vector);
    const wire = exactBinarySize(
      vector.serializedBytes,
      (length) => toBinary(events.StreamFrameSchema, frameWithData(length)),
      32768,
    );
    assert.equal(fromBinary(events.StreamFrameSchema, wire).frame.case, "output");
    assert.equal(wire.byteLength <= vector.limit, vector.valid, vector.id);
  }

  const expectedIds = new Set([
    ...fixture.rpcVectors.map((vector) => vector.id),
    ...fixture.messageFieldVectors.map((vector) => vector.id),
    ...fixture.eventPayloadVectors.map((vector) => vector.id),
    ...Object.values(fixture.aggregateBoundaryVectors)
      .flat()
      .map((vector) => vector.id),
  ]);
  assert.deepEqual(
    [...seen].sort(),
    [...expectedIds].sort(),
    "all public fixture vectors consumed exactly once; none unknown/unconsumed",
  );
  assert.equal(fixture.shapeLimitations.length, 3);
  assert.ok(
    fixture.shapeLimitations.some((value) => value.includes("not by this message shape alone")),
  );
  assert.ok(
    fixture.shapeLimitations.some((value) => value.includes("not runtime streaming enforcement")),
  );
  assert.ok(
    fixture.shapeLimitations.some((value) =>
      value.includes("not represented by this per-field constraint grammar"),
    ),
  );
});
