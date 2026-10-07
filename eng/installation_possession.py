# SPDX-License-Identifier: Apache-2.0
"""One source-owned, closed canonical installation transcript in three SDKs.

This module emits no signing operation, key custody or authorization result.
"""
from pathlib import Path
from generate_shapes import emit, HEADER

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('identity.completeAuthentication', 'identity.redeemEmailCode', 'identity.completeEnrollment', 'native.token')
INITIAL_DOMAIN = 'arcforges.installation-possession.v1'
REFRESH_DOMAIN = 'arcforges.installation-refresh-possession.v1'

cs_rules = {
    'installationClaim': 'if (value.HasPublicKey != value.HasKeyVersion || value.HasPublicKey && !InstallationSpki(value.PublicKey.Span)) return false;',
    'installationChallenge': 'if (value.HasInstallationProofChallenge != value.HasInstallationProofBinding || value.HasInstallationProofChallenge != value.HasInstallationKeyVersion) return false;',
}
ts_rules = {
    'installationClaim': 'if ((value.publicKey !== undefined) !== (value.keyVersion !== undefined) || value.publicKey !== undefined && !installationSpki(value.publicKey as Uint8Array)) return false;',
    'installationChallenge': 'if ((value.installationProofChallenge !== undefined) !== (value.installationProofBinding !== undefined) || (value.installationProofChallenge !== undefined) !== (value.installationKeyVersion !== undefined)) return false;',
}

CS_SHAPE_HELPERS = r'''
    private static bool InstallationSpki(global::System.ReadOnlySpan<byte> bytes)
    {
        if (bytes.Length != 91) return false;
        try
        {
            using var key = global::System.Security.Cryptography.ECDsa.Create();
            key.ImportSubjectPublicKeyInfo(bytes, out var consumed);
            return consumed == bytes.Length && key.KeySize == 256 && key.ExportParameters(false).Curve.Oid.Value == "1.2.840.10045.3.1.7" && key.ExportSubjectPublicKeyInfo().AsSpan().SequenceEqual(bytes);
        }
        catch (global::System.Security.Cryptography.CryptographicException) { return false; }
        catch (global::System.ArgumentException) { return false; }
        catch (global::System.PlatformNotSupportedException) { return false; }
    }
'''
TS_SHAPE_HELPERS = r'''
function installationSpki(bytes: Uint8Array): boolean {
  const prefix=[0x30,0x59,0x30,0x13,0x06,0x07,0x2a,0x86,0x48,0xce,0x3d,0x02,0x01,0x06,0x08,0x2a,0x86,0x48,0xce,0x3d,0x03,0x01,0x07,0x03,0x42,0x00,0x04];
  if(bytes.length!==91 || !prefix.every((v,i)=>bytes[i]===v)) return false;
  const integer=(data:Uint8Array)=>data.reduce((v,b)=>(v<<8n)|BigInt(b),0n);
  const x=integer(bytes.subarray(27,59)),y=integer(bytes.subarray(59));
  const p=0xffffffff00000001000000000000000000000000ffffffffffffffffffffffffn;
  const b=0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604bn;
  return x<p && y<p && (y*y-(x*x*x-3n*x+b))%p===0n;
}
'''

