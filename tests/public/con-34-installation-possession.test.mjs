// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import test from "node:test";
import { fromBinary, fromJson, toBinary } from "@bufbuild/protobuf";
import * as proto from "@arcforges/proto";
import * as api from "@arcforges/api-client";

const fixture = JSON.parse(
  await readFile(
    new URL("../../fixtures/public/con-34-installation-possession.json", import.meta.url),
    "utf8",
  ),
);
const sdk = await import(
  process.env.CON34_HELPER_PATH ?? "../../src/public/ts/proto/dist/installation-possession.js"
);
const bytes = (hex) => Uint8Array.from(Buffer.from(hex, "hex"));
const id = (hex) => ({ $typeName: "arcforges.foundation.v1.Id", value: bytes(hex) });
const hex = (value) => Buffer.from(value).toString("hex");
const flow = (original, changed = {}) => {
  const v = { ...original, ...changed };
  return sdk.tryFlowBindingHash(
    id(v.realmId),
    id(v.flowId),
    id(v.installationId),
    v.productId,
    v.platform,
    bytes(v.publicKeySha256Hex),
    BigInt(v.keyVersion),
    v.purpose,
    BigInt(v.authEpoch),
    BigInt(v.recoveryGeneration),
    BigInt(v.recoveryRevision),
    v.clientId,
    v.redirectUri,
    bytes(v.pkceChallengeHex),
    bytes(v.stateSha256Hex),
    BigInt(v.expiresAtMicros),
  );
};
const context = (changed = {}) => {
  const v = { ...fixture.refreshContext, ...changed };
  return sdk.tryRefreshContextHash(
    id(v.realmId),
    id(v.userId),
    id(v.deviceId),
    id(v.installationId),
    id(v.sessionId),
    id(v.familyId),
    v.productId,
    bytes(v.publicKeySha256Hex),
    BigInt(v.keyVersion),
    v.purpose,
    BigInt(v.authEpoch),
    BigInt(v.recoveryGeneration),
    BigInt(v.sessionRevision),
    BigInt(v.familyExpiresAtMicros),
  );
};

test("all four closed initial operations match independent network-order binary vectors", () => {
  for (const vector of fixture.initial) {
    const data = sdk.tryInitialSigningData(
      vector.operation,
      id(fixture.ids.command),
      bytes(fixture.challengeHex),
      bytes(fixture.bindingHex),
    );
    assert.equal(hex(data), vector.dataHex);
    assert.equal(createHash("sha256").update(data).digest("hex"), vector.sha256);
  }
  assert.notEqual(fixture.initial[0].dataHex, fixture.initial[3].dataHex);
});

test("refresh hashes exact canonical synthetic token and captures mutable inputs before async digest", async () => {
  const command = id(fixture.ids.command),
    originalContext = bytes(fixture.contextHex);
  const pending = sdk.tryRefreshSigningData(
    command,
    originalContext,
    fixture.refresh.canonicalToken,
  );
  command.value.fill(0);
  originalContext.fill(0);
  const data = await pending;
  assert.equal(hex(data), fixture.refresh.dataHex);
  assert.equal(createHash("sha256").update(data).digest("hex"), fixture.refresh.sha256);
  assert.equal(data.length, fixture.refresh.dataHex.length / 2);
});

test("full native and direct flow hashes preserve UTF8 framing, Int64 precision and zero-pair distinction", async () => {
  for (const vector of fixture.flowBindings) assert.equal(hex(await flow(vector)), vector.sha256);
  assert.equal(hex(await context()), fixture.refreshContext.sha256);
  assert.notEqual(
    hex(await flow(fixture.flowBindings[0], { authEpoch: "9007199254740992" })),
    fixture.flowBindings[0].sha256,
  );
});

