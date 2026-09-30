// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.google.protobuf.ByteString
import io.github.arcforges.contracts.foundation.v1.Id
import io.github.arcforges.contracts.foundation.v1.Instant
import io.github.arcforges.contracts.foundation.v1.PageState
import io.github.arcforges.contracts.foundation.v1.Revision
import io.github.arcforges.contracts.publicapi.v1.NotificationView
import io.github.arcforges.contracts.publicapi.v1.PolicyBundle
import io.github.arcforges.contracts.publicapi.v1.SupportCase
import io.github.arcforges.contracts.publicapi.v1.SupportMessage

/** Independent JVM vectors for the exact public support projections and bounds. */
internal object SupportCases {
    private val keyPattern = Regex("^[A-Za-z0-9._:/-]{1,128}$")
    private val caseStates = setOf("open", "inProgress", "awaitingUser", "resolved", "closed")
    private val caseCategories = setOf("support", "bug", "communityReport", "appeal", "security")

    fun run() {
        val id = Id.newBuilder()
            .setValue(ByteString.copyFrom(hex("112233445566478899aabbccddeeff00")))
            .build()
        val now = Instant.newBuilder().setUnixSeconds(1).build()
        val forwardActor = SupportMessage.newBuilder()
            .setMessageId(id)
            .setActorKind("future.owner-kind")
            .setText("Explicit support text.")
            .setCreatedAt(now)
            .build()
        check(validMessage(forwardActor)) { "Forward-compatible actorKind Key was rejected" }
        check(SupportMessage.parseFrom(forwardActor.toByteArray()) == forwardActor) { "SupportMessage binary round-trip changed" }
        check(!validMessage(forwardActor.toBuilder().setActorKind("not valid").build())) { "Invalid actorKind Key was accepted" }
        check(!validMessage(forwardActor.toBuilder().clearText().build())) { "Absent support text was accepted" }
        check(!validMessage(forwardActor.toBuilder().clearCreatedAt().build())) { "Absent support message timestamp was accepted" }
        check(!validMessage(forwardActor.toBuilder().setText("é".repeat(131073)).build())) { "Oversized support text was accepted" }
        check(validMessage(forwardActor.toBuilder().setText("é".repeat(131072)).build())) { "Text at the UTF-8 boundary was rejected" }

        val sample = SupportCase.newBuilder()
            .setCaseId(id)
            .setSubject("😀".repeat(256))
            .setState("open")
            .addMessages(forwardActor)
            .setRevision(Revision.newBuilder().setValue(1).build())
            .setCategory("support")
            .setMessagePage(PageState.newBuilder().setHasMore(false).build())
            .build()
        check(validCase(sample)) { "SupportCase at declared boundaries was rejected" }
        check(SupportCase.parseFrom(sample.toByteArray()) == sample) { "SupportCase binary round-trip changed" }
        check(!validCase(sample.toBuilder().setSubject("😀".repeat(257)).build())) { "Oversized Name was accepted" }
        check(!validCase(sample.toBuilder().clearSubject().build())) { "Absent SupportCase subject was accepted" }
        check(!validCase(sample.toBuilder().clearRevision().build())) { "Absent SupportCase revision was accepted" }
        check(!validCase(sample.toBuilder().setState("futureState").build())) { "Unknown SupportCase state was accepted" }
        check(!validCase(sample.toBuilder().setCategory("futureCategory").build())) { "Unknown SupportCase category was accepted" }
        val tooManyMessages = sample.toBuilder().clearMessages().apply {
            repeat(101) { addMessages(forwardActor) }
        }.build()
        check(!validCase(tooManyMessages)) { "SupportCase message page above 100 was accepted" }

        val notification = NotificationView.newBuilder()
            .setNotificationId(id)
            .setKind("future.notification")
            .setDurability("durable")
            .setMessageKey("future.message-key")
            .setState("unread")
            .setCreatedAt(now)
            .build()
        check(validNotification(notification)) { "Forward-compatible notification Key was rejected" }
        check(NotificationView.parseFrom(notification.toByteArray()) == notification) { "NotificationView binary round-trip changed" }
        check(!validNotification(notification.toBuilder().setKind("bad key").build())) { "Invalid notification Key was accepted" }
        check(!validNotification(notification.toBuilder().clearCreatedAt().build())) { "Absent notification timestamp was accepted" }

        val bundle = PolicyBundle.newBuilder()
            .setVersion("policy.1")
            .setIssuedAt(now)
            .setExpiresAt(Instant.newBuilder().setUnixSeconds(2).build())
            .setBody(ByteString.copyFrom(ByteArray(1048576)))
            .setSignature(ByteString.copyFrom(byteArrayOf(1)))
            .setKeyId("key.1")
            .build()
        check(validBundle(bundle)) { "PolicyBundle body at 1 MiB was rejected" }
        check(PolicyBundle.parseFrom(bundle.toByteArray()) == bundle) { "PolicyBundle binary round-trip changed" }
        check(!validBundle(bundle.toBuilder().clearBody().build())) { "Absent PolicyBundle body was accepted" }
        check(!validBundle(bundle.toBuilder().clearSignature().build())) { "Absent PolicyBundle signature was accepted" }
        check(!validBundle(bundle.toBuilder().clearIssuedAt().build())) { "Absent PolicyBundle issuedAt was accepted" }
        check(!validBundle(bundle.toBuilder().clearExpiresAt().build())) { "Absent PolicyBundle expiresAt was accepted" }
        check(!validBundle(bundle.toBuilder().setBody(ByteString.copyFrom(ByteArray(1048577))).build())) {
            "PolicyBundle body above 1 MiB was accepted"
        }
        println("CON.22 JVM: canonical support projections, forward-compatible Keys and independent boundary vectors passed.")
    }

    private fun validCase(value: SupportCase): Boolean =
        value.caseId.value.size() == 16 &&
            value.hasSubject() &&
            value.subject.codePointCount(0, value.subject.length) <= 256 &&
            value.state in caseStates &&
            value.category in caseCategories &&
            value.hasRevision() &&
            value.messagesCount <= 100 &&
            value.messagesList.all(::validMessage)

    private fun validMessage(value: SupportMessage): Boolean =
        value.messageId.value.size() == 16 &&
            value.hasText() &&
            keyPattern.matches(value.actorKind) &&
            value.hasCreatedAt() &&
            value.text.toByteArray(Charsets.UTF_8).size <= 262144

    private fun validNotification(value: NotificationView): Boolean =
        value.notificationId.value.size() == 16 &&
            keyPattern.matches(value.kind) &&
            keyPattern.matches(value.durability) &&
            keyPattern.matches(value.messageKey) &&
            keyPattern.matches(value.state) &&
            value.hasCreatedAt()

    private fun validBundle(value: PolicyBundle): Boolean =
        value.hasBody() &&
            value.hasSignature() &&
            value.hasIssuedAt() &&
            value.hasExpiresAt() &&
            keyPattern.matches(value.version) &&
            keyPattern.matches(value.keyId) &&
            value.body.size() <= 1048576

    private fun hex(value: String): ByteArray = ByteArray(value.length / 2) { index ->
        value.substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}
