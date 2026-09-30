// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.protobuf.ByteString
import com.google.protobuf.CodedInputStream
import com.google.protobuf.MessageLite
import com.connectrpc.MethodSpec
import com.connectrpc.ProtocolClientInterface
import com.connectrpc.StreamType
import io.github.arcforges.contracts.fixtures.ContractFixtures
import io.github.arcforges.contracts.foundation.v1.ArcError
import io.github.arcforges.contracts.foundation.v1.EncodedBodyRef
import io.github.arcforges.contracts.foundation.v1.Id
import io.github.arcforges.contracts.foundation.v1.Instant
import io.github.arcforges.contracts.foundation.v1.PageRequest
import io.github.arcforges.contracts.foundation.v1.PageState
import io.github.arcforges.contracts.foundation.v1.RequestMeta
import io.github.arcforges.contracts.foundation.v1.ResponseMeta
import io.github.arcforges.contracts.foundation.v1.Revision
import io.github.arcforges.contracts.publicapi.v1.ScopeMetadata
import io.github.arcforges.contracts.publicapi.v1.ScopeProjectSummary
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceClientInterface
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceGetSessionRequest
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceGetSessionResponse
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceGetSessionValue
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceListProjectsRequest
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceListProjectsResponse
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceListProjectsValue
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceListSessionsRequest
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceListSessionsResponse
import io.github.arcforges.contracts.publicapi.v1.ScopeServiceListSessionsValue
import io.github.arcforges.contracts.publicapi.v1.ScopeSessionSummary
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Modifier
import java.lang.reflect.Proxy
import kotlin.coroutines.Continuation
import kotlin.coroutines.intrinsics.COROUTINE_SUSPENDED
import kotlinx.coroutines.runBlocking

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
        "projects-order-updated-at-primary-before-project-id",
        "sessions-order-updated-at-then-session-id-descending",
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

        verifyGeneratedSurface(fixture)

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
                    val sourceProjects = vector.getAsJsonObject("source").getAsJsonArray("projects").map { it.asJsonObject }
                    check(sourceProjects.size == 3)
                    val commitTimes = sourceProjects.map { project ->
                        val updatedAt = project.getAsJsonObject("updatedAt")
                        updatedAt["unixSeconds"].asString to updatedAt["nanos"].asInt
                    }.distinct()
                    check(commitTimes.size == 1) { "The ordering vector must use equal commit times" }
                    val derivedVisibleProjectIds = sourceProjects
                        .filter { it["hasVisibleLiveSessions"].asBoolean }
                        .map { it["projectIdHex"].asString }
                        .sortedDescending()
                    val expectedProjectIds = vector.getAsJsonArray("expectedProjectIdsHex").map { it.asString }
                    check(derivedVisibleProjectIds == expectedProjectIds) {
                        "Expected project order must derive from visible source projects"
                    }
                    check(expectedProjectIds == listOf(
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
                expectedIds[8] -> {
                    check(vector["operationId"].asString == "scope.listProjects")
                    val sourceProjects = vector.getAsJsonObject("source").getAsJsonArray("projects").map { it.asJsonObject }
                    check(sourceProjects.size == 3 && sourceProjects.all { it["hasVisibleLiveSessions"].asBoolean })
                    val instants = sourceProjects.map { project ->
                        val updatedAt = project.getAsJsonObject("updatedAt")
                        updatedAt["unixSeconds"].asString to updatedAt["nanos"].asInt
                    }.toSet()
                    check(instants.size == 3)
                    check(instants.map { it.first }.toSet().size == 2) { "The vector must order nanoseconds within one second" }
                    val actual = sourceProjects.sortedWith(
                        compareByDescending<JsonObject> { it.getAsJsonObject("updatedAt")["unixSeconds"].asString.toLong() }
                            .thenByDescending { it.getAsJsonObject("updatedAt")["nanos"].asInt }
                            .thenByDescending { it["projectIdHex"].asString },
                    ).map { it["projectIdHex"].asString }
                    val expected = vector.getAsJsonArray("expectedProjectIdsHex").map { it.asString }
                    check(actual == expected)
                    check(actual == listOf(
                        "00000000000000000000000000000001",
                        "00000000000000000000000000000002",
                        "00000000000000000000000000000003",
                    )) { "updatedAt must sort before projectId" }
                }
                expectedIds[9] -> {
                    check(vector["operationId"].asString == "scope.listSessions")
                    val sourceRows = vector.getAsJsonObject("source").getAsJsonArray("sessionsInListSnapshot")
                        .map { it.asJsonObject }.filter { it["live"].asBoolean && it["visible"].asBoolean }
                    check(sourceRows.size == 4)
                    val timestampKeys = sourceRows.map {
                        val updatedAt = it.getAsJsonObject("updatedAt")
                        updatedAt["unixSeconds"].asString + ":" + updatedAt["nanos"].asInt
                    }
                    check(timestampKeys.toSet().size == 3)
                    check(timestampKeys.count { it == "1790593200:100000000" } == 2) { "The tie pair must share updatedAt" }
                    val actual = sourceRows.sortedWith(
                        compareByDescending<JsonObject> { it.getAsJsonObject("updatedAt")["unixSeconds"].asString.toLong() }
                            .thenByDescending { it.getAsJsonObject("updatedAt")["nanos"].asInt }
                            .thenByDescending { it["sessionIdHex"].asString },
                    ).map { it["sessionIdHex"].asString }
                    val expected = vector.getAsJsonArray("expectedSessionIdsHex").map { it.asString }
                    check(actual == expected)
                    check(actual == listOf(
                        "00000000000000000000000000000001",
                        "00000000000000000000000000000004",
                        "00000000000000000000000000000002",
                        "00000000000000000000000000000003",
                    )) { "updatedAt must sort before sessionId, with descending ID for ties" }
                }
                else -> error("Unknown CON.24 vector $id")
            }
        }
        check(consumed == expectedIds.toSet()) { "Every CON.24 vector must be consumed exactly once" }
        println("CON.24: published ScopeService client and lite messages, product-owner authorization and all ten public vectors passed.")
    }

    private fun verifyGeneratedSurface(fixture: JsonObject) {
        val methods = ScopeServiceClientInterface::class.java.declaredMethods
            .filter { Modifier.isAbstract(it.modifiers) && !it.isSynthetic }
        check(methods.map { it.name }.sorted() == listOf("getSession", "listProjects", "listSessions"))
        val requestTypeNames = listOf(
            "ScopeServiceListProjectsRequest", "ScopeServiceListSessionsRequest", "ScopeServiceGetSessionRequest",
        )
        val requestTypes = mapOf(
            "getSession" to ScopeServiceGetSessionRequest::class.java,
            "listProjects" to ScopeServiceListProjectsRequest::class.java,
            "listSessions" to ScopeServiceListSessionsRequest::class.java,
        )
        check(methods.all { it.parameterTypes.firstOrNull() == requestTypes[it.name] })

        val operations = fixture.getAsJsonArray("operations").map { it.asJsonObject }
        check(operations.size == 3)
        check(operations.map { it["rpc"].asString } == listOf(
            "ScopeService/ListProjects", "ScopeService/ListSessions", "ScopeService/GetSession",
        ))
        val requestFields = listOf(
            listOf("meta", "page"),
            listOf("meta", "projectId", "page"),
            listOf("meta", "sessionId", "minRevision"),
        )
        val valueTypes = listOf(
            "ScopeServiceListProjectsValue", "ScopeServiceListSessionsValue", "ScopeServiceGetSessionValue",
        )
        val responseTypes = listOf(
            "ScopeServiceListProjectsResponse", "ScopeServiceListSessionsResponse", "ScopeServiceGetSessionResponse",
        )
        val valueFields = listOf(listOf("items", "page"), listOf("items", "page"), listOf("session", "revision", "committedAt"))
        for (index in operations.indices) {
            val operation = operations[index]
            check(operation["requestType"].asString == requestTypeNames[index])
            check(operation.getAsJsonArray("requestFields").map { it.asString } == requestFields[index])
            check(operation["valueType"].asString == valueTypes[index])
            check(operation.getAsJsonArray("valueFields").map { it.asString } == valueFields[index])
            check(operation["responseType"].asString == responseTypes[index])
            check(operation.getAsJsonArray("outcomeFields").map { it.asString } == listOf("value", "error", "encodedBody"))
        }

        check(ScopeServiceListProjectsRequest.META_FIELD_NUMBER == 1 && ScopeServiceListProjectsRequest.PAGE_FIELD_NUMBER == 10)
        check(ScopeServiceListSessionsRequest.META_FIELD_NUMBER == 1 && ScopeServiceListSessionsRequest.PROJECT_ID_FIELD_NUMBER == 10 && ScopeServiceListSessionsRequest.PAGE_FIELD_NUMBER == 11)
        check(ScopeServiceGetSessionRequest.META_FIELD_NUMBER == 1 && ScopeServiceGetSessionRequest.SESSION_ID_FIELD_NUMBER == 10 && ScopeServiceGetSessionRequest.MIN_REVISION_FIELD_NUMBER == 11)
        check(ScopeServiceListProjectsResponse.META_FIELD_NUMBER == 1 && ScopeServiceListProjectsResponse.VALUE_FIELD_NUMBER == 2 && ScopeServiceListProjectsResponse.ERROR_FIELD_NUMBER == 3 && ScopeServiceListProjectsResponse.ENCODED_BODY_FIELD_NUMBER == 4)
        check(ScopeServiceListSessionsResponse.META_FIELD_NUMBER == 1 && ScopeServiceListSessionsResponse.VALUE_FIELD_NUMBER == 2 && ScopeServiceListSessionsResponse.ERROR_FIELD_NUMBER == 3 && ScopeServiceListSessionsResponse.ENCODED_BODY_FIELD_NUMBER == 4)
        check(ScopeServiceGetSessionResponse.META_FIELD_NUMBER == 1 && ScopeServiceGetSessionResponse.VALUE_FIELD_NUMBER == 2 && ScopeServiceGetSessionResponse.ERROR_FIELD_NUMBER == 3 && ScopeServiceGetSessionResponse.ENCODED_BODY_FIELD_NUMBER == 4)
        check(ScopeServiceListProjectsValue.ITEMS_FIELD_NUMBER == 10 && ScopeServiceListProjectsValue.PAGE_FIELD_NUMBER == 11)
        check(ScopeServiceListSessionsValue.ITEMS_FIELD_NUMBER == 10 && ScopeServiceListSessionsValue.PAGE_FIELD_NUMBER == 11)
        check(ScopeServiceGetSessionValue.SESSION_FIELD_NUMBER == 10 && ScopeServiceGetSessionValue.REVISION_FIELD_NUMBER == 11 && ScopeServiceGetSessionValue.COMMITTED_AT_FIELD_NUMBER == 12)
        check(ScopeProjectSummary.PROJECT_ID_FIELD_NUMBER == 1 && ScopeProjectSummary.NAME_FIELD_NUMBER == 2 && ScopeProjectSummary.SESSION_COUNT_FIELD_NUMBER == 3 && ScopeProjectSummary.UPDATED_AT_FIELD_NUMBER == 4 && ScopeProjectSummary.REVISION_FIELD_NUMBER == 5)
        check(ScopeSessionSummary.SESSION_ID_FIELD_NUMBER == 1 && ScopeSessionSummary.PROJECT_ID_FIELD_NUMBER == 2 && ScopeSessionSummary.NAME_FIELD_NUMBER == 3 && ScopeSessionSummary.FINDING_COUNT_FIELD_NUMBER == 4 && ScopeSessionSummary.REPORT_COUNT_FIELD_NUMBER == 5 && ScopeSessionSummary.TAGS_FIELD_NUMBER == 6 && ScopeSessionSummary.UPDATED_AT_FIELD_NUMBER == 7 && ScopeSessionSummary.REVISION_FIELD_NUMBER == 8)

        val projectVector = fixture.getAsJsonArray("vectors").map { it.asJsonObject }
            .single { it["id"].asString == "projects-use-project-metadata-and-visible-live-sessions-in-one-snapshot" }
        val projectExpected = projectVector.getAsJsonObject("expected")
        val project = projectSummary(projectExpected)
        check(project.hasProjectId() && project.projectId == id(projectExpected["projectIdHex"].asString))
        check(project.hasName() && project.name == projectExpected["name"].asString)
        check(project.hasSessionCount() && project.sessionCount == projectExpected["sessionCount"].asInt)
        check(project.updatedAt == instant(projectExpected.getAsJsonObject("updatedAt")))
        check(project.revision == revision(projectExpected["revision"].asLong))
        val decodedProject = roundTrip(project, ScopeProjectSummary::parseFrom)

        val sessionsVector = fixture.getAsJsonArray("vectors").map { it.asJsonObject }
            .single { it["id"].asString == "sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate" }
        val expectedItems = sessionsVector.getAsJsonArray("expectedItems").map { it.asJsonObject }
        val sessions = expectedItems.map(::sessionSummary)
        check(sessions.size == 1)
        val expectedSession = expectedItems.single()
        val session = sessions.single()
        check(session.hasSessionId() && session.sessionId == id(expectedSession["sessionIdHex"].asString))
        check(session.hasProjectId() && session.projectId == id(expectedSession["projectIdHex"].asString))
        check(session.hasName() && session.name == expectedSession["name"].asString)
        check(session.hasFindingCount() && session.findingCount == expectedSession["findingCount"].asInt)
        check(session.hasReportCount() && session.reportCount == expectedSession["reportCount"].asInt)
        check(session.tagsList == expectedSession.getAsJsonArray("tagsHex").map { id(it.asString) })
        check(session.updatedAt == instant(expectedSession.getAsJsonObject("updatedAt")))
        check(session.revision == revision(expectedSession["revision"].asLong))
        val decodedSession = roundTrip(session, ScopeSessionSummary::parseFrom)

        val projectsRequest = ScopeServiceListProjectsRequest.newBuilder()
            .setMeta(RequestMeta.getDefaultInstance())
            .setPage(PageRequest.getDefaultInstance())
            .build()
        check(roundTrip(projectsRequest, ScopeServiceListProjectsRequest::parseFrom).hasMeta())
        check(wireTags(projectsRequest) == listOf((1 shl 3) or 2, (10 shl 3) or 2))
        val sessionsRequest = ScopeServiceListSessionsRequest.newBuilder()
            .setMeta(RequestMeta.getDefaultInstance())
            .setProjectId(session.projectId)
            .setPage(PageRequest.getDefaultInstance())
            .build()
        check(roundTrip(sessionsRequest, ScopeServiceListSessionsRequest::parseFrom).projectId == session.projectId)
        check(wireTags(sessionsRequest) == listOf((1 shl 3) or 2, (10 shl 3) or 2, (11 shl 3) or 2))
        val getSessionRequest = ScopeServiceGetSessionRequest.newBuilder()
            .setMeta(RequestMeta.getDefaultInstance())
            .setSessionId(session.sessionId)
            .setMinRevision(session.revision)
            .build()
        check(roundTrip(getSessionRequest, ScopeServiceGetSessionRequest::parseFrom).minRevision == session.revision)
        check(wireTags(getSessionRequest) == listOf((1 shl 3) or 2, (10 shl 3) or 2, (11 shl 3) or 2))

        val capturedMethods = mutableListOf<MethodSpec<*, *>>()
        val protocolClient = Proxy.newProxyInstance(
            ProtocolClientInterface::class.java.classLoader,
            arrayOf(ProtocolClientInterface::class.java),
            InvocationHandler { _, method, arguments ->
                if (method.name != "unary" || arguments == null || arguments.size != 4 || arguments[3] !is Continuation<*>) {
                    throw UnsupportedOperationException("Unexpected Connect client call: ${method.name}")
                }
                capturedMethods.add(arguments[2] as MethodSpec<*, *>)
                @Suppress("UNCHECKED_CAST")
                val continuation = arguments[3] as Continuation<Any?>
                continuation.resumeWith(Result.failure(CapturedMethod()))
                COROUTINE_SUSPENDED
            },
        ) as ProtocolClientInterface
        val client = io.github.arcforges.contracts.publicapi.v1.ScopeServiceClient(protocolClient)
        val rpcCalls: List<suspend () -> Unit> = listOf(
            { client.listProjects(projectsRequest) },
            { client.listSessions(sessionsRequest) },
            { client.getSession(getSessionRequest) },
        )
        for (rpcCall in rpcCalls) {
            try {
                runBlocking { rpcCall() }
                error("Generated Connect call did not reach the recorder")
            } catch (_: CapturedMethod) {
                // The fake protocol client records the generated method specification and stops before I/O.
            }
        }
        check(capturedMethods.map { it.path } == listOf(
            "arcforges.publicapi.v1.ScopeService/ListProjects",
            "arcforges.publicapi.v1.ScopeService/ListSessions",
            "arcforges.publicapi.v1.ScopeService/GetSession",
        ))
        check(capturedMethods.map { it.requestClass.java } == listOf(
            ScopeServiceListProjectsRequest::class.java,
            ScopeServiceListSessionsRequest::class.java,
            ScopeServiceGetSessionRequest::class.java,
        ))
        check(capturedMethods.map { it.responseClass.java } == listOf(
            ScopeServiceListProjectsResponse::class.java,
            ScopeServiceListSessionsResponse::class.java,
            ScopeServiceGetSessionResponse::class.java,
        ))
        check(capturedMethods.all { it.streamType == StreamType.UNARY })

        val projectsResponse = ScopeServiceListProjectsResponse.newBuilder()
            .setMeta(ResponseMeta.getDefaultInstance())
            .setValue(ScopeServiceListProjectsValue.newBuilder().addItems(decodedProject).setPage(PageState.getDefaultInstance()))
            .build()
        val decodedProjectsResponse = roundTrip(projectsResponse, ScopeServiceListProjectsResponse::parseFrom)
        check(decodedProjectsResponse.hasMeta() && decodedProjectsResponse.hasValue())
        check(!decodedProjectsResponse.hasError() && !decodedProjectsResponse.hasEncodedBody())
        check(decodedProjectsResponse.value.itemsList == listOf(decodedProject))

        val sessionsResponse = ScopeServiceListSessionsResponse.newBuilder()
            .setMeta(ResponseMeta.getDefaultInstance())
            .setValue(ScopeServiceListSessionsValue.newBuilder().addItems(decodedSession).setPage(PageState.getDefaultInstance()))
            .build()
        val decodedSessionsResponse = roundTrip(sessionsResponse, ScopeServiceListSessionsResponse::parseFrom)
        check(decodedSessionsResponse.hasMeta() && decodedSessionsResponse.hasValue())
        check(!decodedSessionsResponse.hasError() && !decodedSessionsResponse.hasEncodedBody())
        check(decodedSessionsResponse.value.itemsList == listOf(decodedSession))

        val getSessionValue = ScopeServiceGetSessionValue.newBuilder()
            .setSession(ScopeMetadata.getDefaultInstance())
            .setRevision(session.revision)
            .setCommittedAt(session.updatedAt)
            .build()
        val getSessionResponse = ScopeServiceGetSessionResponse.newBuilder()
            .setMeta(ResponseMeta.getDefaultInstance())
            .setValue(getSessionValue)
            .build()
        val decodedGetSessionResponse = roundTrip(getSessionResponse, ScopeServiceGetSessionResponse::parseFrom)
        check(decodedGetSessionResponse.hasValue() && decodedGetSessionResponse.value.revision == session.revision)
        check(!decodedGetSessionResponse.hasError() && !decodedGetSessionResponse.hasEncodedBody())
        val errorResponse = roundTrip(
            ScopeServiceGetSessionResponse.newBuilder().setError(ArcError.getDefaultInstance()).build(),
            ScopeServiceGetSessionResponse::parseFrom,
        )
        check(errorResponse.hasError() && !errorResponse.hasValue() && !errorResponse.hasEncodedBody())
        val encodedResponse = roundTrip(
            ScopeServiceGetSessionResponse.newBuilder().setEncodedBody(EncodedBodyRef.getDefaultInstance()).build(),
            ScopeServiceGetSessionResponse::parseFrom,
        )
        check(encodedResponse.hasEncodedBody() && !encodedResponse.hasValue() && !encodedResponse.hasError())
    }

    private fun projectSummary(value: JsonObject): ScopeProjectSummary = ScopeProjectSummary.newBuilder()
        .setProjectId(id(value["projectIdHex"].asString))
        .setName(value["name"].asString)
        .setSessionCount(value["sessionCount"].asInt)
        .setUpdatedAt(instant(value.getAsJsonObject("updatedAt")))
        .setRevision(revision(value["revision"].asLong))
        .build()

    private fun sessionSummary(value: JsonObject): ScopeSessionSummary {
        val builder = ScopeSessionSummary.newBuilder()
            .setSessionId(id(value["sessionIdHex"].asString))
            .setProjectId(id(value["projectIdHex"].asString))
            .setName(value["name"].asString)
            .setFindingCount(value["findingCount"].asInt)
            .setReportCount(value["reportCount"].asInt)
            .setUpdatedAt(instant(value.getAsJsonObject("updatedAt")))
            .setRevision(revision(value["revision"].asLong))
        value.getAsJsonArray("tagsHex").forEach { builder.addTags(id(it.asString)) }
        return builder.build()
    }

    private fun id(hex: String): Id {
        check(hex.length == 32 && hex.all { it in "0123456789abcdef" })
        val bytes = hex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        return Id.newBuilder().setValue(ByteString.copyFrom(bytes)).build()
    }

    private fun instant(value: JsonObject): Instant = Instant.newBuilder()
        .setUnixSeconds(value["unixSeconds"].asString.toLong())
        .setNanos(value["nanos"].asInt)
        .build()

    private fun revision(value: Long): Revision = Revision.newBuilder().setValue(value).build()

    private fun <T : MessageLite> roundTrip(message: T, parse: (ByteArray) -> T): T {
        val bytes = message.toByteArray()
        val decoded = parse(bytes)
        check(decoded == message && decoded.toByteArray().contentEquals(bytes))
        return decoded
    }

    private fun wireTags(message: MessageLite): List<Int> {
        val input = CodedInputStream.newInstance(message.toByteArray())
        val tags = mutableListOf<Int>()
        while (true) {
            val tag = input.readTag()
            if (tag == 0) break
            tags.add(tag)
            check(input.skipField(tag))
        }
        return tags
    }

    private class CapturedMethod : RuntimeException()
}