test("unknown operations, zero/wrong UUIDs and noncanonical refresh aliases refuse without bytes", async () => {
  for (const operation of [0, 5, -1, 1.5, NaN])
    assert.equal(
      sdk.tryInitialSigningData(
        operation,
        id(fixture.ids.command),
        bytes(fixture.challengeHex),
        bytes(fixture.bindingHex),
      ),
      undefined,
    );
  for (const command of [undefined, id("00".repeat(16)), id("01".repeat(15)), id("01".repeat(17))])
    assert.equal(
      sdk.tryInitialSigningData(1, command, bytes(fixture.challengeHex), bytes(fixture.bindingHex)),
      undefined,
    );
  assert.equal(
    sdk.tryInitialSigningData(
      1,
      id(fixture.ids.command),
      new Uint8Array(31),
      bytes(fixture.bindingHex),
    ),
    undefined,
  );
  assert.equal(
    sdk.tryInitialSigningData(
      1,
      id(fixture.ids.command),
      bytes(fixture.challengeHex),
      new Uint8Array(33),
    ),
    undefined,
  );
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_",
    token = fixture.refresh.canonicalToken;
  const alias = token.slice(0, -1) + alphabet[alphabet.indexOf(token.at(-1)) + 1];
  assert.deepEqual(Buffer.from(alias, "base64url"), Buffer.from(token, "base64url"));
  for (const invalid of [
    "",
    token + "=",
    token + "\n",
    token.slice(1),
    "+" + token.slice(1),
    alias,
  ])
    assert.equal(
      await sdk.tryRefreshSigningData(id(fixture.ids.command), bytes(fixture.contextHex), invalid),
      undefined,
    );
  assert.equal(
    await sdk.tryRefreshSigningData(id(fixture.ids.command), new Uint8Array(31), token),
    undefined,
  );
});

test("binding/context refuse overflow, missing facts, malformed UTF16, key syntax and ambiguous direct fields", async () => {
  const native = fixture.flowBindings[0],
    direct = fixture.flowBindings[1];
  for (const change of [
    { realmId: "00".repeat(16) },
    { productId: "other" },
    { platform: "windows\n" },
    { platform: "\ud800" },
    { redirectUri: "arcscope://\ud800" },
    { clientId: "\udc00" },
    { redirectUri: "x".repeat(2049) },
    { keyVersion: "0" },
    { keyVersion: "9223372036854775808" },
    { purpose: 0 },
    { purpose: 6 },
    { authEpoch: "0" },
    { recoveryGeneration: "-1" },
    { recoveryRevision: "0" },
    { publicKeySha256Hex: "01".repeat(31) },
    { pkceChallengeHex: "01".repeat(33) },
    { expiresAtMicros: "0" },
    { expiresAtMicros: "253402300800000000" },
    { clientId: "" },
  ])
    assert.equal(await flow(native, change), undefined, JSON.stringify(change));
  assert.equal(await flow(direct, { pkceChallengeHex: "01".repeat(32) }), undefined);
  assert.equal(await flow(direct, { stateSha256Hex: "01".repeat(32) }), undefined);
  for (const change of [
    { familyId: "00".repeat(16) },
    { productId: "other" },
    { keyVersion: "0" },
    { purpose: 0 },
    { authEpoch: "0" },
    { recoveryGeneration: "-1" },
    { sessionRevision: "0" },
    { familyExpiresAtMicros: "253402300800000000" },
  ])
    assert.equal(await context(change), undefined);
});

test("async server hashing owns complete snapshots rather than retaining callers' UUID/hash arrays", async () => {
  const v = fixture.refreshContext,
    realm = id(v.realmId),
    user = id(v.userId),
    device = id(v.deviceId),
    installation = id(v.installationId),
    session = id(v.sessionId),
    family = id(v.familyId),
    keyHash = bytes(v.publicKeySha256Hex);
  const pending = sdk.tryRefreshContextHash(
    realm,
    user,
    device,
    installation,
    session,
    family,
    v.productId,
    keyHash,
    BigInt(v.keyVersion),
    v.purpose,
    BigInt(v.authEpoch),
    BigInt(v.recoveryGeneration),
    BigInt(v.sessionRevision),
    BigInt(v.familyExpiresAtMicros),
  );
  for (const value of [realm, user, device, installation, session, family]) value.value.fill(0);
  keyHash.fill(0);
  assert.equal(hex(await pending), v.sha256);
});

