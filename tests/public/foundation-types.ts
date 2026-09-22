// SPDX-License-Identifier: Apache-2.0
import {
  parseId,
  idToWire,
  cloudRevision,
  nativeRevision,
  deliverySequence,
  localNotesToken,
  type DocumentId,
  type ResourceId,
  type CloudRevision,
  type NativeRevision,
  type DeliverySequence,
  type RunId,
} from "../../src/public/ts/proto/dist/values.js";

const document: DocumentId = parseId("DocumentId", "00112233-4455-6677-8899-aabbccddeeff");
const resource: ResourceId = parseId("ResourceId", "00112233-4455-6677-8899-aabbccddeeff");
idToWire("DocumentId", document);
// @ts-expect-error A resource identity cannot enter a document domain.
const wrongDocument: DocumentId = resource;
// @ts-expect-error The explicit wire conversion must preserve its domain.
idToWire("DocumentId", resource);
// @ts-expect-error A Notes text-run identity cannot become an AI execution-run identity.
const wrongRun: RunId = parseId("TextRunId", "00112233-4455-6677-8899-aabbccddeeff");
const cloud: CloudRevision = cloudRevision(1n);
const native: NativeRevision = nativeRevision(1n);
const sequence: DeliverySequence = deliverySequence(1n);
// @ts-expect-error Native revisions are independent of Cloud acknowledgements.
const wrongCloud: CloudRevision = native;
// @ts-expect-error Delivery ordering is independent of owner revision.
const wrongNative: NativeRevision = sequence;
// @ts-expect-error Composite local tokens cannot become committed Cloud revisions.
const wrongSequence: DeliverySequence = localNotesToken(0n, 1n);
// @ts-expect-error A JS number cannot represent an exact Cloud revision.
cloudRevision(9007199254740993);
void [cloud, wrongDocument, wrongRun, wrongCloud, wrongNative, wrongSequence];
