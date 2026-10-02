// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.google.protobuf.ByteString
import io.github.arcforges.contracts.foundation.v1.Id
import io.github.arcforges.contracts.foundation.v1.Instant
import io.github.arcforges.contracts.foundation.v1.Revision
import io.github.arcforges.contracts.publicapi.v1.AuthChallenge
import io.github.arcforges.contracts.publicapi.v1.AuthMethod
import io.github.arcforges.contracts.publicapi.v1.AuthProof
import io.github.arcforges.contracts.publicapi.v1.AuthPurpose
import io.github.arcforges.contracts.publicapi.v1.CredentialReplacement
import io.github.arcforges.contracts.publicapi.v1.AuthProviderView
import io.github.arcforges.contracts.publicapi.v1.DeviceServiceClientInterface
import io.github.arcforges.contracts.publicapi.v1.DeviceServiceSetTrustRequest
import io.github.arcforges.contracts.publicapi.v1.DeviceView
import io.github.arcforges.contracts.publicapi.v1.IdentityServiceBeginAuthenticationRequest
import io.github.arcforges.contracts.publicapi.v1.IdentityServiceBeginRecoveryRequest
import io.github.arcforges.contracts.publicapi.v1.IdentityServiceBeginStepUpRequest
import io.github.arcforges.contracts.publicapi.v1.IdentityServiceClientInterface
import io.github.arcforges.contracts.publicapi.v1.IdentityServiceRequestEmailCodeRequest
import io.github.arcforges.contracts.publicapi.v1.NativeSession
import io.github.arcforges.contracts.publicapi.v1.ProfileUpdate
import io.github.arcforges.contracts.publicapi.v1.ProtectionProfile
import io.github.arcforges.contracts.publicapi.v1.RecoveryMethod
import io.github.arcforges.contracts.publicapi.v1.TrustLevel
import io.github.arcforges.contracts.publicapi.v1.WebAuthnAssertion
import io.github.arcforges.contracts.publicapi.v1.SessionView
import io.github.arcforges.contracts.publicapi.v1.WorkspaceServiceClientInterface
import io.github.arcforges.contracts.publicapi.v1.WorkspaceView

/** Independent JVM vectors for the CON.07 identity, workspace and device surface. */
internal object IdentityCases {
    private val identityMethods = setOf(
        "beginPasskeyRegistration", "completePasskeyRegistration", "beginAuthentication", "completeAuthentication",
        "requestEmailCode", "redeemEmailCode", "refreshSession", "revokeSession", "revokeAllSessions",
        "listAuthIdentities", "removeAuthIdentity", "beginStepUp", "completeStepUp", "beginRecovery",
        "completeRecovery", "requestAccountDeletion", "cancelAccountDeletion", "getProfile", "updateProfile",
        "listAuthProviders", "beginEmailChange", "completeEmailChange", "renameAuthIdentity",
        "generateRecoveryCodes", "listSessions", "listApiTokens", "createApiToken", "revokeApiToken",
        "listSecurityActivity", "getAccountDeletion", "changePassword", "completeEnrollment",
    )
    private val workspaceMethods = setOf(
        "getHealth", "requestDataDeletion", "previewDataDeletion", "getDataDeletion", "list", "get", "updateSettings",
    )
    private val deviceMethods = setOf(
        "signOut", "getRemotePolicy", "setRemotePolicy", "register", "list", "rename", "setTrust", "setRemoteEnabled",
        "revoke", "getCapabilities",
    )

