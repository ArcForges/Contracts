# SPDX-License-Identifier: Apache-2.0
"""Closed storage-profile relationships. No provider I/O or authorization."""
from __future__ import annotations

cs_rules = {
    "authenticationCredential": "if (((int)value.Method == 1) != (value.HasPublicKeySha256 && value.HasUserHandleSha256) || value.HasPublicKeySha256 != value.HasUserHandleSha256 || value.Revision.Value <= 0) return false;",
    "authenticationMethod": "if (value.Password is not null && (int)value.Password.Credential.Method != 3) return false;",
    "authenticationPassword": "if ((int)value.Credential.Method != 3) return false;",
    "authenticationNative": "if (value.NativeFlowRevision.Value <= 0) return false;",
    "authenticationPasskey": "if (!AuthenticationOrigins(value.Origins) || !global::System.Security.Cryptography.SHA256.HashData(value.Challenge.Span).AsSpan().SequenceEqual(value.ChallengeSha256.Span)) return false;",
    "authenticationOrigins": "if (!AuthenticationOrigins(value.Origins)) return false;",
    "authenticationCompletion": "if (!AuthenticationCompletion(value)) return false;",
    "authenticationFlow": "if (value.CalculateSize() > 131072 || !AuthenticationFlow(value)) return false;",
    "authenticationStepUp": "if (value.CalculateSize() > 131072 || !AuthenticationStepUp(value)) return false;",
    "authenticationOperator": "if (value.CalculateSize() > 65536 || !AuthenticationOperator(value)) return false;",
    "authenticationPolicies": "if (!AuthenticationPolicies(value)) return false;",
    "authenticationPolicyProjection": "if (!AuthenticationGuid(value.PolicyId)) return false;",
    "authenticationCustomer": "if (value.CalculateSize() > 65536 || value.RecoveryRevision.Value <= 0 || value.CompletedFlowRevision.Value <= 0 || value.TokenExpiresAtSeconds <= (value.HasAuthenticatedAtSeconds ? value.AuthenticatedAtSeconds : 0) || value.ObservedAt.UnixSeconds >= value.TokenExpiresAtSeconds || value.HasAuthenticatedAtSeconds && value.AuthenticatedAtSeconds > value.ObservedAt.UnixSeconds) return false;",
}

