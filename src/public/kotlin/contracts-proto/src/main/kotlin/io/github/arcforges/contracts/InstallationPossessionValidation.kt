// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.contracts

import io.github.arcforges.contracts.publicapi.v1.AuthChallenge
import io.github.arcforges.contracts.publicapi.v1.InstallationClaim
import io.github.arcforges.contracts.publicapi.v1.InstallationPossessionProof
import io.github.arcforges.contracts.publicapi.v1.NativeSession
import java.math.BigInteger

/** Bounded shape checks for the new adjunct only. No signature, owner or session authority is granted. */
object InstallationPossessionValidation {
    private val prefix = byteArrayOf(0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2a, 0x86.toByte(),
        0x48, 0xce.toByte(), 0x3d, 0x02, 0x01, 0x06, 0x08, 0x2a, 0x86.toByte(), 0x48,
        0xce.toByte(), 0x3d, 0x03, 0x01, 0x07, 0x03, 0x42, 0x00, 0x04)
    private val prime = BigInteger("ffffffff00000001000000000000000000000000ffffffffffffffffffffffff", 16)
    private val coefficient = BigInteger("5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b", 16)

    /** Exact canonical P-256 DER-SPKI with an actual finite point on the configured curve. */
    fun isPublicKey(bytes: ByteArray): Boolean {
        if (bytes.size != 91 || prefix.indices.any { bytes[it] != prefix[it] }) return false
        val x = BigInteger(1, bytes.copyOfRange(27, 59))
        val y = BigInteger(1, bytes.copyOfRange(59, 91))
        return x < prime && y < prime &&
            y.multiply(y).subtract(x.multiply(x).multiply(x).subtract(x.multiply(BigInteger.valueOf(3))).add(coefficient)).mod(prime) == BigInteger.ZERO
    }

    /** Absence remains decodable for original non-native flows; native owners require their captured key. */
    fun isInstallationAdjunct(value: InstallationClaim): Boolean =
        value.hasPublicKey() == value.hasKeyVersion() && (!value.hasPublicKey() ||
            value.keyVersion > 0 && value.publicKey.size() == 91 && isPublicKey(value.publicKey.toByteArray()))

    /** A challenge tuple is either absent or entirely present with exact widths and a supported version. */
    fun isChallengeAdjunct(value: AuthChallenge): Boolean =
        value.hasInstallationProofChallenge() == value.hasInstallationProofBinding() &&
            value.hasInstallationProofChallenge() == value.hasInstallationKeyVersion() &&
            (!value.hasInstallationProofChallenge() || value.installationProofChallenge.size() == 32 &&
                value.installationProofBinding.size() == 32 && value.installationKeyVersion > 0)

    /** P1363 fixed-width proof shape, distinct from DER/WebAuthn. Its signature still requires real verification. */
    fun isProof(value: InstallationPossessionProof): Boolean = value.hasKeyVersion() &&
        value.keyVersion > 0 && value.hasSignature() && value.signature.size() == 64

    /** Genuine issued native sessions carry a refresh context and stable key version. */
    fun isSessionAdjunct(value: NativeSession): Boolean = value.hasInstallationProofContext() &&
        value.installationProofContext.size() == 32 && value.hasInstallationKeyVersion() && value.installationKeyVersion > 0
}
