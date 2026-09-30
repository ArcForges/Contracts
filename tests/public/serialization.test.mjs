// SPDX-License-Identifier: Apache-2.0
// WP03.02 posture: executes the independent fixtures/public/wp03-02.json vectors in TypeScript.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  ArcErrorSchema,
  ContractSerializationError,
  contractServices,
  decodeContract,
  encodeContract,
  IdSchema,
  StructuredValueSchema,
  wireLimits,
} from "@arcforges/proto";
import {
  createPublicGrpcWebTransport,
  parsePartReceiptJson,
  serializePackageInventoryJson,
  serializePartReceiptJson,
  tryParsePackageInventoryJson,
  tryParsePartReceiptJson,
} from "@arcforges/api-client";
import {
  serializeCommitReceiptJson,
  tryParseCommitReceiptJson,
} from "../../src/internal/ts/ai-internal/dist/gen/http.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/wp03-02.json", import.meta.url)),
);
const targets = {
  "arcforges.foundation.v1.Id": IdSchema,
  "arcforges.foundation.v1.ArcError": ArcErrorSchema,
  "arcforges.publicapi.v1.StructuredValue": StructuredValueSchema,
};
const codecs = {
  PartReceipt: { tryParse: tryParsePartReceiptJson, serialize: serializePartReceiptJson },
  CommitReceipt: { tryParse: tryParseCommitReceiptJson, serialize: serializeCommitReceiptJson },
  PackageInventory: {
    tryParse: tryParsePackageInventoryJson,
    serialize: serializePackageInventoryJson,
  },
};

function varint(value) {
  const out = [];
  do {
    const low = value % 128;
    value = Math.floor(value / 128);
    out.push(value > 0 ? low | 0x80 : low);
  } while (value > 0);
  return out;
}

function lengthDelimited(field, payload) {
  const head = [...varint(field * 8 + 2), ...varint(payload.length)];
  const out = new Uint8Array(head.length + payload.length);
  out.set(head);
  out.set(payload, head.length);
  return out;
}

function construct(spec) {
  if (spec.kind === "hex") return Uint8Array.from(Buffer.from(spec.hex, "hex"));
  if (spec.kind === "filler") {
    const tag = varint(15999 * 8 + 2).length;
    for (let width = 1; width <= 5; width++) {
      const length = spec.totalBytes - tag - width;
      if (length >= 0 && varint(length).length === width)
        return lengthDelimited(15999, new Uint8Array(length));
    }
    throw new Error("No exact filler length");
  }
  if (spec.kind === "nested") {
    let inner = new Uint8Array(0);
    for (let level = spec.levels; level >= 1; level--) {
      inner = lengthDelimited(spec.fields[(level - 1) % spec.fields.length], inner);
    }
    return inner;
  }
  throw new Error(`Unknown construction ${spec.kind}`);
}

function documentBytes(item) {
  if (item.hex !== undefined) return Uint8Array.from(Buffer.from(item.hex, "hex"));
  if (item.construct !== undefined) {
    const base = Buffer.from(item.construct.base, "utf8");
    return Uint8Array.from(
      Buffer.concat([base, Buffer.alloc(item.construct.totalBytes - base.length, 0x20)]),
    );
  }
  return Uint8Array.from(Buffer.from(item.text, "utf8"));
}

function outcome(action) {
  try {
    return { expect: "accept", value: action() };
  } catch (error) {
    assert.ok(error instanceof ContractSerializationError, String(error));
    return { expect: error.failure };
  }
}

test("fixed limits match the independent vectors", () => {
  for (const key of [
    "unaryMessage",
    "helperMessage",
    "inlinePage",
    "streamFrame",
    "largeProjection",
    "nestedMessageLevels",
  ]) {
    assert.equal(wireLimits[key], fixture.limits[key], key);
  }
});

test("bounded binary codec follows every binary vector", () => {
  for (const item of fixture.binary) {
    const schema = targets[item.construct.target];
    const bytes = construct(item.construct);
    if (item.construct.kind === "filler")
      assert.equal(bytes.length, item.construct.totalBytes, item.id);
    const result =
      item.operation === "encode"
        ? outcome(() =>
            encodeContract(schema, decodeContract(schema, bytes, "largeProjection"), item.limit),
          )
        : outcome(() => decodeContract(schema, bytes, item.limit));
    assert.equal(result.expect, item.expect, item.id);
    if (result.expect !== "accept") continue;
    const encoded =
      item.operation === "encode"
        ? result.value
        : encodeContract(schema, result.value, "largeProjection");
    assert.deepEqual(
      Buffer.from(encoded),
      Buffer.from(bytes),
      `${item.id} re-encodes every retained byte`,
    );
    if (item.reencodeHex !== undefined)
      assert.equal(Buffer.from(encoded).toString("hex"), item.reencodeHex, item.id);
  }
});