CS_SOURCE = r'''
#nullable enable
using System;
using System.Buffers.Binary;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using ArcForges.Contracts.Foundation.V1;

namespace ArcForges.Contracts.PublicApi;

/// <summary>The closed native completion operations; never a caller-selected signing label.</summary>
public enum InstallationInitialOperation
{
    /// <summary>Complete the original authentication flow.</summary>
    CompleteAuthentication = 1,
    /// <summary>Redeem the original email proof.</summary>
    RedeemEmailCode = 2,
    /// <summary>Complete original enrollment with separately verified credential evidence.</summary>
    CompleteEnrollment = 3,
    /// <summary>Redeem an original native authorization code.</summary>
    NativeToken = 4,
}

/// <summary>Closed canonical public signing data. No private key, signature or permission is produced.</summary>
public static class InstallationPossession
{
    private static readonly UTF8Encoding Utf8 = new(false, true);

    /// <summary>Creates owned signing bytes for the selected exact operation and original server challenge/binding.</summary>
    public static bool TryInitialSigningData(InstallationInitialOperation operation, Id? commandId,
        ReadOnlySpan<byte> installationChallenge, ReadOnlySpan<byte> installationBinding, out byte[]? signingData)
    {
        signingData = null;
        var label = operation switch { __LABEL_SWITCH__ _ => null };
        if (label is null || !ValidId(commandId) || installationChallenge.Length != 32 || installationBinding.Length != 32) return false;
        using var stream = Begin("__INITIAL__", label);
        stream.Write(commandId!.Value.Span); stream.Write(installationChallenge); stream.Write(installationBinding);
        signingData = stream.ToArray(); return true;
    }

    /// <summary>Creates owned refresh signing bytes from the exact server context and canonical32-byte token; the token is hashed and never returned.</summary>
    public static bool TryRefreshSigningData(Id? commandId, ReadOnlySpan<byte> installationContext,
        string? canonicalRefreshToken, out byte[]? signingData)
    {
        signingData = null;
        if (!ValidId(commandId) || installationContext.Length != 32 || canonicalRefreshToken is null || canonicalRefreshToken.Length != 43) return false;
        Span<char> encoded = stackalloc char[44]; Span<byte> token = stackalloc byte[32]; Span<char> canonical = stackalloc char[44];
        try
        {
            for (var i = 0; i < 43; i++) { var c = canonicalRefreshToken[i]; if (!(char.IsAsciiLetterOrDigit(c) || c is '-' or '_')) return false; encoded[i] = c == '-' ? '+' : c == '_' ? '/' : c; }
            encoded[43] = '=';
            if (!Convert.TryFromBase64Chars(encoded, token, out var count) || count != 32 || !Convert.TryToBase64Chars(token, canonical, out var chars) || chars != 44) return false;
            for (var i = 0; i < 43; i++) { var c = canonical[i] == '+' ? '-' : canonical[i] == '/' ? '_' : canonical[i]; if (c != canonicalRefreshToken[i]) return false; }
            using var stream = Begin("__REFRESH__", "identity.refreshSession");
            stream.Write(commandId!.Value.Span); stream.Write(installationContext);
            Span<byte> digest = stackalloc byte[32]; SHA256.HashData(token, digest); stream.Write(digest); CryptographicOperations.ZeroMemory(digest);
            signingData = stream.ToArray(); return true;
        }
        finally { CryptographicOperations.ZeroMemory(token); encoded.Clear(); canonical.Clear(); }
    }

    /// <summary>Hashes the full original flow binding; all input facts must come from the actual owner, and this digest is not proof.</summary>
    public static bool TryFlowBindingHash(Id? realmId, Id? flowId, Id? installationId, string? productId, string? platform,
        ReadOnlySpan<byte> publicKeySha256, long keyVersion, V1.AuthPurpose purpose, long authEpoch, long recoveryGeneration,
        long recoveryRevision, string? clientId, string? redirectUri, ReadOnlySpan<byte> pkceChallenge,
        ReadOnlySpan<byte> stateSha256, long expiresAtMicros, out byte[]? binding)
    {
        binding = null;
        if (!ValidId(realmId) || !ValidId(flowId) || !ValidId(installationId) || !Product(productId) || !Key(platform, 128) || publicKeySha256.Length != 32 || keyVersion <= 0 || (int)purpose is < 1 or > 5 || authEpoch <= 0 || recoveryGeneration < 0 || recoveryRevision <= 0 || !Text(clientId, 256, true) || !Text(redirectUri, 2048, true) || pkceChallenge.Length != 32 || stateSha256.Length != 32 || expiresAtMicros is <= 0 or > 253402300799999999L) return false;
        if ((clientId!.Length == 0) != (redirectUri!.Length == 0) || clientId.Length == 0 && (!Zero(pkceChallenge) || !Zero(stateSha256))) return false;
        using var stream = Domain("arcforges.installation-flow-binding.v1");
        stream.Write(realmId!.Value.Span); stream.Write(flowId!.Value.Span); stream.Write(installationId!.Value.Span);
        String(stream, productId!); String(stream, platform!); stream.Write(publicKeySha256); Integer(stream, keyVersion); Integer(stream, (int)purpose); Integer(stream, authEpoch); Integer(stream, recoveryGeneration); Integer(stream, recoveryRevision);
        String(stream, clientId); String(stream, redirectUri); stream.Write(pkceChallenge); stream.Write(stateSha256); Integer(stream, expiresAtMicros);
        binding = SHA256.HashData(stream.GetBuffer().AsSpan(0, checked((int)stream.Length))); return true;
    }

    /// <summary>Hashes exact current server-owned session/install facts for refresh; never accepts a caller context as authority.</summary>
    public static bool TryRefreshContextHash(Id? realmId, Id? userId, Id? deviceId, Id? installationId, Id? sessionId,
        Id? familyId, string? productId, ReadOnlySpan<byte> publicKeySha256, long keyVersion, V1.AuthPurpose purpose,
        long authEpoch, long recoveryGeneration, long sessionRevision, long familyExpiresAtMicros, out byte[]? context)
    {
        context = null;
        if (!ValidId(realmId) || !ValidId(userId) || !ValidId(deviceId) || !ValidId(installationId) || !ValidId(sessionId) || !ValidId(familyId) || !Product(productId) || publicKeySha256.Length != 32 || keyVersion <= 0 || (int)purpose is < 1 or > 5 || authEpoch <= 0 || recoveryGeneration < 0 || sessionRevision <= 0 || familyExpiresAtMicros is <= 0 or > 253402300799999999L) return false;
        using var stream = Domain("arcforges.installation-refresh-context.v1");
        stream.Write(realmId!.Value.Span); stream.Write(userId!.Value.Span); stream.Write(deviceId!.Value.Span); stream.Write(installationId!.Value.Span); stream.Write(sessionId!.Value.Span); stream.Write(familyId!.Value.Span); String(stream, productId!); stream.Write(publicKeySha256); Integer(stream, keyVersion); Integer(stream, (int)purpose); Integer(stream, authEpoch); Integer(stream, recoveryGeneration); Integer(stream, sessionRevision); Integer(stream, familyExpiresAtMicros);
        context = SHA256.HashData(stream.GetBuffer().AsSpan(0, checked((int)stream.Length))); return true;
    }

    private static bool ValidId(Id? id) => id is not null && id.HasValue && id.Value.Length == 16 && !Zero(id.Value.Span);
    private static bool Zero(ReadOnlySpan<byte> bytes) { foreach (var b in bytes) if (b != 0) return false; return true; }
    private static bool Product(string? text) => text is "arcscope" or "companion";
    private static bool Text(string? text, int max, bool empty = false) { if (text is null || !empty && text.Length == 0 || text.Length > max) return false; try { return Utf8.GetByteCount(text) <= max; } catch (EncoderFallbackException) { return false; } }
    private static bool Key(string? text, int max) { if (!Text(text, max)) return false; foreach (var c in text!) if (!(char.IsAsciiLetterOrDigit(c) || c is '.' or '_' or ':' or '/' or '-')) return false; return true; }
    private static MemoryStream Domain(string domain) { var stream = new MemoryStream(1024); stream.Write(Utf8.GetBytes(domain)); stream.WriteByte(0); return stream; }
    private static MemoryStream Begin(string domain, string label) { var stream = Domain(domain); String(stream, label); return stream; }
    private static void String(Stream stream, string text) { var bytes = Utf8.GetBytes(text); Span<byte> size = stackalloc byte[4]; BinaryPrimitives.WriteUInt32BigEndian(size, (uint)bytes.Length); stream.Write(size); stream.Write(bytes); }
    private static void Integer(Stream stream, long value) { Span<byte> data = stackalloc byte[8]; BinaryPrimitives.WriteInt64BigEndian(data, value); stream.Write(data); }
}
'''