    fun run() {
        check(clientMethods(IdentityServiceClientInterface::class.java) == identityMethods) { "IdentityService client methods changed" }
        check(clientMethods(WorkspaceServiceClientInterface::class.java) == workspaceMethods) { "WorkspaceService client methods changed" }
        check(clientMethods(DeviceServiceClientInterface::class.java) == deviceMethods) { "DeviceService client methods changed" }
        check(identityMethods.size + workspaceMethods.size + deviceMethods.size == 49) { "Exact 49 Registry04 operations" }

        check(AuthMethod.values().filter { it != AuthMethod.UNRECOGNIZED }.map { it.number } == listOf(0, 1, 2, 3, 4)) { "AuthMethod numbers changed" }
        check(AuthPurpose.values().filter { it != AuthPurpose.UNRECOGNIZED }.map { it.number } == listOf(0, 1, 2, 3, 4, 5)) { "AuthPurpose numbers changed" }
        check(RecoveryMethod.values().filter { it != RecoveryMethod.UNRECOGNIZED }.map { it.number } == listOf(0, 1, 2, 3, 4)) { "RecoveryMethod numbers changed" }
        check(TrustLevel.values().filter { it != TrustLevel.UNRECOGNIZED }.map { it.number } == listOf(0, 1, 2, 3)) { "TrustLevel numbers changed" }
        check(ProtectionProfile.values().filter { it != ProtectionProfile.UNRECOGNIZED }.map { it.number } == listOf(0, 1)) { "ProtectionProfile keeps only Standard and reserves 2" }

        // Registry04 required enums outside a oneof carry explicit presence: an absent value is distinguishable from the zero value.
        check(!AuthChallenge.getDefaultInstance().hasPurpose() && AuthChallenge.newBuilder().setPurpose(AuthPurpose.AUTH_PURPOSE_ENROLL).build().hasPurpose()) { "AuthChallenge.purpose lost explicit presence" }
        check(!NativeSession.getDefaultInstance().hasPurpose() && NativeSession.newBuilder().setPurpose(AuthPurpose.AUTH_PURPOSE_ENROLL).build().hasPurpose()) { "NativeSession.purpose lost explicit presence" }
        check(!SessionView.getDefaultInstance().hasPurpose() && SessionView.newBuilder().setPurpose(AuthPurpose.AUTH_PURPOSE_ENROLL).build().hasPurpose()) { "SessionView.purpose lost explicit presence" }
        check(!AuthProviderView.getDefaultInstance().hasMethod() && AuthProviderView.newBuilder().setMethod(AuthMethod.AUTH_METHOD_OIDC).build().hasMethod()) { "AuthProviderView.method lost explicit presence" }
        check(!WorkspaceView.getDefaultInstance().hasProtection() && WorkspaceView.newBuilder().setProtection(ProtectionProfile.PROTECTION_PROFILE_STANDARD).build().hasProtection()) { "WorkspaceView.protection lost explicit presence" }
        check(!DeviceView.getDefaultInstance().hasTrust() && DeviceView.newBuilder().setTrust(TrustLevel.TRUST_LEVEL_TRUSTED).build().hasTrust()) { "DeviceView.trust lost explicit presence" }
        check(!IdentityServiceBeginAuthenticationRequest.getDefaultInstance().hasMethod() && !IdentityServiceBeginAuthenticationRequest.getDefaultInstance().hasPurpose() &&
            IdentityServiceBeginAuthenticationRequest.newBuilder().setMethod(AuthMethod.AUTH_METHOD_EMAIL).setPurpose(AuthPurpose.AUTH_PURPOSE_ENROLL).build().let { it.hasMethod() && it.hasPurpose() }) {
            "BeginAuthentication request method and purpose lost explicit presence"
        }
        check(!IdentityServiceRequestEmailCodeRequest.getDefaultInstance().hasPurpose() && IdentityServiceRequestEmailCodeRequest.newBuilder().setPurpose(AuthPurpose.AUTH_PURPOSE_ENROLL).build().hasPurpose()) { "RequestEmailCode request purpose lost explicit presence" }
        check(!IdentityServiceBeginStepUpRequest.getDefaultInstance().hasMethod() && IdentityServiceBeginStepUpRequest.newBuilder().setMethod(AuthMethod.AUTH_METHOD_PASSKEY).build().hasMethod()) { "BeginStepUp request method lost explicit presence" }
        check(!IdentityServiceBeginRecoveryRequest.getDefaultInstance().hasMethod() && IdentityServiceBeginRecoveryRequest.newBuilder().setMethod(RecoveryMethod.RECOVERY_METHOD_EMAIL_CODE).build().hasMethod()) { "BeginRecovery request method lost explicit presence" }
        check(!DeviceServiceSetTrustRequest.getDefaultInstance().hasTrust() && DeviceServiceSetTrustRequest.newBuilder().setTrust(TrustLevel.TRUST_LEVEL_TRUSTED).build().hasTrust()) { "SetTrust request trust lost explicit presence" }

        val passkey = WebAuthnAssertion.newBuilder()
            .setCredentialId(ByteString.copyFromUtf8("credential"))
            .setClientDataJson(ByteString.copyFromUtf8("{}"))
            .setAuthenticatorData(ByteString.copyFromUtf8("data"))
            .setSignature(ByteString.copyFromUtf8("signature"))
            .build()
        val proofs = listOf(
            AuthProof.newBuilder().setPasskey(passkey).build() to AuthProof.ProofCase.PASSKEY,
            AuthProof.newBuilder().setEmailCode("123456").build() to AuthProof.ProofCase.EMAIL_CODE,
            AuthProof.newBuilder().setRecoveryCode("recovery").build() to AuthProof.ProofCase.RECOVERY_CODE,
            AuthProof.newBuilder().setPassword("correct horse battery staple").build() to AuthProof.ProofCase.PASSWORD,
            AuthProof.newBuilder().setProviderReceipt("receipt").build() to AuthProof.ProofCase.PROVIDER_RECEIPT,
            AuthProof.newBuilder().setAdminGrant("grant").build() to AuthProof.ProofCase.ADMIN_GRANT,
        )
        for ((proof, expectedCase) in proofs) {
            check(proof.proofCase == expectedCase) { "AuthProof variant $expectedCase was not retained" }
            check(AuthProof.parseFrom(proof.toByteArray()) == proof) { "AuthProof binary round-trip changed" }
        }
        val replaced = AuthProof.newBuilder().setEmailCode("1").setPassword("2").build()
        check(replaced.proofCase == AuthProof.ProofCase.PASSWORD && replaced.emailCode.isEmpty()) { "A second AuthProof variant must replace the first, never coexist" }
        check(AuthProof.getDefaultInstance().proofCase == AuthProof.ProofCase.PROOF_NOT_SET) { "An absent proof is representable only as not set" }

        check(validReplacementPassword("😀".repeat(15))) { "Password of 15 scalars was rejected" }
        check(!validReplacementPassword("😀".repeat(14))) { "Password of 14 scalars was accepted" }
        check(!validReplacementPassword("a".repeat(129))) { "Password of 129 scalars was accepted" }
        check(CredentialReplacement.newBuilder().setPassword("p".repeat(15)).build().replacementCase == CredentialReplacement.ReplacementCase.PASSWORD) {
            "CredentialReplacement password variant was not retained"
        }

        val id = Id.newBuilder().setValue(ByteString.copyFrom(hex("112233445566478899aabbccddeeff00"))).build()
        val now = Instant.newBuilder().setUnixSeconds(1).build()
        val challenge = AuthChallenge.newBuilder()
            .setFlowId(id)
            .setChallenge(ByteString.copyFrom(ByteArray(32)))
            .setExpiresAt(now)
            .setPurpose(AuthPurpose.AUTH_PURPOSE_RECOVER)
            .setRecoveryMethod(RecoveryMethod.RECOVERY_METHOD_EMAIL_CODE)
            .build()
        check(validChallenge(challenge)) { "Recovery challenge with recoveryMethod was rejected" }
        check(!validChallenge(challenge.toBuilder().setMethod(AuthMethod.AUTH_METHOD_EMAIL).build())) { "Recovery challenge carrying method was accepted" }
        check(!validChallenge(challenge.toBuilder().clearRecoveryMethod().build())) { "Recovery challenge without recoveryMethod was accepted" }
        val authenticate = challenge.toBuilder().setPurpose(AuthPurpose.AUTH_PURPOSE_AUTHENTICATE).clearRecoveryMethod().setMethod(AuthMethod.AUTH_METHOD_PASSKEY).build()
        check(validChallenge(authenticate)) { "Authenticate challenge with method was rejected" }
        check(!validChallenge(authenticate.toBuilder().setRecoveryMethod(RecoveryMethod.RECOVERY_METHOD_PASSKEY).build())) { "Authenticate challenge carrying recoveryMethod was accepted" }
        check(!validChallenge(authenticate.toBuilder().setChallenge(ByteString.copyFrom(ByteArray(33))).build())) { "33-byte challenge was accepted" }

        val device = DeviceView.newBuilder()
            .setDeviceId(id)
            .setName("Workstation")
            .setPlatform("windows")
            .setTrust(TrustLevel.TRUST_LEVEL_TRUSTED)
            .setRemoteEnabled(false)
            .setRevision(Revision.newBuilder().setValue(1).build())
            .build()
        val session = NativeSession.newBuilder()
            .setSessionId(id)
            .setAccessToken("access")
            .setAccessExpiresAt(now)
            .setRefreshToken("refresh")
            .setRefreshExpiresAt(now)
            .setDevice(device)
            .setRecoveryGeneration(1)
            .setPurpose(AuthPurpose.AUTH_PURPOSE_AUTHENTICATE)
            .build()
        check(NativeSession.parseFrom(session.toByteArray()) == session) { "NativeSession binary round-trip changed" }
        check(!NativeSession.newBuilder(session).clearRefreshToken().build().hasRefreshToken()) { "Absent refresh token must stay absent" }

        val cleared = ProfileUpdate.newBuilder().setClearAvatar(true).build()
        check(cleared.changeCase == ProfileUpdate.ChangeCase.CLEAR_AVATAR && cleared.clearAvatar) { "clearAvatar variant was not retained" }
        check(ProfileUpdate.parseFrom(cleared.toByteArray()) == cleared) { "ProfileUpdate binary round-trip changed" }
        check(ProfileUpdate.getDefaultInstance().changeCase == ProfileUpdate.ChangeCase.CHANGE_NOT_SET) { "An unchanged avatar is the unset oneof" }
        println("CON.07 JVM: 49 client operations, oneof proofs, recovery challenge rules and independent boundary vectors passed.")
    }

    private fun clientMethods(type: Class<*>): Set<String> = type.declaredMethods
        .filter { !it.isSynthetic && !it.isBridge }
        .map { it.name }
        .toSet()

    private fun validReplacementPassword(value: String): Boolean = value.codePointCount(0, value.length) in 15..128

    private fun validChallenge(value: AuthChallenge): Boolean =
        value.challenge.size() <= 32 &&
            if (value.purpose == AuthPurpose.AUTH_PURPOSE_RECOVER) value.hasRecoveryMethod() && !value.hasMethod()
            else value.hasMethod() && !value.hasRecoveryMethod()

    private fun hex(value: String): ByteArray = ByteArray(value.length / 2) { index ->
        value.substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}