const publicKey = Buffer.from(
  "3059301306072a8648ce3d020106082a8648ce3d03010703420004" +
    "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296" +
    "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5",
  "hex",
);

test("generated installation adjuncts preserve genuine optional presence and strict P256/Int64/P1363 bounds", async () => {
  const original = JSON.parse(
    await readFile(new URL("../../fixtures/public/con-07-identity.json", import.meta.url), "utf8"),
  );
  const positive = (target) =>
    structuredClone(original.cases.find((v) => v.target === target && v.valid).value);
  const roundtrip = (schema, value, valid) => {
    const message = fromJson(schema, value);
    const wire = toBinary(schema, message);
    const copy = fromBinary(schema, wire);
    assert.equal(valid(message), true);
    assert.equal(valid(copy), true);
    assert.deepEqual(toBinary(schema, copy), wire);
    return message;
  };
  const key = positive("InstallationClaim");
  roundtrip(proto.InstallationClaimSchema, key, proto.isInstallationClaim); // Browser unbound remains a shape, never key authority.
  key.publicKey = publicKey.toString("base64");
  key.keyVersion = "9223372036854775807";
  roundtrip(proto.InstallationClaimSchema, key, proto.isInstallationClaim);
  const offCurve = Buffer.from(publicKey);
  offCurve[90] ^= 1;
  for (const patch of [
    { publicKey: undefined },
    { keyVersion: undefined },
    { keyVersion: "0" },
    { keyVersion: "9223372036854775808" },
    { publicKey: offCurve.toString("base64") },
    { publicKey: Buffer.concat([publicKey, Buffer.of(0)]).toString("base64") },
  ]) {
    const value = { ...key, ...patch };
    for (const name of Object.keys(value)) if (value[name] === undefined) delete value[name];
    assert.equal(proto.isInstallationClaim(fromJson(proto.InstallationClaimSchema, value)), false);
  }
  const challenge = positive("AuthChallenge");
  roundtrip(proto.AuthChallengeSchema, challenge, proto.isAuthChallenge);
  Object.assign(challenge, {
    installationProofChallenge: Buffer.alloc(32, 1).toString("base64"),
    installationProofBinding: Buffer.alloc(32, 2).toString("base64"),
    installationKeyVersion: "1",
  });
  roundtrip(proto.AuthChallengeSchema, challenge, proto.isAuthChallenge);
  for (const field of [
    "installationProofChallenge",
    "installationProofBinding",
    "installationKeyVersion",
  ]) {
    const value = { ...challenge };
    delete value[field];
    assert.equal(proto.isAuthChallenge(fromJson(proto.AuthChallengeSchema, value)), false);
  }
  const proof = { keyVersion: "1", signature: Buffer.alloc(64, 1).toString("base64") };
  roundtrip(proto.InstallationPossessionProofSchema, proof, proto.isInstallationPossessionProof);
  for (const value of [
    { signature: proof.signature },
    { keyVersion: "1" },
    { ...proof, keyVersion: "0" },
    { ...proof, signature: Buffer.alloc(70, 1).toString("base64") },
  ])
    assert.equal(
      proto.isInstallationPossessionProof(fromJson(proto.InstallationPossessionProofSchema, value)),
      false,
    );
  const session = positive("NativeSession");
  assert.equal(proto.isNativeSession(fromJson(proto.NativeSessionSchema, session)), false);
  Object.assign(session, {
    recoveryGeneration: "0",
    installationProofContext: Buffer.alloc(32, 3).toString("base64"),
    installationKeyVersion: "1",
  });
  roundtrip(proto.NativeSessionSchema, session, proto.isNativeSession);
  for (const patch of [
    { installationProofContext: Buffer.alloc(31, 3).toString("base64") },
    { installationKeyVersion: "0" },
  ])
    assert.equal(
      proto.isNativeSession(fromJson(proto.NativeSessionSchema, { ...session, ...patch })),
      false,
    );
});