CS_HELPERS = r'''
    private static bool AuthenticationGuid(string text) => global::System.Guid.TryParseExact(text, "D", out var id) && id != global::System.Guid.Empty && id.ToString("D") == text;
    private static int AuthenticationTime(global::ArcForges.Contracts.Foundation.V1.Instant a, global::ArcForges.Contracts.Foundation.V1.Instant b) => a.UnixSeconds != b.UnixSeconds ? a.UnixSeconds.CompareTo(b.UnixSeconds) : a.Nanos.CompareTo(b.Nanos);
    private static bool AuthenticationReferenceEqual(global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.AuthenticationCredentialReference a, global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.AuthenticationCredentialReference b) =>
        a.IdentityId.Value.Equals(b.IdentityId.Value) && a.Revision.Value == b.Revision.Value && a.ProviderKey == b.ProviderKey && a.Method == b.Method && a.SubjectSha256.Equals(b.SubjectSha256) &&
        a.HasPublicKeySha256 == b.HasPublicKeySha256 && (!a.HasPublicKeySha256 || a.PublicKeySha256.Equals(b.PublicKeySha256)) &&
        a.HasUserHandleSha256 == b.HasUserHandleSha256 && (!a.HasUserHandleSha256 || a.UserHandleSha256.Equals(b.UserHandleSha256));
    private static bool AuthenticationOrigins(global::System.Collections.Generic.IEnumerable<string> values)
    {
        string? previous = null;
        foreach (var value in values)
        {
            if (previous is not null && global::System.StringComparer.Ordinal.Compare(previous, value) >= 0) return false;
            if (!global::System.Uri.TryCreate(value, global::System.UriKind.Absolute, out var uri) || uri.Scheme != "https" || uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0 || uri.AbsolutePath != "/" || value.EndsWith('/')) return false;
            previous = value;
        }
        return previous is not null;
    }
    private static bool AuthenticationInventory(global::System.Collections.Generic.IList<global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.AuthenticationCredentialReference> rows, int method, bool empty, bool actor = false)
    {
        if (rows.Count == 0) return empty;
        var selected = actor ? (int)rows[0].Method : method;
        if (rows.Count > 64 || selected != 1 && rows.Count != 1) return false;
        global::Google.Protobuf.ByteString? previous = null;
        var subjects = new global::System.Collections.Generic.HashSet<string>(global::System.StringComparer.Ordinal);
        foreach (var row in rows)
        {
            if ((int)row.Method != selected || row.Revision.Value <= 0 || previous is not null && previous.Span.SequenceCompareTo(row.IdentityId.Value.Span) >= 0) return false;
            if (!subjects.Add(row.ProviderKey + ":" + global::System.Convert.ToHexString(row.SubjectSha256.Span))) return false;
            previous = row.IdentityId.Value;
        }
        return true;
    }
    private static bool AuthenticationMethod(global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.AuthenticationMethodProofBinding proof, int method, bool enrollment, bool anonymous)
    {
        if (enrollment) return proof.Enrollment is not null && (int)proof.Enrollment.RegistrationCase == method;
        if (proof.Enrollment is not null) return false;
        if (proof.PasswordDiscovery is not null) return anonymous && method == 3;
        return (int)proof.ProofCase == method && (proof.Email is null || anonymous || proof.Email.AddressIdentityRevision is { Value: > 0 });
    }
    private static bool AuthenticationCompletion(global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.AuthenticationCompletionCapture value) =>
        value.UserRevision.Value > 0 && value.RecoveryRevision.Value > 0 &&
        (value.DeviceId is null) == (value.DeviceRevision is null) && (value.InstallationId is null) == (value.InstallationRevision is null) &&
        (value.DeviceRevision is null || value.DeviceRevision.Value > 0) && (value.InstallationRevision is null || value.InstallationRevision.Value > 0) &&
        (value.InstallationId is null || value.DeviceId is not null);
    private static bool AuthenticationFlow(global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.AuthenticationFlowPayload v)
    {
        var kind = (int)v.FlowKind; var method = (int)v.Method; var enrollment = (int)v.Purpose == 2 || kind == 6; var anonymous = v.UserId is null;
        if (AuthenticationTime(v.CreatedAt, v.ExpiresAt) >= 0 || v.RecoveryRevision.Value <= 0 || (v.UserId is null) != (v.UserRevision is null) || v.UserRevision is { Value: <= 0 }) return false;
        if ((v.SessionId is null) != (v.SessionRevision is null) || v.SessionRevision is { Value: <= 0 } || (v.DeviceId is null) != (v.DeviceRevision is null) || v.DeviceRevision is { Value: <= 0 } || v.InstallationRevision is { Value: <= 0 } || v.InstallationRevision is not null && v.InstallationId is null) return false;
        if (kind is 4 or 5 or 7 && anonymous || kind == 6 && (anonymous || v.InitialCredentials.Count != 0 || v.RecoveryAuthorization is null || (int)v.Purpose != 4) || kind != 6 && v.RecoveryAuthorization is not null) return false;
        if (v.RecoveryAuthorization is not null && v.RecoveryAuthorization.Revision.Value <= 0) return false;
        if (kind == 4 ? v.SessionId is null || !v.HasOperationClass || !v.HasTargetPayloadSha256 || (int)v.Purpose != 3 : v.HasOperationClass) return false;
        var browser = v.HasOrigin || v.HasPreauthBindingSha256 || v.HasCsrfSha256;
        if (browser && !(v.HasOrigin && v.HasPreauthBindingSha256 && v.HasCsrfSha256) || kind == 2 && !browser || kind is 1 or 9 && browser) return false;
        if ((kind == 1) != (v.NativeBinding is not null)) return false;
        var native = kind is 1 or 9;
        var keyFields = (v.HasInstallationPublicKeySha256 ? 1 : 0) + (v.HasInstallationKeyVersion ? 1 : 0) + (v.HasInstallationProofChallenge ? 1 : 0) + (v.HasInstallationProofBinding ? 1 : 0) + (v.HasInstallationPublicKey ? 1 : 0);
        if (keyFields != 0 && keyFields != 5 || native && (keyFields != 5 || v.InstallationId is null) || browser && keyFields != 0 || (v.InstallationId is not null) != v.HasProductId) return false;
        if (keyFields == 5 && !global::System.Security.Cryptography.SHA256.HashData(v.InstallationPublicKey.Span).AsSpan().SequenceEqual(v.InstallationPublicKeySha256.Span)) return false;
        if (anonymous && v.InitialCredentials.Count != 0 || !AuthenticationInventory(v.InitialCredentials, method, anonymous || kind == 6, enrollment) || !AuthenticationMethod(v.MethodProof, method, enrollment, anonymous)) return false;
        if (v.MethodProof.Password is not null && (v.InitialCredentials.Count != 1 || !AuthenticationReferenceEqual(v.InitialCredentials[0], v.MethodProof.Password.Credential))) return false;
        if (v.Completion is not null)
        {
            var c = v.Completion;
            if ((int)c.Credential.Method != method || c.AuthEpoch != v.AuthEpoch || c.RecoveryGeneration != v.RecoveryGeneration || c.RecoveryRevision.Value != v.RecoveryRevision.Value || AuthenticationTime(c.VerifiedAt, v.CreatedAt) < 0 || AuthenticationTime(c.VerifiedAt, v.ExpiresAt) >= 0) return false;
            if (!enrollment && v.InitialCredentials.Count != 0 && !v.InitialCredentials.Any(row => AuthenticationReferenceEqual(row, c.Credential))) return false;
            if (v.UserId is not null && (!v.UserId.Value.Equals(c.UserId.Value) || v.UserRevision!.Value != c.UserRevision.Value) || v.DeviceId is not null && (c.DeviceId is null || !v.DeviceId.Value.Equals(c.DeviceId.Value) || v.DeviceRevision!.Value != c.DeviceRevision!.Value) || c.InstallationId is not null && v.InstallationId is not null && !v.InstallationId.Value.Equals(c.InstallationId.Value) || v.InstallationRevision is not null && v.InstallationRevision.Value != c.InstallationRevision?.Value) return false;
        }
        return true;
    }
    private static bool AuthenticationStepUp(global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.StepUpMethodProofSnapshot v) =>
        v.RecoveryRevision.Value > 0 && v.UserRevision.Value > 0 && v.SessionRevision.Value > 0 && AuthenticationTime(v.PreparedAt, v.ExpiresAt) < 0 &&
        AuthenticationInventory(v.Credentials, (int)v.Method, false) && AuthenticationMethod(v.MethodProof, (int)v.Method, false, false) &&
        (v.MethodProof.Password is null || AuthenticationReferenceEqual(v.Credentials[0], v.MethodProof.Password.Credential)) &&
        (v.MethodProof.Passkey is null || v.MethodProof.Passkey.ChallengeSha256.Equals(v.ProofSha256));
    private static bool AuthenticationPolicies(global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.OperatorPolicyObservation v)
    {
        string? previous = null;
        foreach (var row in v.Policies)
        {
            if (previous is not null && global::System.StringComparer.Ordinal.Compare(previous, row.PolicyId) >= 0 || AuthenticationTime(row.ObservedAt, v.ObservedAt) > 0) return false;
            previous = row.PolicyId;
        }
        return true;
    }
    private static bool AuthenticationOperator(global::ArcForges.Contracts.CloudInternal.Identity.Storage.V1.OperatorAuthenticationEvidence v)
    {
        if (!AuthenticationGuid(v.TenantId) || !AuthenticationGuid(v.ClientId) || !AuthenticationGuid(v.ObjectId) || v.RecoveryRevision.Value <= 0 || v.CompletedFlowRevision.Value <= 0 || v.TokenExpiresAtSeconds <= v.AuthenticatedAtSeconds || v.ObservedAt.UnixSeconds >= v.TokenExpiresAtSeconds || v.AuthenticatedAtSeconds > v.ObservedAt.UnixSeconds) return false;
        var step = (int)v.Purpose == 2;
        if (step != (v.OperatorSessionId is not null) || step != (v.OperatorSessionRevision is not null) || step != v.HasPreviousEvidenceSha256 || step != v.HasOperatorSubjectSha256 || step != (v.PreviousEvidenceId is not null) || step != v.HasPreviousOperatorObjectId || step != v.HasPreviousOperatorSubject || v.OperatorSessionRevision is { Value: <= 0 }) return false;
        if (step && (!AuthenticationGuid(v.PreviousOperatorObjectId) || v.PreviousOperatorObjectId != v.ObjectId || v.PreviousOperatorSubject != v.PairwiseSubject)) return false;
        if (AuthenticationTime(v.PolicyBegin.ObservedAt, v.PolicyComplete.ObservedAt) > 0 || AuthenticationTime(v.PolicyComplete.ObservedAt, v.ObservedAt) > 0 || !v.PolicyBegin.AggregateSha256.Equals(v.PolicyComplete.AggregateSha256) || v.PolicyBegin.Policies.Count != v.PolicyComplete.Policies.Count) return false;
        for (var i = 0; i < v.PolicyBegin.Policies.Count; i++) if (v.PolicyBegin.Policies[i].PolicyId != v.PolicyComplete.Policies[i].PolicyId || !v.PolicyBegin.Policies[i].ProjectionSha256.Equals(v.PolicyComplete.Policies[i].ProjectionSha256)) return false;
        return true;
    }
'''