TS_SOURCE = r'''
import type { Id } from "./gen/arcforges/foundation/v1/foundation_pb.js";
/** Closed source-owned completion operation; no arbitrary signing label. */
export enum InstallationInitialOperation { CompleteAuthentication=1, RedeemEmailCode=2, CompleteEnrollment=3, NativeToken=4 }
const labels = __LABELS__;
const encoder = new TextEncoder();
function id(value: Id | undefined): value is Id & {value: Uint8Array} { return value?.value instanceof Uint8Array && value.value.length===16 && value.value.some(x=>x!==0); }
function join(domain:string,label:string,command:Uint8Array,a:Uint8Array,b:Uint8Array):Uint8Array {
  const prefix=encoder.encode(domain+'\0'),name=encoder.encode(label),output=new Uint8Array(prefix.length+4+name.length+16+64);output.set(prefix);new DataView(output.buffer).setUint32(prefix.length,name.length,false);let n=prefix.length+4;output.set(name,n);n+=name.length;output.set(command,n);n+=16;output.set(a,n);output.set(b,n+32);return output;
}
/** Returns newly owned canonical data or undefined. No signature or permission is produced. */
export function tryInitialSigningData(operation:InstallationInitialOperation,commandId:Id|undefined,challenge:Uint8Array,binding:Uint8Array):Uint8Array|undefined {
  if(!Number.isInteger(operation) || operation<1 || operation>4 || !id(commandId) || !(challenge instanceof Uint8Array) || challenge.length!==32 || !(binding instanceof Uint8Array) || binding.length!==32)return undefined;
  return join('__INITIAL__',labels[operation-1]!,commandId.value,challenge,binding);
}
/** Hashes the decoded canonical token; never returns the token. Private key custody is outside this helper. */
export async function tryRefreshSigningData(commandId:Id|undefined,context:Uint8Array,canonicalRefreshToken:string):Promise<Uint8Array|undefined> {
  if(!id(commandId) || !(context instanceof Uint8Array) || context.length!==32 || typeof canonicalRefreshToken!=='string' || /^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$/.exec(canonicalRefreshToken)?.[0]!==canonicalRefreshToken)return undefined;
  const capturedCommand=commandId.value.slice(),capturedContext=context.slice(),token=new Uint8Array(32);
  try { const raw=atob(canonicalRefreshToken.replaceAll('-','+').replaceAll('_','/')+'=');if(raw.length!==32)return undefined;for(let i=0;i<32;i++)token[i]=raw.charCodeAt(i);const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',token));return join('__REFRESH__','identity.refreshSession',capturedCommand,capturedContext,digest); }
  finally {token.fill(0);capturedCommand.fill(0);capturedContext.fill(0);}
}
'''

