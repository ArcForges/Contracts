// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.protobuf.Descriptors.FileDescriptor
import io.github.arcforges.contracts.fixtures.ContractFixtures

internal object Con24ScopeLibraryCases {
    private val expectedIds = listOf(
        "projects-use-project-metadata-and-visible-live-sessions-in-one-snapshot",
        "projects-order-equal-commit-times-by-project-id-descending",
        "sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate",
        "sessions-missing-or-hidden-project-returns-not-found",
        "sessions-next-page-rechecks-current-access",
        "get-session-returns-only-committed-metadata-with-cloud-revision-and-time",
        "get-session-unresolved-parent-is-not-reassigned-or-exposed",
        "get-session-tombstone-returns-gone",
    )

    fun run() {
        val fixture = ContractFixtures::class.java.getResourceAsStream("/arcforges/fixtures/con-24-scope-library.json")
            ?.bufferedReader(Charsets.UTF_8)?.use { JsonParser.parseReader(it).asJsonObject }
            ?: error("CON.24 public fixture is missing from the published contract-fixtures archive")
        check(fixture["evidenceClass"].asString == "offline-contract-only-no-owner-service-or-live-workspace")
        val auth = fixture.getAsJsonObject("authorization")
        check(auth["scope"].asString == "product-owner")
        check(auth["risk"].asString == "R1")
        check(auth["idempotency"].asString == "Q")
        check(auth["compatibility"].asString == "AO")
        check(auth["capability"].isJsonNull && auth["approval"].asString == "none")
        check(!auth["stepUp"].asBoolean && !auth["localPresence"].asBoolean)
        check(auth["egress"].asString == "none" && !auth["patEligible"].asBoolean)
        check(auth.getAsJsonArray("actorKinds").map { it.asString } == listOf("human"))

        val descriptorType = Class.forName("io.github.arcforges.contracts.publicapi.v1.ScopeProto")
        val file = descriptorType.getMethod("getDescriptor").invoke(null) as FileDescriptor
        val service = checkNotNull(file.findServiceByName("ScopeService"))
        check(service.fullName == "arcforges.publicapi.v1.ScopeService")
        check(service.methods.map { it.name } == listOf("ListProjects", "ListSessions", "GetSession"))
        for (method in service.methods) {
            check(!method.isClientStreaming && !method.isServerStreaming)
            check(method.inputType.findFieldByNumber(1)?.messageType?.fullName == "arcforges.foundation.v1.RequestMeta")
            check(method.outputType.findFieldByNumber(1)?.messageType?.fullName == "arcforges.foundation.v1.ResponseMeta")
            check(method.inputType.fields.all { it.number == 1 || it.number >= 10 })
            check(method.outputType.fields.map { it.number }.filter { it >= 2 } == listOf(2, 3, 4))
            check(method.outputType.fields.filter { it.number >= 2 }.all { it.containingOneof?.name == "outcome" })
            check(method.outputType.findFieldByNumber(4)?.messageType?.fullName == "arcforges.foundation.v1.EncodedBodyRef")
        }
        val operationSpecs = fixture.getAsJsonArray("operations").map { it.asJsonObject }
        check(operationSpecs.size == 3)
        check(operationSpecs.map { it["rpc"].asString } == listOf(
            "ScopeService/ListProjects", "ScopeService/ListSessions", "ScopeService/GetSession",
        ))
        for (operation in operationSpecs) {
            val methodName = operation["rpc"].asString.substringAfter('/')
            val method = checkNotNull(service.findMethodByName(methodName))
            check(method.inputType.name == operation["requestType"].asString)
            check(method.inputType.fields.map { it.jsonName } == operation.getAsJsonArray("requestFields").map { it.asString })
            val value = checkNotNull(method.outputType.findFieldByNumber(2)?.messageType)
            check(value.name == operation["valueType"].asString)
            check(value.fields.filter { it.number >= 10 }.sortedBy { it.number }.map { it.jsonName } ==
                operation.getAsJsonArray("valueFields").map { it.asString })
            check(method.outputType.name == operation["responseType"].asString)
            check(method.outputType.fields.filter { it.number >= 2 }.sortedBy { it.number }.map { it.jsonName } ==
                operation.getAsJsonArray("outcomeFields").map { it.asString })
        }
        requireFields(service.findMethodByName("ListProjects")!!.inputType, listOf("meta" to 1, "page" to 10))
        requireFields(service.findMethodByName("ListSessions")!!.inputType, listOf("meta" to 1, "projectId" to 10, "page" to 11))
        requireFields(service.findMethodByName("GetSession")!!.inputType, listOf("meta" to 1, "sessionId" to 10, "minRevision" to 11))
        requireFields(service.findMethodByName("ListProjects")!!.outputType.findFieldByNumber(2).messageType, listOf("items" to 10, "page" to 11))
        requireFields(service.findMethodByName("ListSessions")!!.outputType.findFieldByNumber(2).messageType, listOf("items" to 10, "page" to 11))
        requireFields(service.findMethodByName("GetSession")!!.outputType.findFieldByNumber(2).messageType, listOf("session" to 10, "revision" to 11, "committedAt" to 12))
        val projectSummary = checkNotNull(file.findMessageTypeByName("ScopeProjectSummary"))
        val sessionSummary = checkNotNull(file.findMessageTypeByName("ScopeSessionSummary"))
        requireFields(projectSummary, listOf("projectId" to 1, "name" to 2, "sessionCount" to 3, "updatedAt" to 4, "revision" to 5))
        requireFields(sessionSummary, listOf("sessionId" to 1, "projectId" to 2, "name" to 3, "findingCount" to 4, "reportCount" to 5, "tags" to 6, "updatedAt" to 7, "revision" to 8))

        val vectors = fixture.getAsJsonArray("vectors")
        val ids = vectors.map { it.asJsonObject["id"].asString }
        check(ids.size == expectedIds.size && ids.toSet().size == ids.size && ids.toSet() == expectedIds.toSet())
        val consumed = mutableSetOf<String>()
        for (element in vectors) {
            val vector = element.asJsonObject
            val id = vector["id"].asString
            check(consumed.add(id)) { "Duplicate CON.24 vector consumption: $id" }
            when (id) {
                expectedIds[0] -> {
                    check(vector["operationId"].asString == "scope.listProjects")
                    val source = vector.getAsJsonObject("source")
                    val expected = vector.getAsJsonObject("expected")
                    val metadata = source.getAsJsonObject("projectMetadata")
                    check(metadata["projectIdHex"] == expected["projectIdHex"] && metadata["name"] == expected["name"])
                    val visible = source.getAsJsonArray("sessionsInListSnapshot").count {
                        it.asJsonObject["live"].asBoolean && it.asJsonObject["visible"].asBoolean
                    }
                    check(visible == expected["sessionCount"].asInt)
                    check(source["projectRevision"] == expected["revision"])
                    check(source.getAsJsonObject("projectUpdatedAt") == expected.getAsJsonObject("updatedAt"))
                    check(expected.getAsJsonArray("mustNotUse").map { it.asString } == listOf("session.name", "max(session.revision)"))
                }
                expectedIds[1] -> {
                    check(vector["operationId"].asString == "scope.listProjects")
                    check(vector.getAsJsonArray("expectedProjectIdsHex").map { it.asString } == listOf(
                        "00000000000000000000000000000002", "00000000000000000000000000000001",
                    ))
                }
                expectedIds[2] -> {
                    check(vector["operationId"].asString == "scope.listSessions")
                    val sourceRows = vector.getAsJsonObject("source").getAsJsonArray("sessionsInListSnapshot")
                    val visible = sourceRows.map { it.asJsonObject }.filter { it["live"].asBoolean && it["visible"].asBoolean }
                    val expectedItems = vector.getAsJsonArray("expectedItems").map { it.asJsonObject }
                    check(visible.size == 1 && expectedItems.size == 1)
                    for (key in listOf("sessionIdHex", "projectIdHex", "name", "findingCount", "reportCount", "tagsHex", "updatedAt", "revision"))
                        check(visible.single()[key] == expectedItems.single()[key])
                }
                expectedIds[3] -> {
                    check(vector["operationId"].asString == "scope.listSessions")
                    check(!vector.getAsJsonObject("source")["projectVisibleToOwner"].asBoolean)
                    check(vector.getAsJsonObject("expected")["errorCode"].asString == "state.not_found")
                    check(!vector.getAsJsonObject("expected")["itemsExposed"].asBoolean)
                }
                expectedIds[4] -> {
                    check(vector["operationId"].asString == "scope.listSessions")
                    check(vector.getAsJsonObject("source")["accessRevokedAfterPreviousPage"].asBoolean)
                    check(vector.getAsJsonObject("expected")["accessRecheckedOnThisRequest"].asBoolean)
                    check(vector.getAsJsonObject("expected")["priorSnapshotDoesNotRestoreRevokedAccess"].asBoolean)
                }
                expectedIds[5] -> {
                    check(vector["operationId"].asString == "scope.getSession")
                    val expected = vector.getAsJsonObject("expected")
                    check(expected["sessionType"].asString == "ScopeMetadata" && expected["revision"].asInt == 9)
                    check(expected.getAsJsonObject("committedAt")["unixSeconds"].asString == "1790593200")
                    check(expected.getAsJsonObject("committedAt")["nanos"].asInt == 500_000_000)
                    check(!expected["rawCaptureBytesPresent"].asBoolean)
                }
                expectedIds[6] -> {
                    check(vector["operationId"].asString == "scope.getSession")
                    check(!vector.getAsJsonObject("source")["parentProjectResolved"].asBoolean)
                    val expected = vector.getAsJsonObject("expected")
                    check(!expected["visible"].asBoolean && expected["errorCode"].asString == "state.not_found")
                    check(!expected["reassigned"].asBoolean)
                }
                expectedIds[7] -> {
                    check(vector["operationId"].asString == "scope.getSession")
                    check(vector.getAsJsonObject("source")["sessionTombstoned"].asBoolean)
                    val expected = vector.getAsJsonObject("expected")
                    check(!expected["visible"].asBoolean && expected["errorCode"].asString == "state.gone")
                }
                else -> error("Unknown CON.24 vector $id")
            }
        }
        check(consumed == expectedIds.toSet()) { "Every CON.24 vector must be consumed exactly once" }
        println("CON.24: published ScopeService descriptors, product-owner authorization and all eight public vectors passed.")
    }

    private fun requireFields(message: com.google.protobuf.Descriptors.Descriptor, expected: List<Pair<String, Int>>) {
        val actual = message.fields.sortedBy { it.number }.map { it.jsonName to it.number }
        check(actual == expected) { "${message.fullName} fields: $actual" }
    }
}