test("strict HTTP-exception JSON codecs follow every JSON vector", () => {
  for (const item of fixture.json) {
    const codec = codecs[item.schema];
    const bytes = documentBytes(item);
    const result = codec.tryParse(bytes);
    assert.equal(result.ok ? "accept" : result.failure, item.expect, item.id);
    if (!result.ok) continue;
    const written = codec.serialize(result.value);
    assert.deepEqual(
      JSON.parse(Buffer.from(written).toString("utf8")),
      item.canonical,
      `${item.id} canonical value`,
    );
    const again = codec.tryParse(written);
    assert.ok(again.ok, item.id);
    assert.deepEqual(
      Buffer.from(codec.serialize(again.value)),
      Buffer.from(written),
      `${item.id} stable output`,
    );
  }
});

test("string input applies the same byte bound and text checks", () => {
  const base = fixture.json.find((item) => item.id === "part-canonical").text;
  assert.equal(parsePartReceiptJson(base).partNumber, 1);
  assert.equal(
    tryParsePartReceiptJson(base + " ".repeat(65536 - base.length + 1)).failure,
    "tooLarge",
  );
  assert.equal(tryParsePartReceiptJson(base.replace('"e1', '"\ud800')).failure, "malformed");
  assert.throws(
    () => parsePartReceiptJson("{}"),
    (error) => error.failure === "invalid",
  );
});

test("serialization refuses values the closed schema rejects", () => {
  assert.throws(
    () =>
      serializePartReceiptJson({ partNumber: 1.5, size: "1", sha256: "a".repeat(64), etag: "x" }),
    (error) => error.failure === "invalid",
  );
});

