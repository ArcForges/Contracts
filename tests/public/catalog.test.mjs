// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { create, toBinary, fromBinary } from "@bufbuild/protobuf";
import * as c from "../../src/public/ts/proto/dist/gen/arcforges/catalog/v1/catalog_pb.js";
import * as policy from "../../src/public/ts/proto/dist/catalog-profile.js";
import * as shape from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const fixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/public/con-13-package-catalog.json", import.meta.url),
    "utf8",
  ),
);
const id = () => ({
  value: new Uint8Array([17, 34, 51, 68, 85, 102, 71, 136, 153, 170, 187, 204, 221, 238, 255, 0]),
});
const meta = () => ({ correlationId: id(), commandId: id(), expectedRev: { value: 0n } });
const submit = () =>
  create(c.CatalogServiceSubmitVersionRequestSchema, {
    meta: meta(),
    submissionId: id(),
    publisherId: id(),
    packageId: "com.example.fixture",
    version: "1.2.3",
    manifestHash: "a".repeat(64),
    archive: {
      resource: {
        realmId: id(),
        ownerAppId: "catalog",
        resourceKind: "package",
        resourceId: id(),
        availability: 4,
      },
      revision: { case: "cloud", value: { value: 1n } },
      contentHash: "b".repeat(64),
      blob: { blobId: id(), contentHash: "b".repeat(64), sizeBytes: 104857600n },
    },
  });

test("catalog exports exactly seven unary public operations and closed PAT subset", async () => {
  const expected = [
    "Search",
    "GetPackage",
    "ListVersions",
    "RegisterPublisher",
    "VerifyPublisher",
    "SubmitVersion",
    "GetSubmission",
  ];
  assert.deepEqual(
    c.CatalogService.methods.map((method) => method.name),
    expected,
  );
  for (const method of c.CatalogService.methods) {
    assert.equal(method.methodKind, "unary");
    assert.equal(method.input.typeName, `arcforges.catalog.v1.CatalogService${method.name}Request`);
    assert.equal(
      method.output.typeName,
      `arcforges.catalog.v1.CatalogService${method.name}Response`,
    );
    assert.ok(method.input.fields.every((field) => field.number === 1 || field.number >= 10));
    assert.equal(
      method.output.fields.some((field) => field.number === 4),
      ["Search", "GetPackage", "ListVersions", "GetSubmission"].includes(method.name),
    );
  }
  const operations = JSON.parse(
    await readFile(new URL("../../eng/operations/con-13.json", import.meta.url), "utf8"),
  ).operations;
  assert.equal(operations.length, 7);
  assert.deepEqual(
    operations
      .filter((row) => row.authorization.patEligible)
      .map((row) => row.operationId)
      .sort(),
    [...fixture.patEligible].sort(),
  );
  for (const operation of fixture.patEligible)
    assert.equal(policy.catalogPatEligible(operation), true);
  for (const operation of fixture.patDenied)
    assert.equal(policy.catalogPatEligible(operation), false);
  for (const row of operations) {
    assert.equal(row.scope, "account");
    assert.equal(row.profile, "human-owner");
    assert.deepEqual(row.authorization.actorKinds, ["human"]);
    assert.equal(row.authorization.capability, null);
  }
});

test("catalog canonical challenge/domain fixtures retain server verification boundary", () => {
  assert.match(fixture.evidenceClass, /not-dns/);
  for (const row of fixture.challenge)
    assert.equal(policy.isCatalogChallenge(row.value), row.valid, row.id);
  for (const row of fixture.domains)
    assert.equal(policy.isCatalogDomain(row.value), row.valid, row.value);
  for (const row of fixture.versions)
    assert.equal(policy.isCatalogVersion(row.value), row.valid, row.value);
  const publisher = create(c.PublisherViewSchema, {
    publisherId: id(),
    domain: "publisher.example.com",
    dnsName: "_arcforges-publisher.publisher.example.com",
    state: "pending",
    challenge: "arcforges=" + "A".repeat(43),
    revision: { value: 1n },
  });
  assert.equal(policy.isCatalogPublisher(publisher), true);
  publisher.dnsName = "attacker.example.com";
  assert.equal(policy.isCatalogPublisher(publisher), false);
});

test("catalog independently supplied archive and manifest projection comparisons", () => {
  for (const row of fixture.integrity) {
    const facts = { ...fixture.integrityBase };
    if (row.field !== "none") facts[row.field] = row.value;
    facts.archiveBytes = BigInt(facts.archiveBytes);
    assert.equal(policy.matchesCatalogSubmission(submit(), facts), row.valid, row.id);
  }
  const request = submit();
  assert.equal(policy.isCatalogRequest(request), true);
  const bytes = toBinary(c.CatalogServiceSubmitVersionRequestSchema, request);
  assert.equal(
    policy.isCatalogRequest(fromBinary(c.CatalogServiceSubmitVersionRequestSchema, bytes)),
    true,
  );
  request.meta.commandId = undefined;
  assert.equal(policy.isCatalogRequest(request), false);
  const stale = submit();
  stale.meta.expectedRev.value = 1n;
  assert.equal(policy.isCatalogRequest(stale), false);
  const native = submit();
  native.archive.revision = { case: "native", value: { value: 1n } };
  assert.equal(policy.isCatalogRequest(native), false);
  const mismatch = submit();
  mismatch.archive.blob.contentHash = "c".repeat(64);
  assert.equal(policy.isCatalogRequest(mismatch), false);
});

test("catalog scalar-count, page, metadata and outcome boundaries", () => {
  const search = create(c.CatalogServiceSearchRequestSchema, {
    meta: meta(),
    query: "😀".repeat(256),
    page: {},
  });
  assert.equal(policy.isCatalogRequest(search), true);
  search.query += "x";
  assert.equal(policy.isCatalogRequest(search), false);
  search.query = "\ud800";
  assert.equal(policy.isCatalogRequest(search), false);
  search.query = "";
  search.page.limit = 100;
  assert.equal(policy.isCatalogRequest(search), true);
  search.page.limit = 101;
  assert.equal(policy.isCatalogRequest(search), false);
  search.page.limit = 0;
  assert.equal(policy.isCatalogRequest(search), false);
  assert.equal(
    shape.isCatalogServiceSearchResponse(
      create(c.CatalogServiceSearchResponseSchema, { meta: { correlationId: id() } }),
    ),
    false,
  );
});