ts_rules = {
    "authenticationCredential": "if ((value.method === 1) !== (value.publicKeySha256 !== undefined && value.userHandleSha256 !== undefined) || (value.publicKeySha256 !== undefined) !== (value.userHandleSha256 !== undefined) || (value.revision as {value: bigint}).value <= 0n) return false;",
    "authenticationMethod": "if ((value.proof as {case?: string; value?: PasswordFlowBinding}).case === 'password' && (value.proof as {value: PasswordFlowBinding}).value.credential!.method !== 3) return false;",
    "authenticationPassword": "if ((value.credential as AuthenticationCredentialReference).method !== 3) return false;",
    "authenticationNative": "if ((value.nativeFlowRevision as {value: bigint}).value <= 0n) return false;",
    "authenticationPasskey": "if (!authenticationOrigins(value.origins as string[]) || !authenticationEqual(authenticationDigest(value.challenge as Uint8Array), value.challengeSha256 as Uint8Array)) return false;",
    "authenticationOrigins": "if (!authenticationOrigins(value.origins as string[])) return false;",
    "authenticationCompletion": "if (!authenticationCompletion(value as unknown as AuthenticationCompletionCapture)) return false;",
    "authenticationFlow": "if (!authenticationFlow(value as unknown as AuthenticationFlowPayload) || !authenticationWithin(value, () => toBinary(AuthenticationFlowPayloadSchema, value as never), 131072)) return false;",
    "authenticationStepUp": "if (!authenticationStepUp(value as unknown as StepUpMethodProofSnapshot) || !authenticationWithin(value, () => toBinary(StepUpMethodProofSnapshotSchema, value as never), 131072)) return false;",
    "authenticationOperator": "if (!authenticationOperator(value as unknown as OperatorAuthenticationEvidence) || !authenticationWithin(value, () => toBinary(OperatorAuthenticationEvidenceSchema, value as never), 65536)) return false;",
    "authenticationPolicies": "if (!authenticationPolicies(value as unknown as OperatorPolicyObservation)) return false;",
    "authenticationPolicyProjection": "if (!authenticationGuid(value.policyId as string)) return false;",
    "authenticationCustomer": "if ((value.recoveryRevision as {value: bigint}).value <= 0n || (value.completedFlowRevision as {value: bigint}).value <= 0n || (value.tokenExpiresAtSeconds as bigint) <= (value.authenticatedAtSeconds as bigint | undefined ?? 0n) || (value.observedAt as {unixSeconds: bigint}).unixSeconds >= (value.tokenExpiresAtSeconds as bigint) || value.authenticatedAtSeconds !== undefined && (value.authenticatedAtSeconds as bigint) > (value.observedAt as {unixSeconds: bigint}).unixSeconds || !authenticationWithin(value, () => toBinary(CustomerProviderAuthenticationEvidenceSchema, value as never), 65536)) return false;",
}

