// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import test from "node:test";

const fixture = JSON.parse(await readFile(new URL("../../fixtures/public/con-34-installation-possession.json", import.meta.url), "utf8"));
const sdk = await import(process.env.CON34_HELPER_PATH ?? "../../src/public/ts/proto/dist/installation-possession.js");
const bytes = (hex) => Uint8Array.from(Buffer.from(hex, "hex"));
const id = (hex) => ({ $typeName: "arcforges.foundation.v1.Id", value: bytes(hex) });
const hex = (value) => Buffer.from(value).toString("hex");
const flow = (original, changed = {}) => {
  const v = { ...original, ...changed };
  return sdk.tryFlowBindingHash(id(v.realmId), id(v.flowId), id(v.installationId), v.productId, v.platform,
    bytes(v.publicKeySha256Hex), BigInt(v.keyVersion), v.purpose, BigInt(v.authEpoch), BigInt(v.recoveryGeneration),
    BigInt(v.recoveryRevision), v.clientId, v.redirectUri, bytes(v.pkceChallengeHex), bytes(v.stateSha256Hex), BigInt(v.expiresAtMicros));
};
const context = (changed = {}) => {
  const v = { ...fixture.refreshContext, ...changed };
  return sdk.tryRefreshContextHash(id(v.realmId), id(v.userId), id(v.deviceId), id(v.installationId), id(v.sessionId), id(v.familyId),
    v.productId, bytes(v.publicKeySha256Hex), BigInt(v.keyVersion), v.purpose, BigInt(v.authEpoch), BigInt(v.recoveryGeneration),
    BigInt(v.sessionRevision), BigInt(v.familyExpiresAtMicros));
};

test("all four closed initial operations match independent network-order binary vectors", () => {
  for (const vector of fixture.initial) {
    const data = sdk.tryInitialSigningData(vector.operation, id(fixture.ids.command), bytes(fixture.challengeHex), bytes(fixture.bindingHex));
    assert.equal(hex(data), vector.dataHex);
    assert.equal(createHash("sha256").update(data).digest("hex"), vector.sha256);
  }
  assert.notEqual(fixture.initial[0].dataHex, fixture.initial[3].dataHex);
});

test("refresh hashes exact canonical synthetic token and captures mutable inputs before async digest", async () => {
  const command = id(fixture.ids.command), originalContext = bytes(fixture.contextHex);
  const pending = sdk.tryRefreshSigningData(command, originalContext, fixture.refresh.canonicalToken);
  command.value.fill(0); originalContext.fill(0);
  const data = await pending;
  assert.equal(hex(data), fixture.refresh.dataHex);
  assert.equal(createHash("sha256").update(data).digest("hex"), fixture.refresh.sha256);
  assert.equal(data.length, fixture.refresh.dataHex.length / 2);
});

test("full native and direct flow hashes preserve UTF8 framing, Int64 precision and zero-pair distinction", async () => {
  for (const vector of fixture.flowBindings) assert.equal(hex(await flow(vector)), vector.sha256);
  assert.equal(hex(await context()), fixture.refreshContext.sha256);
  assert.notEqual(hex(await flow(fixture.flowBindings[0], { authEpoch: "9007199254740992" })), fixture.flowBindings[0].sha256);
});

test("unknown operations, zero/wrong UUIDs and noncanonical refresh aliases refuse without bytes", async () => {
  for (const operation of [0, 5, -1, 1.5, NaN])
    assert.equal(sdk.tryInitialSigningData(operation, id(fixture.ids.command), bytes(fixture.challengeHex), bytes(fixture.bindingHex)), undefined);
  for (const command of [undefined, id("00".repeat(16)), id("01".repeat(15)), id("01".repeat(17))])
    assert.equal(sdk.tryInitialSigningData(1, command, bytes(fixture.challengeHex), bytes(fixture.bindingHex)), undefined);
  assert.equal(sdk.tryInitialSigningData(1, id(fixture.ids.command), new Uint8Array(31), bytes(fixture.bindingHex)), undefined);
  assert.equal(sdk.tryInitialSigningData(1, id(fixture.ids.command), bytes(fixture.challengeHex), new Uint8Array(33)), undefined);
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_", token = fixture.refresh.canonicalToken;
  const alias = token.slice(0, -1) + alphabet[alphabet.indexOf(token.at(-1)) + 1];
  assert.deepEqual(Buffer.from(alias, "base64url"), Buffer.from(token, "base64url"));
  for (const invalid of ["", token + "=", token + "\n", token.slice(1), "+" + token.slice(1), alias])
    assert.equal(await sdk.tryRefreshSigningData(id(fixture.ids.command), bytes(fixture.contextHex), invalid), undefined);
  assert.equal(await sdk.tryRefreshSigningData(id(fixture.ids.command), new Uint8Array(31), token), undefined);
});

test("binding/context refuse overflow, missing facts, malformed UTF16, key syntax and ambiguous direct fields", async () => {
  const native = fixture.flowBindings[0], direct = fixture.flowBindings[1];
  for (const change of [
    { realmId: "00".repeat(16) }, { productId: "other" }, { platform: "windows\n" }, { platform: "\ud800" },
    { redirectUri: "arcscope://\ud800" }, { clientId: "\udc00" }, { redirectUri: "x".repeat(2049) },
    { keyVersion: "0" }, { keyVersion: "9223372036854775808" }, { purpose: 0 }, { purpose: 6 },
    { authEpoch: "0" }, { recoveryGeneration: "-1" }, { recoveryRevision: "0" },
    { publicKeySha256Hex: "01".repeat(31) }, { pkceChallengeHex: "01".repeat(33) },
    { expiresAtMicros: "0" }, { expiresAtMicros: "253402300800000000" }, { clientId: "" },
  ]) assert.equal(await flow(native, change), undefined, JSON.stringify(change));
  assert.equal(await flow(direct, { pkceChallengeHex: "01".repeat(32) }), undefined);
  assert.equal(await flow(direct, { stateSha256Hex: "01".repeat(32) }), undefined);
  for (const change of [{ familyId: "00".repeat(16) }, { productId: "other" }, { keyVersion: "0" },
    { purpose: 0 }, { authEpoch: "0" }, { recoveryGeneration: "-1" }, { sessionRevision: "0" },
    { familyExpiresAtMicros: "253402300800000000" }]) assert.equal(await context(change), undefined);
});

test("async server hashing owns complete snapshots rather than retaining callers' UUID/hash arrays", async () => {
  const v = fixture.refreshContext, realm = id(v.realmId), user = id(v.userId), device = id(v.deviceId),
    installation = id(v.installationId), session = id(v.sessionId), family = id(v.familyId), keyHash = bytes(v.publicKeySha256Hex);
  const pending = sdk.tryRefreshContextHash(realm, user, device, installation, session, family, v.productId, keyHash,
    BigInt(v.keyVersion), v.purpose, BigInt(v.authEpoch), BigInt(v.recoveryGeneration), BigInt(v.sessionRevision), BigInt(v.familyExpiresAtMicros));
  for (const value of [realm, user, device, installation, session, family]) value.value.fill(0);
  keyHash.fill(0);
  assert.equal(hex(await pending), v.sha256);
});
