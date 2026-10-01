// SPDX-License-Identifier: Apache-2.0
// CON.07 independent identity/session/device and authentication-exception vectors against built generated TypeScript.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fromBinary, fromJson, toBinary } from "@bufbuild/protobuf";
import * as proto from "@arcforges/proto";
import * as api from "@arcforges/api-client";
import * as shapes from "../../src/public/ts/proto/dist/shapes/gen/proto.js";

const read = async (path) => JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
const fixture = await read("../../fixtures/public/con-07-identity.json");
const exported = await read("../../eng/operations/con-07.json");
const shape = (fields) => fields.map((field) => `${field.number}:${field.name}`).join(",");
const upperSnake = (name) => name.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toUpperCase();
const lowerCamel = (name) => name.toLowerCase().replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
const inPackage = (name) => `arcforges.publicapi.v1.${name}`;

test("CON.07 generates exactly the three Registry04 identity services and 49 operations", () => {
  assert.equal(fixture.operations.length, 49);
  assert.deepEqual(Object.keys(fixture.services), [
    inPackage("IdentityService"),
    inPackage("WorkspaceService"),
    inPackage("DeviceService"),
  ]);
  for (const [typeName, methods] of Object.entries(fixture.services)) {
    const service = proto.contractServices.find((candidate) => candidate.typeName === typeName);
    assert.ok(service, `missing ${typeName}`);
    assert.deepEqual(
      service.methods.map((method) => method.name),
      methods,
    );
  }
  for (const row of fixture.operations) {
    const typeName = inPackage(row.service);
    const service = proto.contractServices.find((candidate) => candidate.typeName === typeName);
    const method = service.methods.find((candidate) => candidate.name === row.method);
    assert.ok(method, `${row.id} method`);
    assert.equal(method.methodKind, "unary", row.id);
    assert.equal(method.input.typeName, `${typeName}${row.method}Request`, row.id);
    assert.equal(method.output.typeName, `${typeName}${row.method}Response`, row.id);
    assert.equal(shape(method.input.fields), row.requestTags, `${row.id} request tags`);
    const value = method.output.fields.find((field) => field.number === 2);
    assert.equal(value.message.typeName, `${typeName}${row.method}Value`, row.id);
    assert.equal(shape(value.message.fields), row.valueTags, `${row.id} value tags`);
    assert.equal(
      method.output.fields.find((field) => field.number === 1).message.typeName,
      "arcforges.foundation.v1.ResponseMeta",
    );
    assert.equal(
      method.output.fields.find((field) => field.number === 3).message.typeName,
      "arcforges.foundation.v1.ArcError",
    );
    assert.equal(
      method.output.fields.some((field) => field.number === 4),
      row.encodedBody,
      `${row.id} encoded body`,
    );
    assert.deepEqual(
      method.input.fields.filter((field) => field.number >= 2 && field.number <= 9),
      [],
      `${row.id} reserved request tags`,
    );
    assert.deepEqual(
      method.output.fields.filter((field) => field.number >= 5 && field.number <= 9),
      [],
      `${row.id} reserved response tags`,
    );
  }
});

test("CON.07 operation export carries the exact eight authorization fields for every operation", () => {
  const rows = new Map(exported.operations.map((row) => [row.operationId, row]));
  assert.equal(rows.size, fixture.operations.length);
  for (const expected of fixture.operations) {
    const row = rows.get(expected.id);
    assert.ok(row, expected.id);
    assert.equal(row.binding, `${inPackage(expected.service)}/${expected.method}`);
    assert.equal(row.kind, "proto");
    assert.equal(row.surface, "public");
    assert.equal(row.source, "public/proto/arcforges/publicapi/v1/identity.proto");
    assert.equal(row.scope, expected.scope);
    assert.equal(row.profile, expected.profile);
    assert.equal(row.idempotency, expected.idempotency);
    assert.deepEqual(row.authorization, {
      capability: null,
      risk: expected.risk,
      approval: "none",
      stepUp: expected.stepUp,
      localPresence: false,
      egress: "none",
      patEligible: expected.patEligible,
      actorKinds: expected.actorKinds,
    });
  }
  const patEligible = fixture.operations.filter((row) => row.patEligible).map((row) => row.id);
  assert.deepEqual(patEligible, ["workspace.list", "workspace.get"]);
  assert.deepEqual(
    fixture.operations.filter((row) => row.risk === "R4").map((row) => row.id),
    ["identity.requestAccountDeletion", "workspace.requestDataDeletion"],
  );
});

