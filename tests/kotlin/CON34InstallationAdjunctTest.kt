// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.contracts.tests

import com.google.protobuf.ByteString
import io.github.arcforges.contracts.InstallationPossessionValidation as V
import io.github.arcforges.contracts.publicapi.v1.AuthChallenge
import io.github.arcforges.contracts.publicapi.v1.InstallationClaim
import io.github.arcforges.contracts.publicapi.v1.InstallationPossessionProof
import io.github.arcforges.contracts.publicapi.v1.NativeSession

object CON34InstallationAdjunctTest {
    private fun bytes(hex: String) = hex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    @JvmStatic fun main(args: Array<String>) {
        check(args.isEmpty())
        // Independently fixed SEC2 P-256 generator point in canonical DER-SPKI.
        val key = bytes("3059301306072a8648ce3d020106082a8648ce3d03010703420004" +
            "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296" +
            "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5")
        check(V.isPublicKey(key))
        val wrong = key.clone(); wrong[90] = (wrong[90].toInt() xor 1).toByte()
        check(!V.isPublicKey(wrong))
        check(!V.isPublicKey(key + byteArrayOf(0)))
        val claim = InstallationClaim.newBuilder().setPublicKey(ByteString.copyFrom(key)).setKeyVersion(Long.MAX_VALUE).build()
        check(V.isInstallationAdjunct(InstallationClaim.parseFrom(claim.toByteArray())))
        check(V.isInstallationAdjunct(InstallationClaim.getDefaultInstance()))
        check(!V.isInstallationAdjunct(claim.toBuilder().clearKeyVersion().build()))
        check(!V.isInstallationAdjunct(claim.toBuilder().setKeyVersion(Long.MIN_VALUE).build()))
        check(!V.isInstallationAdjunct(claim.toBuilder().setPublicKey(ByteString.copyFrom(wrong)).build()))
        val hash = ByteString.copyFrom(ByteArray(32) { it.toByte() })
        val challenge = AuthChallenge.newBuilder().setInstallationProofChallenge(hash).setInstallationProofBinding(hash).setInstallationKeyVersion(1).build()
        check(V.isChallengeAdjunct(AuthChallenge.parseFrom(challenge.toByteArray())))
        check(V.isChallengeAdjunct(AuthChallenge.getDefaultInstance()))
        check(!V.isChallengeAdjunct(challenge.toBuilder().clearInstallationProofBinding().build()))
        check(!V.isChallengeAdjunct(challenge.toBuilder().setInstallationKeyVersion(0).build()))
        val proof = InstallationPossessionProof.newBuilder().setKeyVersion(1).setSignature(ByteString.copyFrom(ByteArray(64))).build()
        check(V.isProof(InstallationPossessionProof.parseFrom(proof.toByteArray())))
        check(!V.isProof(proof.toBuilder().setSignature(ByteString.copyFrom(ByteArray(70))).build()))
        check(!V.isProof(proof.toBuilder().clearKeyVersion().build()))
        val session = NativeSession.newBuilder().setInstallationProofContext(hash).setInstallationKeyVersion(1).build()
        check(V.isSessionAdjunct(NativeSession.parseFrom(session.toByteArray())))
        check(!V.isSessionAdjunct(NativeSession.getDefaultInstance()))
        check(!V.isSessionAdjunct(session.toBuilder().setInstallationProofContext(ByteString.copyFrom(ByteArray(31))).build()))
        println("CON.34 actual Kotlin installation DER/tuple/P1363/UInt64/presence and serializer cases passed")
    }
}