def ts_imports() -> str:
    return '''import { toBinary } from "@bufbuild/protobuf";
import { AuthenticationFlowPayloadSchema, StepUpMethodProofSnapshotSchema, OperatorAuthenticationEvidenceSchema, CustomerProviderAuthenticationEvidenceSchema } from "../../gen/arcforges/identity/v1/authentication_storage_pb.js";
import type { AuthenticationFlowPayload, AuthenticationCredentialReference, AuthenticationMethodProofBinding, PasswordFlowBinding, AuthenticationCompletionCapture, StepUpMethodProofSnapshot, OperatorAuthenticationEvidence, OperatorPolicyObservation } from "../../gen/arcforges/identity/v1/authentication_storage_pb.js";
'''

TS_HELPERS = r'''
function authenticationWithin(value:unknown,encode:()=>Uint8Array,cap:number):boolean {
  let remaining=cap;const active=new Set<object>();
  const visit=(node:unknown,depth:number):boolean=>{
    if(node===null || typeof node!=='object' || node instanceof Uint8Array)return true;
    if(depth>32 || active.has(node))return false;
    active.add(node);
    try {
      if(Array.isArray(node))return node.every(child=>visit(child,depth+1));
      const object=node as Record<string,unknown>;
      if(!authenticationUnknown(object))return false;
      if(Array.isArray(object.$unknown))for(const field of object.$unknown){remaining-=(field as {data:Uint8Array}).data.length;if(remaining<0)return false;}
      return Object.entries(object).every(([name,child])=>name==='$unknown' || visit(child,depth+1));
    } finally {active.delete(node);}
  };
  try{return visit(value,0) && encode().length<=cap;}catch{return false;}
}
function authenticationUnknown(value: Record<string,unknown>): boolean {
  const fields=value.$unknown;
  if(fields===undefined) return true;
  if(!Array.isArray(fields) || fields.length>4096) return false;
  let total=0;for(const field of fields){ if(typeof field!=='object' || field===null || !('data' in field) || !(field.data instanceof Uint8Array)) return false;total+=field.data.length;if(total>131072)return false; }return true;
}
function authenticationGuid(text: string): boolean { return text !== '00000000-0000-0000-0000-000000000000' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.exec(text)?.[0] === text; }
function authenticationTime(a: {unixSeconds?: bigint | undefined; nanos?: number | undefined}, b: {unixSeconds?: bigint | undefined; nanos?: number | undefined}): number { return a.unixSeconds !== b.unixSeconds ? (a.unixSeconds! < b.unixSeconds! ? -1 : 1) : Math.sign(a.nanos! - b.nanos!); }
function authenticationEqual(a: Uint8Array, b: Uint8Array): boolean { return a.length === b.length && a.every((v,i) => v === b[i]); }
function authenticationCompare(a: Uint8Array, b: Uint8Array): number { for (let i=0;i<a.length;i++) if(a[i]!==b[i]) return a[i]! - b[i]!; return a.length-b.length; }
function authenticationOrigins(values: string[]): boolean {
  let previous: string | undefined;
  const Url=(globalThis as unknown as {URL?: new(value:string)=>{protocol:string;username:string;password:string;pathname:string;search:string;hash:string}}).URL;
  if(Url===undefined)return false;
  for (const value of values) { if(previous !== undefined && previous >= value) return false; try { const u=new Url(value); if(u.protocol!=='https:' || u.username!=='' || u.password!=='' || u.pathname!=='/' || u.search!=='' || u.hash!=='' || value.endsWith('/')) return false; } catch { return false; } previous=value; }
  return previous !== undefined;
}
function authenticationInventory(rows: AuthenticationCredentialReference[], method: number, empty: boolean, actor=false): boolean {
  if(rows.length===0) return empty;
  const selected=actor ? rows[0]!.method! : method;
  if(rows.length>64 || selected!==1 && rows.length!==1) return false;
  let previous: Uint8Array | undefined; const subjects=new Set<string>();
  for(const row of rows) { const id=row.identityId!.value!; const subject=row.providerKey+':'+Array.from(row.subjectSha256!, x=>x.toString(16).padStart(2,'0')).join('');
    if(row.method!==selected || row.revision!.value!<=0n || previous!==undefined && authenticationCompare(previous,id)>=0 || subjects.has(subject)) return false;
    previous=id;subjects.add(subject);
  } return true;
}
function authenticationMethod(proof: AuthenticationMethodProofBinding, method: number, enrollment: boolean, anonymous: boolean): boolean {
  const selected=proof.proof;
  const names=['','passkey','email','password','oidc'];
  if(enrollment) return selected.case==='enrollment' && selected.value.registration.case===names[method];
  if(selected.case==='enrollment') return false;
  if(selected.case==='passwordDiscovery') return anonymous && method===3;
  return selected.case===names[method] && (selected.case!=='email' || anonymous || (selected.value.addressIdentityRevision?.value ?? 0n)>0n);
}
function authenticationCompletion(v: AuthenticationCompletionCapture): boolean {
  return v.userRevision!.value!>0n && v.recoveryRevision!.value!>0n && (v.deviceId===undefined)===(v.deviceRevision===undefined) && (v.installationId===undefined)===(v.installationRevision===undefined) && (v.deviceRevision===undefined || v.deviceRevision.value!>0n) && (v.installationRevision===undefined || v.installationRevision.value!>0n) && (v.installationId===undefined || v.deviceId!==undefined);
}
function authenticationFlow(v: AuthenticationFlowPayload): boolean {
  const kind=v.flowKind!,method=v.method!,enrollment=v.purpose===2 || kind===6,anonymous=v.userId===undefined;
  if(authenticationTime(v.createdAt!,v.expiresAt!)>=0 || v.recoveryRevision!.value!<=0n || anonymous!==(v.userRevision===undefined) || v.userRevision!==undefined && v.userRevision.value!<=0n) return false;
  if((v.sessionId===undefined)!==(v.sessionRevision===undefined) || v.sessionRevision!==undefined && v.sessionRevision.value!<=0n || (v.deviceId===undefined)!==(v.deviceRevision===undefined) || v.deviceRevision!==undefined && v.deviceRevision.value!<=0n || v.installationRevision!==undefined && (v.installationRevision.value!<=0n || v.installationId===undefined)) return false;
  if([4,5,7].includes(kind) && anonymous || kind===6 && (anonymous || v.initialCredentials.length!==0 || v.recoveryAuthorization===undefined || v.purpose!==4) || kind!==6 && v.recoveryAuthorization!==undefined) return false;
  if(v.recoveryAuthorization!==undefined && v.recoveryAuthorization.revision!.value!<=0n) return false;
  if(kind===4 ? v.sessionId===undefined || v.operationClass===undefined || v.targetPayloadSha256===undefined || v.purpose!==3 : v.operationClass!==undefined) return false;
  const browser=v.origin!==undefined || v.preauthBindingSha256!==undefined || v.csrfSha256!==undefined;
  if(browser && !(v.origin!==undefined && v.preauthBindingSha256!==undefined && v.csrfSha256!==undefined) || kind===2 && !browser || [1,9].includes(kind) && browser) return false;
  if((kind===1)!==(v.nativeBinding!==undefined)) return false;
  const fields=[v.installationPublicKeySha256,v.installationKeyVersion,v.installationProofChallenge,v.installationProofBinding,v.installationPublicKey].filter(x=>x!==undefined).length;
  if(fields!==0 && fields!==5 || [1,9].includes(kind) && (fields!==5 || v.installationId===undefined) || browser && fields!==0 || (v.installationId!==undefined)!==(v.productId!==undefined)) return false;
  if(fields===5 && !authenticationEqual(authenticationDigest(v.installationPublicKey!),v.installationPublicKeySha256!)) return false;
  if(anonymous && v.initialCredentials.length!==0 || !authenticationInventory(v.initialCredentials,method,anonymous || kind===6,enrollment) || !authenticationMethod(v.methodProof!,method,enrollment,anonymous)) return false;
  if(v.methodProof!.proof.case==='password' && (v.initialCredentials.length!==1 || !authenticationReferenceEqual(v.initialCredentials[0]!,v.methodProof!.proof.value.credential!))) return false;
  if(v.completion!==undefined) {
    const c=v.completion;
    if(c.credential!.method!==method || c.authEpoch!==v.authEpoch || c.recoveryGeneration!==v.recoveryGeneration || c.recoveryRevision!.value!==v.recoveryRevision!.value || authenticationTime(c.verifiedAt!,v.createdAt!)<0 || authenticationTime(c.verifiedAt!,v.expiresAt!)>=0) return false;
    if(!enrollment && v.initialCredentials.length!==0 && !v.initialCredentials.some(row=>authenticationReferenceEqual(row,c.credential!)))return false;
    if(v.userId!==undefined && (!authenticationEqual(v.userId.value!,c.userId!.value!) || v.userRevision!.value!==c.userRevision!.value) || v.deviceId!==undefined && (c.deviceId===undefined || !authenticationEqual(v.deviceId.value!,c.deviceId.value!) || v.deviceRevision!.value!==c.deviceRevision!.value) || c.installationId!==undefined && v.installationId!==undefined && !authenticationEqual(v.installationId.value!,c.installationId.value!) || v.installationRevision!==undefined && v.installationRevision.value!==c.installationRevision?.value) return false;
  } return true;
}
function authenticationReferenceEqual(a: AuthenticationCredentialReference,b: AuthenticationCredentialReference): boolean { return authenticationEqual(a.identityId!.value!,b.identityId!.value!) && a.revision!.value===b.revision!.value && a.providerKey===b.providerKey && a.method===b.method && authenticationEqual(a.subjectSha256!,b.subjectSha256!) && (a.publicKeySha256===undefined ? b.publicKeySha256===undefined : b.publicKeySha256!==undefined && authenticationEqual(a.publicKeySha256,b.publicKeySha256)) && (a.userHandleSha256===undefined ? b.userHandleSha256===undefined : b.userHandleSha256!==undefined && authenticationEqual(a.userHandleSha256,b.userHandleSha256)); }
function authenticationStepUp(v: StepUpMethodProofSnapshot): boolean { return v.recoveryRevision!.value!>0n && v.userRevision!.value!>0n && v.sessionRevision!.value!>0n && authenticationTime(v.preparedAt!,v.expiresAt!)<0 && authenticationInventory(v.credentials,v.method!,false) && authenticationMethod(v.methodProof!,v.method!,false,false) && (v.methodProof!.proof.case!=='password' || authenticationReferenceEqual(v.credentials[0]!,v.methodProof!.proof.value.credential!)) && (v.methodProof!.proof.case!=='passkey' || authenticationEqual(v.methodProof!.proof.value.challengeSha256!,v.proofSha256!)); }
function authenticationPolicies(v: OperatorPolicyObservation): boolean { let previous: string | undefined; for(const row of v.policies) { if(previous!==undefined && previous>=row.policyId! || authenticationTime(row.observedAt!,v.observedAt!)>0) return false; previous=row.policyId; } return true; }
function authenticationOperator(v: OperatorAuthenticationEvidence): boolean {
  if(!authenticationGuid(v.tenantId!) || !authenticationGuid(v.clientId!) || !authenticationGuid(v.objectId!) || v.recoveryRevision!.value!<=0n || v.completedFlowRevision!.value!<=0n || v.tokenExpiresAtSeconds!<=v.authenticatedAtSeconds! || v.observedAt!.unixSeconds!>=v.tokenExpiresAtSeconds! || v.authenticatedAtSeconds!>v.observedAt!.unixSeconds!) return false;
  const step=v.purpose===2;
  if([v.operatorSessionId,v.operatorSessionRevision,v.previousEvidenceSha256,v.operatorSubjectSha256,v.previousEvidenceId,v.previousOperatorObjectId,v.previousOperatorSubject].some(x=>step!==(x!==undefined)) || v.operatorSessionRevision!==undefined && v.operatorSessionRevision.value!<=0n) return false;
  if(step && (!authenticationGuid(v.previousOperatorObjectId!) || v.previousOperatorObjectId!==v.objectId || v.previousOperatorSubject!==v.pairwiseSubject)) return false;
  if(authenticationTime(v.policyBegin!.observedAt!,v.policyComplete!.observedAt!)>0 || authenticationTime(v.policyComplete!.observedAt!,v.observedAt!)>0 || !authenticationEqual(v.policyBegin!.aggregateSha256!,v.policyComplete!.aggregateSha256!) || v.policyBegin!.policies.length!==v.policyComplete!.policies.length) return false;
  return v.policyBegin!.policies.every((p,i)=>p.policyId===v.policyComplete!.policies[i]!.policyId && authenticationEqual(p.projectionSha256!,v.policyComplete!.policies[i]!.projectionSha256!));
}
// Bounded SHA256 for public32/91-byte profile consistency checks. It is not an identity proof.
function authenticationDigest(input: Uint8Array): Uint8Array {
  if(input.length>128) throw new RangeError('Bounded authentication profile digest');
  const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const padded=new Uint8Array(Math.ceil((input.length+9)/64)*64);padded.set(input);padded[input.length]=128;const d=new DataView(padded.buffer);d.setUint32(padded.length-4,input.length*8,false);
  const r=(v:number,n:number)=>(v>>>n)|(v<<(32-n));const w=new Uint32Array(64);
  for(let offset=0;offset<padded.length;offset+=64){for(let i=0;i<16;i++)w[i]=d.getUint32(offset+i*4,false);for(let i=16;i<64;i++){const a=w[i-15]!,b=w[i-2]!;w[i]=(w[i-16]!+(r(a,7)^r(a,18)^(a>>>3))+w[i-7]!+(r(b,17)^r(b,19)^(b>>>10)))>>>0;}
    let [a,b,c,e,f,g,j,l]=h as [number,number,number,number,number,number,number,number];for(let i=0;i<64;i++){const t=(l+(r(f,6)^r(f,11)^r(f,25))+((f&g)^(~f&j))+k[i]!+w[i]!)>>>0;const u=((r(a,2)^r(a,13)^r(a,22))+((a&b)^(a&c)^(b&c)))>>>0;l=j;j=g;g=f;f=(e+t)>>>0;e=c;c=b;b=a;a=(t+u)>>>0;}const v=[a,b,c,e,f,g,j,l];for(let i=0;i<8;i++)h[i]=(h[i]!+v[i]!)>>>0;}
  const out=new Uint8Array(32);const view=new DataView(out.buffer);h.forEach((v,i)=>view.setUint32(i*4,v,false));padded.fill(0);w.fill(0);return out;
}
'''

