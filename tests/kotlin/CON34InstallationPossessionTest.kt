// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.contracts.tests

import com.google.protobuf.ByteString
import io.github.arcforges.contracts.InstallationInitialOperation
import io.github.arcforges.contracts.InstallationPossession
import io.github.arcforges.contracts.foundation.v1.Id
import io.github.arcforges.contracts.publicapi.v1.AuthPurpose
import java.io.File
import java.security.MessageDigest

/** Independent exact normative binary/hash vectors. No OS, transport or key custody is simulated. */
object CON34InstallationPossessionTest {
    private fun bytes(hex: String): ByteArray = hex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    private fun hex(value: ByteArray): String = value.joinToString("") { "%02x".format(it.toInt() and 255) }
    private fun id(hex: String): Id = Id.newBuilder().setValue(ByteString.copyFrom(bytes(hex))).build()
    private const val command = "00112233445566778899aabbccddeeff"
    private const val challenge = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    private const val binding = "202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f"
    private const val context = "606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f"
    private const val token = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
    private const val refreshData = "617263666f726765732e696e7374616c6c6174696f6e2d726566726573682d706f7373657373696f6e2e763100000000176964656e746974792e7265667265736853657373696f6e00112233445566778899aabbccddeeff606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd"
    private val initialData = arrayOf("617263666f726765732e696e7374616c6c6174696f6e2d706f7373657373696f6e2e7631000000001f6964656e746974792e636f6d706c65746541757468656e7469636174696f6e00112233445566778899aabbccddeeff000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f","617263666f726765732e696e7374616c6c6174696f6e2d706f7373657373696f6e2e763100000000186964656e746974792e72656465656d456d61696c436f646500112233445566778899aabbccddeeff000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f","617263666f726765732e696e7374616c6c6174696f6e2d706f7373657373696f6e2e7631000000001b6964656e746974792e636f6d706c657465456e726f6c6c6d656e7400112233445566778899aabbccddeeff000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f","617263666f726765732e696e7374616c6c6174696f6e2d706f7373657373696f6e2e7631000000000c6e61746976652e746f6b656e00112233445566778899aabbccddeeff000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f")
    private const val nativeHash = "5b6d34bf83ea79fcc9b890adbc1e9c4b04d4e41b3966103a6f21be71c917975a"
    private const val directHash = "8ac24b1c284590d3ec599f48ab4f21c74583d9e4ca76aeead90cae96cba9dd73"
    private const val contextHash = "a6cd9c5629d1c230f68d8ab8181f21a8af4d6127b2f53bde9829d2d2151c5f99"
    private fun flow(direct: Boolean = false, platform: String = "windows", redirect: String? = null,
        revision: Long = 1, keyVersion: Long = Long.MAX_VALUE, pkce: ByteArray? = null,
        state: ByteArray? = null, expires: Long = 253402300799999999L, purpose: AuthPurpose = AuthPurpose.AUTH_PURPOSE_AUTHENTICATE): ByteArray? {
        return InstallationPossession.tryFlowBindingHash(id("01010101010101010101010101010101"),id("02020202020202020202020202020202"),
            id("03030303030303030303030303030303"),if(direct) "companion" else "arcscope",if(direct) "android" else platform,
            bytes("808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f"),if(direct) 1 else keyVersion,if(direct) AuthPurpose.AUTH_PURPOSE_ENROLL else purpose,
            if(direct) 1 else 9007199254740993L,0,revision,if(direct) "" else "arcscope.desktop",
            redirect ?: if(direct) "" else "arcscope://auth/callback?return=路🔑",
            pkce ?: if(direct) ByteArray(32) else bytes("404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f"),state ?: if(direct) ByteArray(32) else bytes("a0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebf"),if(direct) 1 else expires)
    }
    private fun current(product: String = "arcscope", revision: Long = Long.MAX_VALUE, generation: Long = Long.MAX_VALUE,
        purpose: AuthPurpose = AuthPurpose.AUTH_PURPOSE_CANCEL_DELETION): ByteArray? {
        return InstallationPossession.tryRefreshContextHash(id("01010101010101010101010101010101"),id("04040404040404040404040404040404"),
            id("05050505050505050505050505050505"),id("03030303030303030303030303030303"),id("06060606060606060606060606060606"),
            id("07070707070707070707070707070707"),product,bytes("808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f"),Long.MAX_VALUE,purpose,9007199254740993L,generation,revision,253402300799999999L)
    }
    @JvmStatic fun main(args: Array<String>) {
        val fixture=File(args.single()).readText(Charsets.UTF_8)
        for(expected in initialData+arrayOf(refreshData,nativeHash,directHash,contextHash))check(fixture.contains(expected))
        InstallationInitialOperation.entries.forEachIndexed { index, operation ->
            check(hex(InstallationPossession.tryInitialSigningData(operation,id(command),bytes(challenge),bytes(binding))!!)==initialData[index])
        }
        check(hex(InstallationPossession.tryRefreshSigningData(id(command),bytes(context),token)!!)==refreshData)
        check(hex(flow()!!)==nativeHash);check(hex(flow(direct=true)!!)==directHash);check(hex(current()!!)==contextHash)
        check(flow(platform="windows\n")==null);check(flow(redirect="arcscope://\uD800")==null)
        check(flow(revision=0)==null);check(flow(keyVersion=0)==null);check(flow(expires=253402300800000000L)==null)
        check(flow(purpose=AuthPurpose.AUTH_PURPOSE_UNSPECIFIED)==null);check(flow(purpose=AuthPurpose.UNRECOGNIZED)==null)
        check(flow(direct=true,pkce=bytes(challenge))==null);check(flow(direct=true,state=bytes(binding))==null)
        check(current(product="other")==null);check(current(revision=0)==null);check(current(generation=-1)==null)
        check(current(purpose=AuthPurpose.UNRECOGNIZED)==null)
        check(InstallationPossession.tryInitialSigningData(null,id(command),bytes(challenge),bytes(binding))==null)
        check(InstallationPossession.tryInitialSigningData(InstallationInitialOperation.NativeToken,id("00".repeat(16)),bytes(challenge),bytes(binding))==null)
        check(InstallationPossession.tryInitialSigningData(InstallationInitialOperation.NativeToken,id(command),ByteArray(31),bytes(binding))==null)
        val alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        val alias=token.dropLast(1)+alphabet[alphabet.indexOf(token.last())+1]
        for(invalid in arrayOf("",token+"=",token+"\n",token.drop(1),"+"+token.drop(1),alias))
            check(InstallationPossession.tryRefreshSigningData(id(command),bytes(context),invalid)==null)
        val mutableChallenge=bytes(challenge);val mutableBinding=bytes(binding)
        val captured=InstallationPossession.tryInitialSigningData(InstallationInitialOperation.CompleteAuthentication,id(command),mutableChallenge,mutableBinding)!!
        mutableChallenge.fill(0);mutableBinding.fill(0);check(hex(captured)==initialData[0])
        check(MessageDigest.getInstance("SHA-256").digest(captured).size==32)
        println(initialData.size)
    }
}