test("CON.07 records, enums and oneofs keep their numbered tags and presence", () => {
  for (const [name, tags] of Object.entries(fixture.records)) {
    const schema = proto[`${name}Schema`];
    assert.ok(schema, name);
    assert.equal(shape(schema.fields), tags, `${name} tags`);
  }
  for (const [name, members] of Object.entries(fixture.enums)) {
    const values = proto[name];
    assert.ok(values, name);
    const prefix = upperSnake(name);
    assert.equal(values[0], "UNSPECIFIED", `${name} zero`);
    members.forEach((member, index) => {
      assert.equal(values[index + 1], upperSnake(member), `${name} value ${index + 1}`);
      assert.equal(lowerCamel(values[index + 1]), member, `${name} projection ${prefix}`);
    });
    assert.equal(Object.keys(values).filter((key) => /^\d+$/.test(key)).length, members.length + 1);
  }
  for (const [name, expected] of Object.entries(fixture.oneofs)) {
    const schema = proto[`${name}Schema`];
    assert.equal(schema.oneofs.length, 1, name);
    assert.equal(schema.oneofs[0].name, expected.group, name);
    assert.deepEqual(
      schema.oneofs[0].fields.map((field) => field.jsonName),
      expected.members,
      `${name} members`,
    );
  }
  const device = proto.DeviceViewSchema;
  assert.deepEqual(
    device.fields.map((field) => field.number),
    [1, 2, 3, 4, 5, 6, 8, 10],
    "DeviceView reserves tags 7, 9 and 11",
  );
  assert.ok(
    !device.fields.some((field) =>
      ["presence", "last_seen_at", "presence_expires_at"].includes(field.name),
    ),
  );
});

test("CON.07 shape vectors are independently checked against generated validators", () => {
  assert.ok(fixture.cases.length >= 90);
  for (const entry of fixture.cases) {
    const schema = proto[`${entry.target}Schema`];
    const validate = shapes[`is${entry.target}`];
    assert.ok(schema && validate, entry.target);
    const value = fromJson(schema, entry.value);
    assert.equal(validate(value), entry.valid, entry.id);
    if (entry.valid) {
      const roundTrip = fromBinary(schema, toBinary(schema, value));
      assert.equal(validate(roundTrip), true, `${entry.id} binary round-trip`);
    }
  }
});

const parsers = {
  json: (root) => [api[`tryParse${root}Json`], api[`serialize${root}Json`]],
  "form-urlencoded": (root) => [api[`tryParse${root}Form`], api[`serialize${root}Form`]],
};
const decoder = new TextDecoder();

test("CON.07 HTTP exception vectors accept and refuse exactly the declared encodings", () => {
  assert.ok(fixture.httpVectors.length >= 100);
  for (const entry of fixture.httpVectors) {
    const [tryParse, serialize] = parsers[entry.wire](entry.root);
    assert.ok(tryParse && serialize, `${entry.root} ${entry.wire} codec`);
    const result = tryParse(entry.text);
    assert.equal(result.ok, entry.valid, entry.id);
    if (entry.valid) {
      const bytes = serialize(result.value);
      if (entry.canonical !== undefined)
        assert.equal(decoder.decode(bytes), entry.canonical, `${entry.id} canonical`);
      const again = tryParse(bytes);
      assert.equal(again.ok, true, `${entry.id} round-trip`);
      assert.deepEqual(again.value, result.value, `${entry.id} lossless`);
    } else {
      assert.equal(result.failure, entry.failure, `${entry.id} failure kind`);
    }
  }
});

test("CON.07 form-urlencoded roots keep the specified 16 KiB bound and refuse non-bytes input", () => {
  assert.equal(api.nativeTokenRequestFormMaxBytes, 16384);
  assert.equal(api.nativeAuthorizeRequestFormMaxBytes, 16384);
  const form = fixture.httpVectors.find((entry) => entry.id === "native-token-desktop").text;
  assert.equal(api.tryParseNativeTokenRequestForm(new TextEncoder().encode(form)).ok, true);
  assert.equal(
    api.tryParseNativeTokenRequestForm(new TextEncoder().encode(`${form}&x=${"a".repeat(16384)}`))
      .failure,
    "tooLarge",
  );
  assert.equal(
    api.tryParseNativeTokenRequestForm(Uint8Array.of(0xff, 0x3d, 0x61)).failure,
    "malformed",
  );
  assert.equal(
    api.tryParseNativeTokenRequestForm(new TextEncoder().encode(form.replaceAll("&", "\n"))).failure,
    "malformed",
  );
  assert.throws(() => api.parseNativeTokenRequestForm("grant_type=authorization_code"), {
    failure: "invalid",
  });
  assert.throws(() => api.serializeNativeTokenRequestForm({ grant_type: "password" }), {
    failure: "invalid",
  });
  const parsed = api.parseNativeTokenRequestForm(form);
  assert.equal(parsed.client_id, "arcscope.desktop");
  assert.equal(parsed.redirect_uri, "com.arcforges.arcscope:/auth/callback");
  assert.equal(Object.getPrototypeOf(parsed), Object.prototype);
  assert.equal(
    api.tryParseNativeTokenRequestForm("__proto__=x&grant_type=authorization_code").failure,
    "invalid",
  );
});

