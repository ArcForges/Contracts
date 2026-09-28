// SPDX-License-Identifier: Apache-2.0
import type * as catalog from "./gen/arcforges/catalog/v1/catalog_pb.js";
import type {
  PageRequest,
  RequestMeta,
  ResourceVersionRef,
} from "./gen/arcforges/foundation/v1/foundation_pb.js";
import * as shape from "./shapes/gen/proto.js";

/** Static facts only: no DNS, credential, signature, archive-byte or publication verification. */
export const maximumCatalogArchiveBytes = 104857600n;

/** Exact catalog subset; a true result does not authorize a token or publisher. */
export function catalogPatEligible(operation: string): boolean {
  return [
    "catalog.search",
    "catalog.getPackage",
    "catalog.listVersions",
    "catalog.submitVersion",
    "catalog.getSubmission",
  ].includes(operation);
}

/** Canonical unpadded 32-byte format only; fixture text is never proof of entropy or freshness. */
export function isCatalogChallenge(value: string): boolean {
  return full(value, /arcforges=[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]/u);
}

/** Already-normalized ASCII DNS syntax; public suffix and owner checks belong to the resolver-backed service. */
export function isCatalogDomain(value: string): boolean {
  return (
    value.length + "_arcforges-publisher.".length <= 253 &&
    full(
      value,
      /[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+/u,
    ) &&
    !full(value, /[0-9.]+/u) &&
    ![".localhost", ".local", ".internal"].some((suffix) => value.endsWith(suffix))
  );
}

export function isCatalogPublisher(value: catalog.PublisherView): boolean {
  return (
    shape.isPublisherView(value) &&
    isCatalogDomain(value.domain!) &&
    value.dnsName === "_arcforges-publisher." + value.domain &&
    (value.challenge === undefined || isCatalogChallenge(value.challenge)) &&
    value.revision!.value! > 0n
  );
}

export function isCatalogPage(value: PageRequest): boolean {
  return (
    shape.isPageRequest(value) &&
    (value.limit === undefined || (value.limit >= 1 && value.limit <= 100))
  );
}

export type CatalogRequest =
  | catalog.CatalogServiceSearchRequest
  | catalog.CatalogServiceGetPackageRequest
  | catalog.CatalogServiceListVersionsRequest
  | catalog.CatalogServiceRegisterPublisherRequest
  | catalog.CatalogServiceVerifyPublisherRequest
  | catalog.CatalogServiceSubmitVersionRequest
  | catalog.CatalogServiceGetSubmissionRequest;

export function isCatalogRequest(value: CatalogRequest): boolean {
  switch (value.$typeName) {
    case "arcforges.catalog.v1.CatalogServiceSearchRequest":
      return (
        shape.isCatalogServiceSearchRequest(value) &&
        read(value.meta!) &&
        isCatalogPage(value.page!)
      );
    case "arcforges.catalog.v1.CatalogServiceGetPackageRequest":
      return shape.isCatalogServiceGetPackageRequest(value) && read(value.meta!);
    case "arcforges.catalog.v1.CatalogServiceListVersionsRequest":
      return (
        shape.isCatalogServiceListVersionsRequest(value) &&
        read(value.meta!) &&
        isCatalogPage(value.page!)
      );
    case "arcforges.catalog.v1.CatalogServiceRegisterPublisherRequest":
      return (
        shape.isCatalogServiceRegisterPublisherRequest(value) &&
        create(value.meta!) &&
        isCatalogDomain(value.domain!)
      );
    case "arcforges.catalog.v1.CatalogServiceVerifyPublisherRequest":
      return (
        shape.isCatalogServiceVerifyPublisherRequest(value) &&
        write(value.meta!) &&
        value.meta!.expectedRev!.value! > 0n
      );
    case "arcforges.catalog.v1.CatalogServiceSubmitVersionRequest":
      return (
        shape.isCatalogServiceSubmitVersionRequest(value) &&
        create(value.meta!) &&
        isArchive(value.archive!)
      );
    case "arcforges.catalog.v1.CatalogServiceGetSubmissionRequest":
      return shape.isCatalogServiceGetSubmissionRequest(value) && read(value.meta!);
    default:
      return false;
  }
}

/** Finite extracted projections, not an alternate wire format or a verification receipt. */
export interface CatalogSubmissionFacts {
  packageId: string;
  version: string;
  manifestHash: string;
  archiveDigest: string;
  archiveBytes: bigint;
  manifestLicences: Readonly<Record<string, string>>;
  archiveLicences: Readonly<Record<string, string>>;
}

export function matchesCatalogSubmission(
  request: catalog.CatalogServiceSubmitVersionRequest,
  facts: CatalogSubmissionFacts,
): boolean {
  if (
    !isCatalogRequest(request) ||
    request.packageId !== facts.packageId ||
    request.version !== facts.version ||
    request.manifestHash !== facts.manifestHash ||
    request.archive!.contentHash !== facts.archiveDigest ||
    facts.archiveBytes < 0n ||
    facts.archiveBytes > maximumCatalogArchiveBytes ||
    (request.archive!.blob !== undefined && request.archive!.blob.sizeBytes !== facts.archiveBytes)
  )
    return false;
  return Object.entries(facts.manifestLicences).every(
    ([path, licence]) =>
      path.trim() !== "" &&
      licence.trim() !== "" &&
      Object.hasOwn(facts.archiveLicences, path) &&
      facts.archiveLicences[path] === licence,
  );
}

/** Exact bounded SemVer2 field profile; identity comparisons retain build metadata. */
export function isCatalogVersion(value: string): boolean {
  return (
    value.length <= 128 &&
    full(
      value,
      /(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?/u,
    )
  );
}
function isArchive(value: ResourceVersionRef): boolean {
  return (
    value.revision.case === "cloud" &&
    value.revision.value.value! > 0n &&
    value.contentHash !== undefined &&
    full(value.contentHash, /[0-9a-f]{64}/u) &&
    (value.blob === undefined ||
      (value.blob.sizeBytes! <= maximumCatalogArchiveBytes &&
        value.blob.contentHash === value.contentHash))
  );
}
function read(meta: RequestMeta): boolean {
  return meta.expectedNative === undefined;
}
function write(meta: RequestMeta): boolean {
  return read(meta) && meta.commandId !== undefined && meta.expectedRev !== undefined;
}
function create(meta: RequestMeta): boolean {
  return write(meta) && meta.expectedRev!.value === 0n;
}
function full(value: string, pattern: RegExp): boolean {
  return pattern.exec(value)?.[0] === value;
}