KOTLIN_SOURCE = r'''
package io.github.arcforges.contracts

import io.github.arcforges.contracts.foundation.v1.Id
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Base64

/** Closed native completion operation. No caller-selected signing label exists. */
enum class InstallationInitialOperation(val wire: Int) { CompleteAuthentication(1), RedeemEmailCode(2), CompleteEnrollment(3), NativeToken(4) }

/** Pure canonical public data; no key custody, signature or authentication result. */
object InstallationPossession {
    private val labels = arrayOf(__KOTLIN_LABELS__)
    private fun validId(value: Id?): Boolean = value != null && value.hasValue() && value.value.size() == 16 && value.value.toByteArray().any { it.toInt() != 0 }
    private fun join(domain: String, label: String, command: ByteArray, a: ByteArray, b: ByteArray): ByteArray {
        val prefix=(domain+"\u0000").toByteArray(StandardCharsets.UTF_8); val name=label.toByteArray(StandardCharsets.UTF_8)
        return ByteBuffer.allocate(prefix.size+4+name.size+16+64).order(ByteOrder.BIG_ENDIAN).put(prefix).putInt(name.size).put(name).put(command).put(a).put(b).array()
    }
    fun tryInitialSigningData(operation: InstallationInitialOperation?, commandId: Id?, challenge: ByteArray, binding: ByteArray): ByteArray? {
        if(operation==null || !validId(commandId) || challenge.size!=32 || binding.size!=32) return null
        return join("__INITIAL__", labels[operation.wire-1], commandId!!.value.toByteArray(), challenge, binding)
    }
    fun tryRefreshSigningData(commandId: Id?, context: ByteArray, canonicalRefreshToken: String): ByteArray? {
        if(!validId(commandId) || context.size!=32 || !Regex("[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]").matches(canonicalRefreshToken))return null
        val token=try { Base64.getUrlDecoder().decode(canonicalRefreshToken) } catch(_: IllegalArgumentException) {return null}
        try {
            if(token.size!=32 || Base64.getUrlEncoder().withoutPadding().encodeToString(token)!=canonicalRefreshToken)return null
            return join("__REFRESH__", "identity.refreshSession", commandId!!.value.toByteArray(), context, MessageDigest.getInstance("SHA-256").digest(token))
        } finally {token.fill(0)}
    }
}
'''

def generate(check: bool = False) -> None:
    import json
    csharp = CS_SOURCE.replace('__LABEL_SWITCH__', ''.join(f'{i+1} => "{name}", ' for i,name in enumerate(LABELS)))
    replacements = {'__INITIAL__':INITIAL_DOMAIN,'__REFRESH__':REFRESH_DOMAIN}
    ts = TS_SOURCE.replace('__LABELS__',json.dumps(LABELS))
    kotlin = KOTLIN_SOURCE.replace('__KOTLIN_LABELS__',', '.join(json.dumps(v) for v in LABELS))
    for old,new in replacements.items():csharp=csharp.replace(old,new);ts=ts.replace(old,new);kotlin=kotlin.replace(old,new)
    emit(ROOT/'src/public/dotnet/ArcForges.Contracts.PublicApi/Generated/InstallationPossessionTranscript.cs',HEADER+csharp.lstrip(),check)
    emit(ROOT/'src/public/ts/proto/src/installation-possession.ts',HEADER+ts.lstrip(),check)
    emit(ROOT/'src/public/kotlin/contracts-proto/src/main/kotlin/io/github/arcforges/contracts/InstallationPossessionTranscript.kt',HEADER+kotlin.lstrip(),check)