test("generated service catalogue lists exactly the authored services", () => {
  const con08Methods = {
    "arcforges.publicapi.v1.EntitlementService": [
      "/arcforges.publicapi.v1.EntitlementService/GetSnapshot",
      "/arcforges.publicapi.v1.EntitlementService/GetServiceTerm",
      "/arcforges.publicapi.v1.EntitlementService/GetCapacity",
      "/arcforges.publicapi.v1.EntitlementService/ListGrants",
      "/arcforges.publicapi.v1.EntitlementService/GetUsage",
      "/arcforges.publicapi.v1.EntitlementService/Check",
    ],
    "arcforges.publicapi.v1.CommerceService": [
      "/arcforges.publicapi.v1.CommerceService/AuthoriseExtraUsage",
      "/arcforges.publicapi.v1.CommerceService/RevokeExtraUsage",
      "/arcforges.publicapi.v1.CommerceService/ExplainCharge",
      "/arcforges.publicapi.v1.CommerceService/GetCatalogue",
      "/arcforges.publicapi.v1.CommerceService/CreatePurchaseIntent",
      "/arcforges.publicapi.v1.CommerceService/CreateCheckoutAttempt",
      "/arcforges.publicapi.v1.CommerceService/GetPurchaseState",
      "/arcforges.publicapi.v1.CommerceService/GetSubscription",
      "/arcforges.publicapi.v1.CommerceService/CancelSubscription",
      "/arcforges.publicapi.v1.CommerceService/ReactivateSubscription",
      "/arcforges.publicapi.v1.CommerceService/GetCredits",
      "/arcforges.publicapi.v1.CommerceService/ListBillingHistory",
      "/arcforges.publicapi.v1.CommerceService/RequestRefund",
      "/arcforges.publicapi.v1.CommerceService/ExportEvidence",
    ],
    "arcforges.publicapi.v1.TaskService": [
      "/arcforges.publicapi.v1.TaskService/List",
      "/arcforges.publicapi.v1.TaskService/Get",
      "/arcforges.publicapi.v1.TaskService/Create",
      "/arcforges.publicapi.v1.TaskService/Cancel",
      "/arcforges.publicapi.v1.TaskService/Pause",
      "/arcforges.publicapi.v1.TaskService/Resume",
      "/arcforges.publicapi.v1.TaskService/RetryAttempt",
      "/arcforges.publicapi.v1.TaskService/Steer",
      "/arcforges.publicapi.v1.TaskService/GetDetails",
    ],
    "arcforges.publicapi.v1.ApprovalService": [
      "/arcforges.publicapi.v1.ApprovalService/List",
      "/arcforges.publicapi.v1.ApprovalService/Decide",
    ],
    "arcforges.publicapi.v1.BridgeService": [
      "/arcforges.publicapi.v1.BridgeService/PullRequests",
      "/arcforges.publicapi.v1.BridgeService/SubmitResult",
      "/arcforges.publicapi.v1.BridgeService/GetRequestState",
    ],
    "arcforges.publicapi.v1.ChatService": [
      "/arcforges.publicapi.v1.ChatService/ListConversations",
      "/arcforges.publicapi.v1.ChatService/GetConversation",
      "/arcforges.publicapi.v1.ChatService/AppendMessage",
      "/arcforges.publicapi.v1.ChatService/CreateBranch",
      "/arcforges.publicapi.v1.ChatService/RequestExport",
      "/arcforges.publicapi.v1.ChatService/CreateConversation",
      "/arcforges.publicapi.v1.ChatService/PutProject",
      "/arcforges.publicapi.v1.ChatService/DeleteProject",
      "/arcforges.publicapi.v1.ChatService/PutMemory",
      "/arcforges.publicapi.v1.ChatService/DeleteMemory",
      "/arcforges.publicapi.v1.ChatService/GetTurn",
      "/arcforges.publicapi.v1.ChatService/CancelTurn",
      "/arcforges.publicapi.v1.ChatService/PreviewPromotion",
      "/arcforges.publicapi.v1.ChatService/PromoteTurn",
      "/arcforges.publicapi.v1.ChatService/CloseTemporary",
      "/arcforges.publicapi.v1.ChatService/SaveTemporary",
      "/arcforges.publicapi.v1.ChatService/UpdateConversation",
      "/arcforges.publicapi.v1.ChatService/ListProjects",
      "/arcforges.publicapi.v1.ChatService/GetProject",
      "/arcforges.publicapi.v1.ChatService/ListMemories",
      "/arcforges.publicapi.v1.ChatService/GetMemory",
    ],
    "arcforges.publicapi.v1.AgentService": [
      "/arcforges.publicapi.v1.AgentService/ListModels",
      "/arcforges.publicapi.v1.AgentService/ListProfiles",
      "/arcforges.publicapi.v1.AgentService/GetUsage",
      "/arcforges.publicapi.v1.AgentService/PutProfile",
      "/arcforges.publicapi.v1.AgentService/DeleteProfile",
      "/arcforges.publicapi.v1.AgentService/PutSkill",
      "/arcforges.publicapi.v1.AgentService/DeleteSkill",
    ],
    "arcforges.publicapi.v1.SearchService": ["/arcforges.publicapi.v1.SearchService/Query"],
    "arcforges.publicapi.v1.AutomationService": [
      "/arcforges.publicapi.v1.AutomationService/List",
      "/arcforges.publicapi.v1.AutomationService/Get",
      "/arcforges.publicapi.v1.AutomationService/Create",
      "/arcforges.publicapi.v1.AutomationService/Update",
      "/arcforges.publicapi.v1.AutomationService/SetEnabled",
      "/arcforges.publicapi.v1.AutomationService/Delete",
      "/arcforges.publicapi.v1.AutomationService/RunNow",
      "/arcforges.publicapi.v1.AutomationService/SubmitEvent",
      "/arcforges.publicapi.v1.AutomationService/ResolveMissed",
    ],
    "arcforges.publicapi.v1.SourceService": [
      "/arcforges.publicapi.v1.SourceService/CreateConsent",
      "/arcforges.publicapi.v1.SourceService/RevokeConsent",
      "/arcforges.publicapi.v1.SourceService/GetPolicy",
      "/arcforges.publicapi.v1.SourceService/SetPolicy",
      "/arcforges.publicapi.v1.SourceService/ClearPolicy",
    ],
    "arcforges.publicapi.v1.SyncService": [
      "/arcforges.publicapi.v1.SyncService/ListScopes",
      "/arcforges.publicapi.v1.SyncService/SetScope",
      "/arcforges.publicapi.v1.SyncService/PullChanges",
      "/arcforges.publicapi.v1.SyncService/PushChange",
      "/arcforges.publicapi.v1.SyncService/PushBatch",
      "/arcforges.publicapi.v1.SyncService/GetAggregate",
      "/arcforges.publicapi.v1.SyncService/ListConflicts",
      "/arcforges.publicapi.v1.SyncService/ResolveConflict",
      "/arcforges.publicapi.v1.SyncService/RequestFullResync",
      "/arcforges.publicapi.v1.SyncService/GetBootstrapPage",
    ],
    "arcforges.publicapi.v1.ResourceService": [
      "/arcforges.publicapi.v1.ResourceService/BeginUpload",
      "/arcforges.publicapi.v1.ResourceService/CompleteUpload",
      "/arcforges.publicapi.v1.ResourceService/GetDownloadTicket",
      "/arcforges.publicapi.v1.ResourceService/GetMetadata",
      "/arcforges.publicapi.v1.ResourceService/Release",
      "/arcforges.publicapi.v1.ResourceService/GetUploadStatus",
      "/arcforges.publicapi.v1.ResourceService/RenewUploadTicket",
    ],
    "arcforges.publicapi.v1.TransferService": [
      "/arcforges.publicapi.v1.TransferService/RequestExport",
      "/arcforges.publicapi.v1.TransferService/PreviewImport",
      "/arcforges.publicapi.v1.TransferService/CommitImport",
      "/arcforges.publicapi.v1.TransferService/Get",
      "/arcforges.publicapi.v1.TransferService/List",
      "/arcforges.publicapi.v1.TransferService/Cancel",
    ],
    "arcforges.publicapi.v1.SupportService": [
      "/arcforges.publicapi.v1.SupportService/CreateCase",
      "/arcforges.publicapi.v1.SupportService/ListCases",
      "/arcforges.publicapi.v1.SupportService/AppendMessage",
      "/arcforges.publicapi.v1.SupportService/DecideAccess",
    ],
    "arcforges.publicapi.v1.NotificationService": [
      "/arcforges.publicapi.v1.NotificationService/List",
      "/arcforges.publicapi.v1.NotificationService/Acknowledge",
      "/arcforges.publicapi.v1.NotificationService/RegisterPush",
      "/arcforges.publicapi.v1.NotificationService/UnregisterPush",
    ],
    "arcforges.publicapi.v1.PreferenceService": ["/arcforges.publicapi.v1.PreferenceService/Put"],
    "arcforges.publicapi.v1.PolicyService": ["/arcforges.publicapi.v1.PolicyService/GetBundle"],
    "arcforges.publicapi.v1.DataService": [
      "/arcforges.publicapi.v1.DataService/RequestExport",
      "/arcforges.publicapi.v1.DataService/GetExportState",
    ],
    "arcforges.publicapi.v1.ExportService": [
      "/arcforges.publicapi.v1.ExportService/GetStatus",
      "/arcforges.publicapi.v1.ExportService/Cancel",
      "/arcforges.publicapi.v1.ExportService/GetDownload",
    ],
    "arcforges.simulation.v1.SimulationService": [
      "/arcforges.simulation.v1.SimulationService/ListDefinitions",
      "/arcforges.simulation.v1.SimulationService/GetDefinition",
      "/arcforges.simulation.v1.SimulationService/CreateDefinition",
      "/arcforges.simulation.v1.SimulationService/PublishScenarioVersion",
      "/arcforges.simulation.v1.SimulationService/StartRun",
      "/arcforges.simulation.v1.SimulationService/PauseRun",
      "/arcforges.simulation.v1.SimulationService/ResumeRun",
      "/arcforges.simulation.v1.SimulationService/CancelRun",
      "/arcforges.simulation.v1.SimulationService/GetRun",
      "/arcforges.simulation.v1.SimulationService/ListRuns",
      "/arcforges.simulation.v1.SimulationService/ListSegments",
      "/arcforges.simulation.v1.SimulationService/GetSegmentTicket",
      "/arcforges.simulation.v1.SimulationService/PollState",
    ],
    "arcforges.publicapi.v1.ScopeService": [
      "/arcforges.publicapi.v1.ScopeService/ListProjects",
      "/arcforges.publicapi.v1.ScopeService/ListSessions",
      "/arcforges.publicapi.v1.ScopeService/GetSession",
    ],
  };
  const con11ServiceMethodCounts = [
    ["arcforges.events.v1.ExecutionService", 5],
    ["arcforges.events.v1.EventService", 2],
    ["arcforges.publicapi.v1.ApplicationService", 3],
    ["arcforges.publicapi.v1.HistoryService", 4],
  ];
  assert.deepEqual(
    con11ServiceMethodCounts.map(([typeName]) => [
      typeName,
      fixture.services.methods[typeName]?.length ?? 0,
    ]),
    con11ServiceMethodCounts,
  );
  const expectedServices = [
    "arcforges.hello.v1.HelloService",
    "arcforges.events.v1.ExecutionService",
    "arcforges.events.v1.EventService",
    "arcforges.catalog.v1.CatalogService",
    ...Object.keys(con08Methods),
    "arcforges.publicapi.v1.ApplicationService",
    "arcforges.publicapi.v1.HistoryService",
  ];
  assert.deepEqual(
    contractServices.map((service) => service.typeName),
    expectedServices,
  );
  for (const service of contractServices) {
    assert.deepEqual(
      service.methods.map((method) => `/${service.typeName}/${method.name}`),
      con08Methods[service.typeName] ?? fixture.services.methods[service.typeName],
    );
  }
});

test("public transport is binary gRPC-Web and refuses codec overrides", () => {
  assert.ok(createPublicGrpcWebTransport({ baseUrl: "https://example.invalid" }));
  for (const override of [
    { useBinaryFormat: false },
    { useBinaryFormat: true },
    { jsonOptions: {} },
    { binaryOptions: {} },
  ]) {
    assert.throws(
      () => createPublicGrpcWebTransport({ baseUrl: "https://example.invalid", ...override }),
      TypeError,
    );
  }
});