CS_POLICY_HELPERS = r'''
    private static bool OperatorProviderPolicy(global::System.Text.Json.JsonElement value)
    {
        foreach (var name in new[] { "realmId", "tenantId", "clientId", "accessApplicationId" }) if (value.GetProperty(name).GetString() == "00000000-0000-0000-0000-000000000000") return false;
        string? previous = null;
        foreach (var id in value.GetProperty("policyIds").EnumerateArray()) { var text = id.GetString()!; if (text == "00000000-0000-0000-0000-000000000000" || previous is not null && global::System.StringComparer.Ordinal.Compare(previous, text) >= 0) return false; previous = text; }
        foreach (var name in new[] { "issuer", "operatorOrigin" }) { var text = value.GetProperty(name).GetString()!; if (!global::System.Uri.TryCreate(text, global::System.UriKind.Absolute, out var uri) || uri.Scheme != "https" || uri.UserInfo.Length != 0 || uri.Fragment.Length != 0 || uri.Query.Length != 0) return false; if (name == "operatorOrigin" && (uri.AbsolutePath != "/" || text.EndsWith('/'))) return false; }
        return OperatorPolicyInstant(value.GetProperty("capturedAt").GetString()!, out var start) && OperatorPolicyInstant(value.GetProperty("notAfter").GetString()!, out var end) && end > start;
    }
    private static bool OperatorPolicyInstant(string text, out global::System.Numerics.BigInteger nanos)
    {
        nanos = 0;
        if (!global::System.DateTimeOffset.TryParseExact(text[..19] + "Z", "yyyy-MM-dd'T'HH:mm:ss'Z'", global::System.Globalization.CultureInfo.InvariantCulture, global::System.Globalization.DateTimeStyles.AssumeUniversal | global::System.Globalization.DateTimeStyles.AdjustToUniversal, out var time)) return false;
        var fraction = text.Length == 20 ? "0" : text[20..^1].PadRight(9, '0');
        nanos = (global::System.Numerics.BigInteger)time.ToUnixTimeSeconds() * 1000000000 + global::System.Int32.Parse(fraction, global::System.Globalization.CultureInfo.InvariantCulture);
        return true;
    }
'''
TS_POLICY_HELPERS = r'''
function operatorProviderPolicy(value: unknown): boolean {
  const v=value as {realmId:string;tenantId:string;clientId:string;accessApplicationId:string;policyIds:string[];issuer:string;operatorOrigin:string;capturedAt:string;notAfter:string};
  if([v.realmId,v.tenantId,v.clientId,v.accessApplicationId,...v.policyIds].some(x=>x==='00000000-0000-0000-0000-000000000000')) return false;
  if(v.policyIds.some((x,i)=>i>0 && v.policyIds[i-1]!>=x)) return false;
  const Url=(globalThis as unknown as {URL?: new(value:string)=>{protocol:string;username:string;password:string;pathname:string;search:string;hash:string}}).URL;if(Url===undefined)return false;
  for(const [name,text] of [['issuer',v.issuer],['operatorOrigin',v.operatorOrigin]]){try{const u=new Url(text!);if(u.protocol!=='https:' || u.username!=='' || u.password!=='' || u.search!=='' || u.hash!=='' || name==='operatorOrigin' && (u.pathname!=='/' || text!.endsWith('/')))return false;}catch{return false;}}
  const start=operatorPolicyInstant(v.capturedAt),end=operatorPolicyInstant(v.notAfter);return start!==undefined && end!==undefined && end>start;
}
function operatorPolicyInstant(text: string): bigint | undefined {
  const base=text.slice(0,19)+'Z';const seconds=Date.parse(base);
  if(text.slice(0,4)==='0000' || !Number.isFinite(seconds) || new Date(seconds).toISOString().slice(0,19)+'Z'!==base)return undefined;
  return BigInt(seconds)*1000000n+BigInt(text.length===20?'0':text.slice(20,-1).padEnd(9,'0'));
}
'''