test("actual generated native forms bind closed public-key and proof fields and refuse aliases or missing fields", () => {
  const authorize = {
    client_id: "arcscope.desktop",
    redirect_uri: "com.arcforges.arcscope:/auth/callback",
    response_type: "code",
    code_challenge: Buffer.alloc(32, 1).toString("base64url"),
    code_challenge_method: "S256",
    state: "original-state",
    installationId: "11223344-5566-4788-99aa-bbccddeeff00",
    publicKey: publicKey.toString("base64url"),
    keyVersion: "9223372036854775807",
  };
  const callback = {
    code: "x".repeat(43),
    state: authorize.state,
    installationProofChallenge: Buffer.alloc(32, 2).toString("base64url"),
    installationProofBinding: Buffer.alloc(32, 3).toString("base64url"),
    installationKeyVersion: "1",
  };
  const token = {
    grant_type: "authorization_code",
    code: callback.code,
    code_verifier: "v".repeat(43),
    client_id: authorize.client_id,
    redirect_uri: authorize.redirect_uri,
    installationId: authorize.installationId,
    commandId: "21223344-5566-4788-99aa-bbccddeeff00",
    installationKeyVersion: "1",
    installationProofSignature: Buffer.alloc(64, 4).toString("base64url"),
  };
  for (const [value, write, parse, validate] of [
    [
      authorize,
      api.serializeNativeAuthorizeRequestForm,
      api.tryParseNativeAuthorizeRequestForm,
      api.isNativeAuthorizeRequest,
    ],
    [
      callback,
      api.serializeNativeAuthorizeCallbackSuccessForm,
      api.tryParseNativeAuthorizeCallbackSuccessForm,
      api.isNativeAuthorizeCallbackSuccess,
    ],
    [
      token,
      api.serializeNativeTokenRequestForm,
      api.tryParseNativeTokenRequestForm,
      api.isNativeTokenRequest,
    ],
  ]) {
    const wire = write(value);
    const result = parse(wire);
    assert.equal(result.ok, true);
    assert.deepEqual(result.value, value);
    assert.deepEqual(write(result.value), wire);
    const text = new TextDecoder().decode(wire);
    const name = Object.keys(value).at(-1);
    assert.equal(parse(text + "&" + name + "=" + encodeURIComponent(value[name])).ok, false);
    assert.equal(parse(text + "&unknown=1").ok, false);
    const absent = { ...value };
    delete absent[name];
    assert.equal(validate(absent), false);
  }
  const offCurve = Buffer.from(publicKey);
  offCurve[90] ^= 1;
  for (const change of [
    { publicKey: offCurve.toString("base64url") },
    { publicKey: authorize.publicKey + "=" },
    { keyVersion: "0" },
    { keyVersion: "01" },
    { keyVersion: "9223372036854775808" },
  ])
    assert.equal(api.isNativeAuthorizeRequest({ ...authorize, ...change }), false);
  for (const change of [
    { installationProofSignature: Buffer.alloc(70).toString("base64url") },
    { installationProofSignature: token.installationProofSignature + "=" },
    { installationKeyVersion: "0" },
    { commandId: "00000000-0000-0000-0000-000000000000" },
  ])
    assert.equal(api.isNativeTokenRequest({ ...token, ...change }), false);
  assert.equal(
    api.isNativeAuthorizeCallbackSuccess({
      ...callback,
      installationProofBinding: Buffer.alloc(31).toString("base64url"),
    }),
    false,
  );
});
