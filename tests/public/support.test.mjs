// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { create, fromJson, fromBinary, toBinary } from "@bufbuild/protobuf";
import {
  contractServices,
  NotificationViewSchema,
  PolicyBundleSchema,
  SupportCaseSchema,
  SupportMessageSchema,
} from "@arcforges/proto";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const fixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/public/con-22-account-support.json", import.meta.url),
    "utf8",
  ),
);
const idBytes = Uint8Array.from(Buffer.from("112233445566478899aabbccddeeff00", "hex"));
const instant = (seconds) => ({ unixSeconds: BigInt(seconds), nanos: 0 });
const id = () => ({ value: idBytes.slice() });
const validators = {
  SupportCase: [SupportCaseSchema, shapes.isSupportCase],
  SupportMessage: [SupportMessageSchema, shapes.isSupportMessage],
  NotificationView: [NotificationViewSchema, shapes.isNotificationView],
  PolicyBundle: [PolicyBundleSchema, shapes.isPolicyBundle],
};

test("CON.22 emits only the six Registry04 public services and exact method maps", () => {
  const expected = {
    "arcforges.publicapi.v1.SupportService": [
      "CreateCase",
      "ListCases",
      "AppendMessage",
      "DecideAccess",
    ],
    "arcforges.publicapi.v1.NotificationService": [
      "List",
      "Acknowledge",
      "RegisterPush",
      "UnregisterPush",
    ],
    "arcforges.publicapi.v1.PreferenceService": ["Put"],
    "arcforges.publicapi.v1.PolicyService": ["GetBundle"],
    "arcforges.publicapi.v1.DataService": ["RequestExport", "GetExportState"],
    "arcforges.publicapi.v1.ExportService": ["GetStatus", "Cancel", "GetDownload"],
  };
  const encodedBody = new Set([
    "arcforges.publicapi.v1.SupportService/ListCases",
    "arcforges.publicapi.v1.NotificationService/List",
    "arcforges.publicapi.v1.PolicyService/GetBundle",
    "arcforges.publicapi.v1.DataService/GetExportState",
    "arcforges.publicapi.v1.ExportService/GetStatus",
  ]);
  for (const [typeName, methods] of Object.entries(expected)) {
    const service = contractServices.find((candidate) => candidate.typeName === typeName);
    assert.ok(service, `missing ${typeName}`);
    assert.deepEqual(
      service.methods.map((method) => method.name),
      methods,
    );
    for (const method of service.methods) {
      assert.equal(method.methodKind, "unary");
      assert.equal(method.input.typeName, `${typeName}${method.name}Request`);
      assert.equal(method.output.typeName, `${typeName}${method.name}Response`);
      assert.equal(
        method.output.fields.some((field) => field.number === 4),
        encodedBody.has(`${typeName}/${method.name}`),
      );
    }
  }
});

test("CON.22 fixture positives and negatives are independently checked against generated shapes", () => {
  for (const entry of fixture.cases) {
    const [schema, validate] = validators[entry.target];
    const value = fromJson(schema, entry.value);
    assert.equal(validate(value), entry.valid, entry.id);
    if (entry.valid) {
      const roundTrip = fromBinary(schema, toBinary(schema, value));
      assert.equal(validate(roundTrip), true, `${entry.id} binary round-trip`);
    }
  }
});

test("CON.22 names, text, keys, repeated messages and policy body retain declared bounds", () => {
  const caseValue = (subject = "Case", state = "open", category = "support", messageCount = 0) =>
    create(SupportCaseSchema, {
      caseId: id(),
      subject,
      state,
      messages: Array.from({ length: messageCount }, (_, index) => ({
        messageId: id(),
        actorKind: "future.owner",
        text: `message ${index}`,
        createdAt: instant(1),
      })),
      revision: { value: 1n },
      category,
      messagePage: { hasMore: false },
    });
  assert.equal(shapes.isSupportCase(caseValue("😀".repeat(256))), true);
  assert.equal(shapes.isSupportCase(caseValue("😀".repeat(257))), false);
  const missingSubject = caseValue();
  delete missingSubject.subject;
  assert.equal(shapes.isSupportCase(missingSubject), false);
  const missingRevision = caseValue();
  delete missingRevision.revision;
  assert.equal(shapes.isSupportCase(missingRevision), false);
  assert.equal(shapes.isSupportCase(caseValue("Case", "futureState")), false);
  assert.equal(shapes.isSupportCase(caseValue("Case", "open", "futureCategory")), false);
  assert.equal(shapes.isSupportCase(caseValue("Case", "open", "support", 100)), true);
  assert.equal(shapes.isSupportCase(caseValue("Case", "open", "support", 101)), false);

  const message = (text, actorKind = "future.owner") =>
    create(SupportMessageSchema, { messageId: id(), actorKind, text, createdAt: instant(1) });
  assert.equal(shapes.isSupportMessage(message("é".repeat(131072))), true);
  assert.equal(shapes.isSupportMessage(message("é".repeat(131073))), false);
  const missingText = message("present");
  delete missingText.text;
  assert.equal(shapes.isSupportMessage(missingText), false);
  const missingMessageTime = message("present");
  delete missingMessageTime.createdAt;
  assert.equal(shapes.isSupportMessage(missingMessageTime), false);
  assert.equal(
    shapes.isSupportMessage(message("explicit support text", "future.actor-kind")),
    true,
  );
  assert.equal(shapes.isSupportMessage(message("text", "not valid")), false);

  const notice = (kind) =>
    create(NotificationViewSchema, {
      notificationId: id(),
      kind,
      durability: "durable",
      messageKey: "future.message-key",
      state: "unread",
      createdAt: instant(1),
    });
  assert.equal(shapes.isNotificationView(notice("future.notification-kind")), true);
  assert.equal(shapes.isNotificationView(notice("bad key")), false);
  const missingNotificationTime = notice("notice.kind");
  delete missingNotificationTime.createdAt;
  assert.equal(shapes.isNotificationView(missingNotificationTime), false);

  const bundle = (length) =>
    create(PolicyBundleSchema, {
      version: "policy.1",
      issuedAt: instant(1),
      expiresAt: instant(2),
      body: new Uint8Array(length),
      signature: Uint8Array.of(1),
      keyId: "key.1",
    });
  assert.equal(shapes.isPolicyBundle(bundle(1048576)), true);
  assert.equal(shapes.isPolicyBundle(bundle(1048577)), false);
  const missingIssuedAt = bundle(1);
  delete missingIssuedAt.issuedAt;
  assert.equal(shapes.isPolicyBundle(missingIssuedAt), false);
  const noBody = create(PolicyBundleSchema, {
    version: "policy.1",
    issuedAt: instant(1),
    expiresAt: instant(2),
    signature: Uint8Array.of(1),
    keyId: "key.1",
  });
  assert.equal(shapes.isPolicyBundle(noBody), false);
  const noSignature = create(PolicyBundleSchema, {
    version: "policy.1",
    issuedAt: instant(1),
    expiresAt: instant(2),
    body: Uint8Array.of(1),
    keyId: "key.1",
  });
  assert.equal(shapes.isPolicyBundle(noSignature), false);
});