test("CON.07 JSON exception roots keep the strict serializer posture", () => {
  const challenge = fixture.httpVectors.find(
    (entry) => entry.id === "browser-auth-challenge-valid",
  );
  const parsed = api.parseBrowserAuthChallengeJson(challenge.text);
  assert.deepEqual(Object.keys(parsed), [
    "flowId",
    "method",
    "challenge",
    "rpId",
    "expiresAt",
    "options",
    "purpose",
  ]);
  assert.equal(api.browserAuthChallengeJsonMaxBytes, 65536);
  assert.equal(
    api.tryParseBrowserAuthChallengeJson(new TextEncoder().encode(challenge.text)).ok,
    true,
  );
  assert.equal(api.tryParseBrowserAuthChallengeJson(new Uint8Array(65537)).failure, "tooLarge");
  assert.equal(
    api.tryParseBrowserAuthChallengeJson(`{"__proto__":{},${challenge.text.slice(1)}`).ok,
    false,
  );
  assert.equal(
    api.tryParseBrowserSessionViewJson(JSON.stringify({ ...JSON.parse(challenge.text) })).ok,
    false,
  );
});

test("CON.07 emits exactly the declared closed route tables", () => {
  assert.deepEqual(api.browserSessionRoutes.map(toRoute), fixture.routes.BrowserSession);
  assert.deepEqual(api.nativeAuthRoutes.map(toRoute), fixture.routes.NativeAuth);
  const all = [...api.browserSessionRoutes, ...api.nativeAuthRoutes];
  assert.equal(new Set(all.map((route) => `${route.method} ${route.path}`)).size, all.length);
  for (const route of all) {
    assert.equal(route.cache, "no-store", route.id);
    assert.ok(route.path.startsWith("/session/v1/"), route.id);
    assert.ok(Object.isFrozen(route), route.id);
  }
  const post = all.filter((route) => route.method === "POST" && route.id.startsWith("browser."));
  assert.ok(
    post.length === 8 &&
      post.every((route) => route.csrf === "required" && route.origin === "exact-configured"),
  );
  assert.equal(all.find((route) => route.id === "browser.logout").setCookie, "clear");
  assert.deepEqual(
    all.filter((route) => route.setCookie === "session").map((route) => route.id),
    ["browser.completeAuthentication", "browser.completeEnrollment"],
  );
  assert.ok(
    !all.some(
      (route) =>
        route.responseRoots.includes("NativeTokenResponse") && route.id.startsWith("browser."),
    ),
  );
});

function toRoute(route) {
  return {
    id: route.id,
    method: route.method,
    path: route.path,
    credential: route.credential,
    origin: route.origin,
    csrf: route.csrf,
    setCookie: route.setCookie,
    cache: route.cache,
    requestWire: route.requestWire,
    requestRoots: [...route.requestRoots],
    responseWire: route.responseWire,
    responseRoots: [...route.responseRoots],
  };
}

test("CON.07 journeys reference real operations and routes and spend one step-up per sensitive action", () => {
  const operations = new Map(fixture.operations.map((row) => [row.id, row]));
  const routes = new Set(
    [...api.browserSessionRoutes, ...api.nativeAuthRoutes].map((route) => route.id),
  );
  assert.deepEqual(
    fixture.journeys.map((journey) => journey.id),
    [
      "account-creation",
      "email-login",
      "passkey-login",
      "passkey-management",
      "self-host-password-enrollment",
      "oidc-login-enrollment-link",
      "recovery",
      "step-up",
      "refresh",
      "logout",
      "native-browser-authorization",
      "api-token",
      "account-deletion",
      "browser-session",
    ],
  );
  for (const journey of fixture.journeys) {
    assert.equal(
      journey.evidenceClass,
      "declarative-owner-runtime-vector-not-executed-by-con07",
      journey.id,
    );
    assert.ok(Object.keys(journey.expect).length > 0, journey.id);
    let credits = 0;
    for (const step of journey.steps) {
      if (step.kind === "route") {
        assert.ok(routes.has(step.id), `${journey.id}: ${step.id}`);
        continue;
      }
      const operation = operations.get(step.id);
      assert.ok(operation, `${journey.id}: ${step.id}`);
      if (step.id === "identity.completeStepUp") credits += 1;
      if (operation.stepUp) {
        assert.ok(credits > 0, `${journey.id}: ${step.id} requires fresh step-up evidence`);
        credits -= 1;
      }
    }
  }
});
