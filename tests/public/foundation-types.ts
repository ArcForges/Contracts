// SPDX-License-Identifier: Apache-2.0
import {
  parseId,
  idToWire,
  cloudRevision,
  nativeRevision,
  deliverySequence,
  type ScopeProjectId,
  type ResourceId,
  type CloudRevision,
  type NativeRevision,
  type DeliverySequence,
  type RunId,
} from "../../src/public/ts/proto/dist/values.js";

const document: ScopeProjectId = parseId("ScopeProjectId", "00112233-4455-6677-8899-aabbccddeeff");
const resource: ResourceId = parseId("ResourceId", "00112233-4455-6677-8899-aabbccddeeff");
idToWire("ScopeProjectId", document);
// @ts-expect-error A resource identity cannot enter a document domain.
const wrongDocument: ScopeProjectId = resource;
// @ts-expect-error The explicit wire conversion must preserve its domain.
idToWire("ScopeProjectId", resource);
// @ts-expect-error A scope project identity cannot become an AI execution-run identity.
const wrongRun: RunId = parseId("ScopeProjectId", "00112233-4455-6677-8899-aabbccddeeff");
const cloud: CloudRevision = cloudRevision(1n);
const native: NativeRevision = nativeRevision(1n);
const sequence: DeliverySequence = deliverySequence(1n);
// @ts-expect-error Native revisions are independent of Cloud acknowledgements.
const wrongCloud: CloudRevision = native;
// @ts-expect-error Delivery ordering is independent of owner revision.
const wrongNative: NativeRevision = sequence;
// @ts-expect-error Cloud revisions cannot become delivery ordering.
const wrongSequence: DeliverySequence = cloud;
// @ts-expect-error A JS number cannot represent an exact Cloud revision.
cloudRevision(9007199254740993);
void [cloud, wrongDocument, wrongRun, wrongCloud, wrongNative, wrongSequence];
