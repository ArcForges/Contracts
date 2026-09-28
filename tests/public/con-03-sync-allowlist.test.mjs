// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import {
  IdSchema,
  NativeContentRevSchema,
  RationalSchema,
  ResourceRefSchema,
  ResourceVersionRefSchema,
  RevisionSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import {
  AggregateBodySchema,
  ChannelDefinitionSchema,
  FrameConfigurationSchema,
  ScopeConfigurationSchema,
  ScopeMetadataSchema,
  ScopeProjectMetadataSchema,
  TaskSnapshotSchema,
} from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const fixture = JSON.parse(
  readFileSync(
    new URL("../../fixtures/public/con-03-sync-allowlist.json", import.meta.url),
    "utf8",
  ),
);
const id = (hex) => create(IdSchema, { value: Uint8Array.from(Buffer.from(hex, "hex")) });

function bodyFrom(value) {
  switch (value.kind) {
    case "none":
      return null;
    case "opaque":
      return fromBinary(AggregateBodySchema, Buffer.from(value.wireHex, "hex"));
    case "scopeProjectMetadata":
      return create(AggregateBodySchema, {
        body: {
          case: "scopeProjectMetadata",
          value: create(ScopeProjectMetadataSchema, {
            projectId: id(value.projectIdHex),
            name: value.name,
          }),
        },
      });
    case "scopeMetadata": {
      const configuration = create(ScopeConfigurationSchema, {
        configurationId: id("22222222222242228222222222222222"),
        channels: [
          create(ChannelDefinitionSchema, {
            channelId: id("11111111111141118111111111111111"),
            name: "Voltage",
            unit: "V",
            sampleType: "f64",
            rate: create(RationalSchema, { numerator: 1n, denominator: 1n }),
          }),
        ],
        parserProfile: "scope.parser.v1",
        revision: create(NativeContentRevSchema, { value: 1n }),
        framing: create(FrameConfigurationSchema, {
          kind: "canonicalReplay",
          start: new Uint8Array(),
          end: new Uint8Array(),
          header: false,
          byteOrder: "little",
        }),
      });
      return create(AggregateBodySchema, {
        body: {
          case: "scopeMetadata",
          value: create(ScopeMetadataSchema, {
            sessionId: id(value.sessionIdHex),
            projectId: id(value.projectIdHex),
            name: value.name,
            configuration,
          }),
        },
      });
    }
    case "taskSnapshot":
      return create(AggregateBodySchema, {
        body: {
          case: "task",
          value: create(TaskSnapshotSchema, {
            taskId: id(value.taskIdHex),
            state: 1,
            revision: create(RevisionSchema, { value: 1n }),
            hasUnknownEffect: false,
            completedSteps: 0,
            totalSteps: 0,
            reasonFacet: 1,
          }),
        },
      });
    case "externalBody": {
      const ref = value.resourceVersionRef;
      return create(AggregateBodySchema, {
        body: {
          case: "externalBody",
          value: create(ResourceVersionRefSchema, {
            resource: create(ResourceRefSchema, {
              realmId: id(ref.realmIdHex),
              resourceId: id(ref.resourceIdHex),
              ownerAppId: ref.ownerAppId,
              resourceKind: ref.resourceKind,
              availability: 1,
            }),
            revision: { case: "cloud", value: create(RevisionSchema, { value: 1n }) },
          }),
        },
      });
    }
    default:
      throw new Error(`Unknown CON.03 body fixture kind ${value.kind}`);
  }
}

test("closed Sync client-write allowlist rejects named negative vectors", () => {
  for (const item of fixture.cases) {
    const sourceBody = bodyFrom(item.body);
    if (item.resolvedBody !== undefined)
      assert.equal(shapes.isAggregateBody(sourceBody), true, item.id + ": external source shape");
    const candidate = item.resolvedBody === undefined ? sourceBody : bodyFrom(item.resolvedBody);
    assert.equal(
      candidate !== null && shapes.isAggregateBody(candidate),
      item.bodyShapeValid,
      item.id + ": shape validity",
    );
    assert.equal(
      shapes.isSyncClientWriteAllowed(candidate, {
        expectedOwner: item.expectedOwner,
        actualOwner: item.actualOwner,
        expectedRevision: item.expectedRevision === null ? null : BigInt(item.expectedRevision),
        actualRevision: item.actualRevision === null ? null : BigInt(item.actualRevision),
      }),
      item.allowed,
      item.id,
    );
  }
});

test("compatible unknown fields on a known response body survive binary round-trip", () => {
  const bytes = Buffer.from(fixture.compatibleUnknownResponse.wireHex, "hex");
  const response = fromBinary(AggregateBodySchema, bytes);
  assert.equal(shapes.isAggregateBody(response), true);
  assert.deepEqual(Buffer.from(toBinary(AggregateBodySchema, response)), bytes);
});
