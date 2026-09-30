// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.connectrpc.MethodSpec
import com.connectrpc.ProtocolClientInterface
import com.connectrpc.StreamType
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.protobuf.ByteString
import io.github.arcforges.contracts.events.v1.EventServiceClient
import io.github.arcforges.contracts.events.v1.Event
import io.github.arcforges.contracts.events.v1.EventServicePollRequest
import io.github.arcforges.contracts.events.v1.EventServiceWatchRequest
import io.github.arcforges.contracts.events.v1.ExecutionServiceAcknowledgeOutputRequest
import io.github.arcforges.contracts.events.v1.ExecutionServiceClient
import io.github.arcforges.contracts.events.v1.ExecutionServicePurgeTransientRequest
import io.github.arcforges.contracts.events.v1.ExecutionServiceReadOutputRequest
import io.github.arcforges.contracts.events.v1.ExecutionServiceStartTransientTurnRequest
import io.github.arcforges.contracts.events.v1.ExecutionServiceWatchOutputRequest
import io.github.arcforges.contracts.events.v1.OutputChunk
import io.github.arcforges.contracts.events.v1.StreamFrame
import io.github.arcforges.contracts.events.v1.StreamPosition
import io.github.arcforges.contracts.fixtures.ContractFixtures
import io.github.arcforges.contracts.foundation.v1.Id
import io.github.arcforges.contracts.foundation.v1.Instant
import io.github.arcforges.contracts.foundation.v1.ApplicationScope
import io.github.arcforges.contracts.foundation.v1.RequestMeta
import io.github.arcforges.contracts.foundation.v1.Revision
import io.github.arcforges.contracts.foundation.v1.ResponseMeta
import io.github.arcforges.contracts.publicapi.v1.ApplicationServiceClient
import io.github.arcforges.contracts.publicapi.v1.ApplicationTarget
import io.github.arcforges.contracts.publicapi.v1.ApplicationServiceDisconnectRequest
import io.github.arcforges.contracts.publicapi.v1.ApplicationServiceHeartbeatRequest
import io.github.arcforges.contracts.publicapi.v1.ApplicationServiceListRequest
import io.github.arcforges.contracts.publicapi.v1.HistoryArchiveRecord
import io.github.arcforges.contracts.publicapi.v1.HistoryMessage
import io.github.arcforges.contracts.publicapi.v1.ConversationView
import io.github.arcforges.contracts.publicapi.v1.HistoryServiceBeginImportRequest
import io.github.arcforges.contracts.publicapi.v1.HistoryServiceCancelImportRequest
import io.github.arcforges.contracts.publicapi.v1.HistoryServiceClient
import io.github.arcforges.contracts.publicapi.v1.HistoryServiceFinalizeImportRequest
import io.github.arcforges.contracts.publicapi.v1.HistoryServiceGetImportRequest
import io.github.arcforges.contracts.publicapi.v1.MessagePart
import io.github.arcforges.contracts.publicapi.v1.MessageView
import io.github.arcforges.contracts.publicapi.v1.TranscriptWindow
import io.github.arcforges.contracts.publicapi.v1.TranscriptMessage
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Method
import java.lang.reflect.Modifier
import java.lang.reflect.Proxy
import java.nio.file.Files
import java.nio.file.Path
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Locale

/** Direct offline consumer of the independent CON.11 public and private fixtures. */
object Con11ApplicationStreamsCases {
    private val applicationMessages = setOf(
        "ApplicationPresence",
        "HistoryImportManifest",
        "HistoryImportView",
        "TransientTurnRequest",
        "TranscriptWindow",
        "TranscriptMessage",
        "CompactionRecord",
        "HistoryArchiveHeader",
        "HistoryArchiveRecord",
        "HistoryMessage",
        "HistoryBranch",
        "HistoryArchiveEnd",
    )

    suspend fun run() {
        val root = repositoryRoot()
        val publicFixture = readPublicFixture()
        val privateFixture = Files.newBufferedReader(root.resolve("fixtures/internal/con-11-run-stream.json"), Charsets.UTF_8).use {
            JsonParser.parseReader(it).asJsonObject
        }
        val operationExport = Files.newBufferedReader(root.resolve("eng/operations/con-11.json"), Charsets.UTF_8).use {
            JsonParser.parseReader(it).asJsonObject
        }
        val seen = linkedSetOf<String>()

        verifyPublicRpcCalls(publicFixture, seen)
        verifyMessageFields(publicFixture, seen)
        verifyEventPayloads(publicFixture, seen)
        verifyUnaryOutcomeAlternatives(publicFixture)
        verifyPollProfile(publicFixture)
        verifyPublicBoundaries(publicFixture, seen)
        verifyPresenceBoundaries(publicFixture, seen)
        verifyOwnerBoundaryVectors(publicFixture, operationExport, seen)
        verifyCursorBoundaries(publicFixture, seen)
        verifyUInt64Boundaries(publicFixture, seen)
        verifyUnknownFieldBoundaries(publicFixture, seen)
        verifyPrivateProjection(root, privateFixture, seen)

        val allIds = fixtureIds(publicFixture, privateFixture)
        requireCon11(allIds.size == allIds.toSet().size, "fixture vector IDs are globally unique")
        requireCon11(seen.toSet() == allIds.toSet() && seen.size == allIds.size,
            "every known public/private fixture vector is consumed exactly once and no unknown vector is accepted")
        println("CON.11 Kotlin consumer verified ${seen.size} public/private fixture vectors and 14 generated Connect method specs.")
    }

    private fun readPublicFixture(): JsonObject {
        val resource = checkNotNull(
            ContractFixtures::class.java.getResourceAsStream("/arcforges/fixtures/con-11-application-streams.json"),
        ) { "Missing packaged public CON.11 fixture" }
        return resource.bufferedReader(Charsets.UTF_8).use { JsonParser.parseReader(it).asJsonObject }
    }

    private fun repositoryRoot(): Path {
        var candidate = Path.of("").toAbsolutePath().normalize()
        while (true) {
            if (Files.isRegularFile(candidate.resolve("fixtures/internal/con-11-run-stream.json"))) return candidate
            candidate = candidate.parent ?: break
        }
        throw IllegalStateException("CON.11 internal fixture is not reachable from the Kotlin test working directory")
    }

    private suspend fun verifyPublicRpcCalls(fixture: JsonObject, seen: MutableSet<String>) {
        val probe = MethodSpecProbe()
        val application = ApplicationServiceClient(probe.client)
        val history = HistoryServiceClient(probe.client)
        val execution = ExecutionServiceClient(probe.client)
        val events = EventServiceClient(probe.client)
        val vectors = fixture.getAsJsonArray("rpcVectors")
        requireCon11(vectors.size() == 14, "fixture declares exactly the 14 public CON.11 RPCs")

        for (entry in vectors) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val id = string(vector, "id")
            val before = probe.calls.size
            when (id) {
                "application.list" -> capture(probe, id) { application.list(ApplicationServiceListRequest.getDefaultInstance(), emptyMap()) }
                "application.heartbeat" -> capture(probe, id) { application.heartbeat(ApplicationServiceHeartbeatRequest.getDefaultInstance(), emptyMap()) }
                "application.disconnect" -> capture(probe, id) { application.disconnect(ApplicationServiceDisconnectRequest.getDefaultInstance(), emptyMap()) }
                "history.beginImport" -> capture(probe, id) { history.beginImport(HistoryServiceBeginImportRequest.getDefaultInstance(), emptyMap()) }
                "history.finalizeImport" -> capture(probe, id) { history.finalizeImport(HistoryServiceFinalizeImportRequest.getDefaultInstance(), emptyMap()) }
                "history.getImport" -> capture(probe, id) { history.getImport(HistoryServiceGetImportRequest.getDefaultInstance(), emptyMap()) }
                "history.cancelImport" -> capture(probe, id) { history.cancelImport(HistoryServiceCancelImportRequest.getDefaultInstance(), emptyMap()) }
                "execution.startTransientTurn" -> capture(probe, id) { execution.startTransientTurn(ExecutionServiceStartTransientTurnRequest.getDefaultInstance(), emptyMap()) }
                "execution.readOutput" -> capture(probe, id) { execution.readOutput(ExecutionServiceReadOutputRequest.getDefaultInstance(), emptyMap()) }
                "execution.watchOutput" -> capture(probe, id) { execution.watchOutput(ExecutionServiceWatchOutputRequest.getDefaultInstance(), emptyMap()) }
                "execution.acknowledgeOutput" -> capture(probe, id) { execution.acknowledgeOutput(ExecutionServiceAcknowledgeOutputRequest.getDefaultInstance(), emptyMap()) }
                "execution.purgeTransient" -> capture(probe, id) { execution.purgeTransient(ExecutionServicePurgeTransientRequest.getDefaultInstance(), emptyMap()) }
                "events.poll" -> capture(probe, id) { events.poll(EventServicePollRequest.getDefaultInstance(), emptyMap()) }
                "events.watch" -> capture(probe, id) { events.watch(EventServiceWatchRequest.getDefaultInstance(), emptyMap()) }
                else -> throw IllegalStateException("Unknown CON.11 RPC vector: $id")
            }

            requireCon11(probe.calls.size == before + 1, "one generated MethodSpec captured for $id")
            val captured = probe.calls.last()
            val expectedStream = when (string(vector, "streamType")) {
                "unary" -> StreamType.UNARY
                "serverStreaming" -> StreamType.SERVER
                else -> throw IllegalStateException("Unknown stream type in CON.11 fixture: ${string(vector, "streamType")}")
            }
            val expectedClientMethod = if (expectedStream == StreamType.UNARY) "unary" else "serverStream"
            val expectedPath = "${string(vector, "service")}/${string(vector, "method")}"
            requireCon11(captured.invokedMethod == expectedClientMethod, "Connect Kotlin call kind for $id")
            requireCon11(captured.spec.path == expectedPath, "generated MethodSpec path for $id")
            requireCon11(captured.spec.requestClass.simpleName == string(vector, "input"), "generated MethodSpec request type for $id")
            requireCon11(captured.spec.responseClass.simpleName == string(vector, "output").substringAfterLast('.'),
                "generated MethodSpec response type for $id")
            requireCon11(captured.spec.streamType == expectedStream, "generated MethodSpec stream type for $id")

            val requestClass = messageClass(string(vector, "input"), string(vector, "service"))
            checkExactFields(requestClass, vector.getAsJsonArray("inputFields"), "$id request")
        }
        requireCon11(probe.calls.size == 14, "all 14 generated client methods invoked once")
    }

    private suspend fun capture(probe: MethodSpecProbe, id: String, call: suspend () -> Any?) {
        try {
            call()
            throw IllegalStateException("Generated Connect method returned without reaching the MethodSpec probe: $id")
        } catch (signal: CapturedMethod) {
            requireCon11(signal.probe === probe, "expected MethodSpec probe sentinel for $id")
        }
    }

    private fun verifyMessageFields(fixture: JsonObject, seen: MutableSet<String>) {
        for (entry in fixture.getAsJsonArray("messageFieldVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val name = string(vector, "message")
            val type = messageClass(name)
            val fields = fieldPairs(vector.getAsJsonArray("fields")).toMutableList()
            if (name == "Event") {
                fields += fixture.getAsJsonArray("eventPayloadVectors").map { entry ->
                    val payload = entry.asJsonObject
                    string(payload, "field") to payload.get("tag").asInt
                }
            }
            checkExactFields(type, fields, string(vector, "id"))

            if (vector.has("oneofFields")) {
                for ((oneofName, fields) in vector.getAsJsonObject("oneofFields").entrySet()) {
                    val expectedNames = fields.asJsonArray.map { it.asString }
                    val numbers = fieldPairs(vector.getAsJsonArray("fields")).toMap()
                    val expected = expectedNames.map { it to checkNotNull(numbers[it]) }
                    checkOneof(type, oneofName, expected, string(vector, "id"))
                }
            }
            if (vector.has("payloadOneof")) {
                val getter = "get${pascal(string(vector, "payloadOneof"))}Case"
                requireCon11(type.methods.any { it.name == getter }, "generated Event payload oneof accessor")
            }
            if (vector.has("presenceFields")) {
                for (field in vector.getAsJsonArray("presenceFields").map { it.asString }) {
                    val hasMethod = "has${pascal(field)}"
                    requireCon11(type.methods.any { it.name == hasMethod },
                        "generated protobuf presence accessor: ${string(vector, "id")}/$field")
                }
            }
        }
    }

    private fun verifyPresenceBoundaries(fixture: JsonObject, seen: MutableSet<String>) {
        for (entry in fixture.getAsJsonArray("presenceBoundaryVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            when (string(vector, "id")) {
                "application-target-empty-product-presence" -> {
                    val parsed = ApplicationTarget.newBuilder().setProductId("").build().let {
                        ApplicationTarget.parseFrom(it.toByteArray())
                    }
                    requireCon11(parsed.hasProductId() && parsed.productId.isEmpty(), "explicit empty target product id presence")
                }
                "application-target-zero-epoch-presence" -> {
                    val parsed = ApplicationTarget.newBuilder().setInstanceEpoch(0L).build().let {
                        ApplicationTarget.parseFrom(it.toByteArray())
                    }
                    requireCon11(parsed.hasInstanceEpoch() && parsed.instanceEpoch == 0L, "explicit zero target epoch presence")
                }
                "request-meta-empty-application-scope-presence" -> {
                    val parsed = RequestMeta.newBuilder().setApplicationScope(ApplicationScope.getDefaultInstance()).build().let {
                        RequestMeta.parseFrom(it.toByteArray())
                    }
                    requireCon11(parsed.hasApplicationScope(), "empty RequestMeta applicationScope remains present at tag 8")
                }
                "conversation-view-empty-application-scope-presence" -> {
                    val parsed = ConversationView.newBuilder().setApplicationScope(ApplicationScope.getDefaultInstance()).build().let {
                        ConversationView.parseFrom(it.toByteArray())
                    }
                    requireCon11(parsed.hasApplicationScope(), "empty ConversationView applicationScope remains present at tag 10")
                }
                "conversation-view-unspecified-history-mode-presence" -> {
                    val parsed = ConversationView.newBuilder().setHistoryModeValue(0).build().let {
                        ConversationView.parseFrom(it.toByteArray())
                    }
                    requireCon11(parsed.hasHistoryMode() && parsed.historyModeValue == 0,
                        "explicit HistoryMode zero remains present at tag 11")
                }
                else -> throw IllegalStateException("Unknown CON.11 presence vector: ${string(vector, "id")}")
            }
        }
    }

    private fun verifyOwnerBoundaryVectors(fixture: JsonObject, export: JsonObject, seen: MutableSet<String>) {
        val operations = export.getAsJsonArray("operations").map { it.asJsonObject }
        for (entry in fixture.getAsJsonArray("ownerBoundaryVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val row = operations.single { string(it, "operationId") == string(vector, "operationId") }
            requireCon11(!vector.get("runtimeEnforcementProven").asBoolean,
                "offline owner scenario is fixture classification, not runtime authorization evidence: ${string(vector, "id")}")
            when (string(vector, "id")) {
                "history-identical-title-different-products" -> {
                    val products = vector.getAsJsonArray("sourceProductIds").map { it.asString }
                    val sources = vector.getAsJsonArray("sourceConversationIds").map { it.asString }
                    requireCon11(vector.get("sameTitle").asBoolean && string(vector, "title") == "Shared title"
                        && products.toSet().size == 2 && sources.toSet().size == 2
                        && string(vector, "expectedBoundary") == "keep-separate-source-identities",
                        "history identity is not inferred from a shared display title")
                }
                "history-finalize-mismatched-resource-owner" -> {
                    val requestOwner = vector.getAsJsonObject("requestOwner")
                    val importOwner = vector.getAsJsonObject("importOwner")
                    requireCon11(string(requestOwner, "productId") != string(importOwner, "productId")
                        && string(requestOwner, "installationId") != string(importOwner, "installationId")
                        && string(vector, "expectedBoundary") == "reject-mismatched-owner",
                        "mismatched history owner is an explicit negative contract fixture")
                }
                "application-heartbeat-forged-target" -> {
                    val bound = vector.getAsJsonObject("boundTarget")
                    val requested = vector.getAsJsonObject("requestTarget")
                    requireCon11(string(bound, "deviceId") != string(requested, "deviceId")
                        && string(bound, "installationId") != string(requested, "installationId")
                        && string(vector, "expectedBoundary") == "reject-forged-target",
                        "forged application target is an explicit negative contract fixture")
                }
                "application-disconnect-stale-epoch" -> {
                    requireCon11(vector.get("requestInstanceEpoch").asLong < vector.get("boundInstanceEpoch").asLong
                        && string(vector, "expectedBoundary") == "reject-stale-epoch",
                        "stale installation epoch is an explicit negative contract fixture")
                }
                "history-finalize-stale-consent" -> {
                    requireCon11(string(row.getAsJsonObject("authorization"), "approval") == string(vector, "authorizationApproval")
                        && string(vector, "consentSnapshotHash") != string(vector, "currentSnapshotHash")
                        && string(vector, "expectedBoundary") == "reject-stale-consent",
                        "history finalize requires its recorded consent and unchanged snapshot hash")
                }
                else -> throw IllegalStateException("Unknown CON.11 owner boundary vector: ${string(vector, "id")}")
            }
        }
    }

    private fun verifyCursorBoundaries(fixture: JsonObject, seen: MutableSet<String>) {
        for (entry in fixture.getAsJsonArray("opaqueCursorVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val cursor = string(vector, "value")
            val request = EventServicePollRequest.newBuilder().setMeta(RequestMeta.getDefaultInstance())
                .setSubscriptionKey("subscription-a").setCursor(cursor).setLimit(1).build()
            val parsed = EventServicePollRequest.parseFrom(request.toByteArray())
            requireCon11(parsed.cursor == cursor && string(vector, "interpretation").contains("never parse as a number"),
                "large Poll cursor round-trips as opaque UTF-8 text")
        }
        for (entry in fixture.getAsJsonArray("cursorByteBoundaryVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val cursor = string(vector, "repeatedCharacter").repeat(vector.get("repeatCount").asInt) + string(vector, "suffix")
            val byteLength = cursor.toByteArray(StandardCharsets.UTF_8).size
            val limit = vector.get("limit").asInt
            requireCon11(byteLength == vector.get("utf8Bytes").asInt
                && (byteLength <= limit) == vector.get("valid").asBoolean,
                "Poll cursor limit counts UTF-8 bytes, not UTF-16 code units: ${string(vector, "id")}")
            val request = EventServicePollRequest.newBuilder().setMeta(RequestMeta.getDefaultInstance())
                .setSubscriptionKey("subscription-a").setCursor(cursor).setLimit(1).build()
            val parsed = EventServicePollRequest.parseFrom(request.toByteArray())
            requireCon11(parsed.cursor == cursor, "multibyte Poll cursor wire round trip: ${string(vector, "id")}")
        }
    }

    private fun verifyUInt64Boundaries(fixture: JsonObject, seen: MutableSet<String>) {
        for (entry in fixture.getAsJsonArray("uint64BoundaryVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val value = string(vector, "value").toLong()
            if (string(vector, "message") == "Event") {
                val parsed = Event.newBuilder().setSeq(value).build().let { Event.parseFrom(it.toByteArray()) }
                requireCon11(parsed.seq == value, "event uint64 sequence survives a >2^53 JavaScript-safe-integer value")
            } else {
                val parsed = StreamPosition.newBuilder().setSequence(value).build().let { StreamPosition.parseFrom(it.toByteArray()) }
                requireCon11(parsed.sequence == value, "stream uint64 sequence survives a >2^53 JavaScript-safe-integer value")
            }
        }
    }

    private fun verifyUnknownFieldBoundaries(fixture: JsonObject, seen: MutableSet<String>) {
        for (entry in fixture.getAsJsonArray("unknownFieldVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val wire = string(vector, "wireHex").chunked(2).map { it.toInt(16).toByte() }.toByteArray()
            val parsed = StreamPosition.parseFrom(wire)
            requireCon11(parsed.cursor == string(vector, "cursor")
                && parsed.sequence == string(vector, "sequence").toLong()
                && parsed.toByteArray().contentEquals(wire)
                && vector.get("unknownTag").asInt == 100,
                "compatible unknown tag survives exact binary round trip: ${string(vector, "id")}")
        }
    }

    private fun verifyEventPayloads(fixture: JsonObject, seen: MutableSet<String>) {
        val eventClass = messageClass("Event", "arcforges.events.v1.Event")
        val expectedCases = mutableListOf<Pair<String, Int>>()
        for (entry in fixture.getAsJsonArray("eventPayloadVectors")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val id = string(vector, "id")
            val field = string(vector, "field")
            val tag = vector.get("tag").asInt
            requireCon11(fieldNumber(eventClass, field) == tag, "event payload generated field tag: $id")
            val payloadCase = caseEntries(eventClass, "payload").singleOrNull { it.second == tag }
            requireCon11(payloadCase?.first == field, "event payload oneof name/tag: $id")
            val getter = eventClass.getMethod("get${pascal(field)}")
            requireCon11(getter.returnType.simpleName == string(vector, "message"), "event payload generated type: $id")
            val payloadClass = messageClass(string(vector, "message"), "arcforges.events.v1.Event")
            checkExactFields(payloadClass, vector.getAsJsonArray("fields"), id)
            expectedCases.add(field to tag)
        }
        checkOneof(eventClass, "payload", expectedCases, "Registry04 event payload closure")
    }

    private fun verifyUnaryOutcomeAlternatives(fixture: JsonObject) {
        val profile = fixture.getAsJsonObject("unaryOutcomeProfile")
        val base = fieldPairs(profile.getAsJsonArray("fields"))
        val encoded = fieldPairs(profile.getAsJsonArray("encodedBodyAlternative"))
        val readIds = profile.getAsJsonArray("readProjectionOperationIds").map { it.asString }.toSet()
        for (entry in fixture.getAsJsonArray("rpcVectors")) {
            val vector = entry.asJsonObject
            if (string(vector, "streamType") != "unary") continue
            val operationId = string(vector, "operationId")
            val responseClass = messageClass(string(vector, "output"), string(vector, "service"))
            val expected = base + if (operationId in readIds) encoded else emptyList()
            checkOneof(responseClass, "outcome", expected, "$operationId response outcome")
        }
    }

    private fun verifyPollProfile(fixture: JsonObject) {
        val profile = fixture.getAsJsonObject("pollProfile")
        requireCon11(string(profile, "operationId") == "events.poll" && string(profile, "scope") == "resource-owner"
            && string(profile, "idempotency") == "Q" && string(profile, "compatibility") == "AO" && string(profile, "risk") == "R1"
            && string(profile, "approval") == "none" && profile.get("capability").isJsonNull
            && !profile.get("stepUp").asBoolean && !profile.get("localPresence").asBoolean
            && string(profile, "egress") == "authorizedHintResponseOnly" && !profile.get("patEligible").asBoolean
            && profile.getAsJsonArray("actorKinds").map { it.asString } == listOf("human"),
            "distinct Registry04 Poll pure-query/eight-field authorization profile")
        requireCon11(string(profile, "noCursor") == "emptyPageWithSignedHighWaterCursorAndResetRequired"
            && string(profile, "retry") == "sameCursorPureQuery; authorizationRefusalWaitsForNewSession; unavailableUsesRetryAfterBackoff",
            "Poll empty-page recovery and retry profile")
    }

    private fun verifyPublicBoundaries(fixture: JsonObject, seen: MutableSet<String>) {
        val groups = fixture.getAsJsonObject("aggregateBoundaryVectors")
        for (entry in groups.getAsJsonArray("transcriptPartTotals")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val perMessage = vector.getAsJsonArray("perMessageCounts").map { it.asInt }
            val transcriptMessages = perMessage.mapIndexed { index, count ->
                TranscriptMessage.newBuilder()
                    .setMessageId(testId(index + 1))
                    .setOrdinal(index.toLong())
                    .setRoleValue(1)
                    .addAllParts(List(count) { MessagePart.newBuilder().setText("x").build() })
                    .build()
            }
            val window = TranscriptWindow.newBuilder()
                .setBranchId(testId(3))
                .setBranchRevision(1L)
                .setFirstOrdinal(0L)
                .setLastOrdinal((transcriptMessages.size - 1).toLong())
                .setWindowHash("a".repeat(64))
                .addAllMessages(transcriptMessages)
                .build()
            val wire = window.toByteArray()
            val parsed = TranscriptWindow.parseFrom(wire)
            val actualPerMessage = parsed.messagesList.map { it.partsCount }
            val actualTotal = actualPerMessage.sum()
            val limit = vector.get("limit").asInt
            requireCon11(actualPerMessage == perMessage && actualTotal == perMessage.sum(),
                "transcript repeated part counts are represented by generated protobuf messages: ${string(vector, "id")}")
            requireCon11(wire.isNotEmpty() && (actualTotal <= limit) == vector.get("valid").asBoolean,
                "transcript aggregate part-count boundary: ${string(vector, "id")}")
        }

        for (entry in groups.getAsJsonArray("archiveRecordBytes")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val target = vector.get("serializedBytes").asInt
            val encoded = buildArchiveRecordBytes(target)
            val parsed = HistoryArchiveRecord.parseFrom(encoded)
            requireCon11(parsed.recordCase.name == "MESSAGE" && parsed.toByteArray().size == target,
                "length-delimited HistoryArchiveRecord exact-size vector: ${string(vector, "id")}")
            requireCon11((encoded.size <= vector.get("limit").asInt) == vector.get("valid").asBoolean,
                "1 MiB HistoryArchiveRecord boundary: ${string(vector, "id")}")
        }

        for (entry in groups.getAsJsonArray("outputChunkBytes")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val chunk = createChunk(vector.get("serializedBytes").asInt)
            requireCon11(chunk.toByteArray().size == vector.get("serializedBytes").asInt
                && (chunk.toByteArray().size <= vector.get("limit").asInt) == vector.get("valid").asBoolean,
                "encoded OutputChunk boundary: ${string(vector, "id")}")
        }

        for (entry in groups.getAsJsonArray("streamFrameBytes")) {
            val vector = entry.asJsonObject
            consume(vector, seen)
            val frame = createFrame(vector.get("serializedBytes").asInt)
            requireCon11(frame.toByteArray().size == vector.get("serializedBytes").asInt
                && (frame.toByteArray().size <= vector.get("limit").asInt) == vector.get("valid").asBoolean,
                "encoded public StreamFrame boundary: ${string(vector, "id")}")
        }
    }

    private fun verifyPrivateProjection(root: Path, fixture: JsonObject, seen: MutableSet<String>) {
        val rpcVectors = fixture.getAsJsonArray("rpcVectors")
        requireCon11(rpcVectors.size() == 1, "fixture declares exactly one private RunStream RPC")
        val vector = rpcVectors.single().asJsonObject
        consume(vector, seen)
        requireCon11(string(vector, "service") == "arcforges.cf.v1.RunStreamService"
            && string(vector, "method") == "Run" && string(vector, "input") == "RunStreamRequest"
            && string(vector, "output") == "arcforges.events.v1.StreamFrame"
            && string(vector, "streamType") == "serverStreaming"
            && fieldPairs(vector.getAsJsonArray("requestFields")) == listOf("execution" to 1, "attemptId" to 2, "generation" to 3),
            "private RunStream service, projection request tags, and shared public StreamFrame output")

        val boundary = fixture.getAsJsonObject("importBoundary")
        requireCon11(string(boundary, "privatePackage") == "arcforges.cf.v1"
            && boundary.getAsJsonArray("allowedPublicDependencies").map { it.asString }.toSet()
                == setOf("arcforges.foundation.v1", "arcforges.publicapi.v1", "arcforges.events.v1")
            && boundary.get("publicPackagesMustNotImportPrivatePackage").asBoolean,
            "RunStream private/public import-boundary declaration")
        checkPrivateProtoContract(root, vector)

        val publicFrame = StreamFrame::class.java
        val privateAllowed = setOf("output", "reset", "heartbeat")
        for (entry in fixture.getAsJsonArray("runStreamFrameVariants")) {
            val variant = entry.asJsonObject
            consume(variant, seen)
            val field = string(variant, "field")
            val tag = variant.get("tag").asInt
            requireCon11(fieldNumber(publicFrame, field) == tag
                && caseEntries(publicFrame, "frame").any { it == field to tag },
                "private RunStream references the public StreamFrame alternative: ${string(variant, "id")}")
            requireCon11(variant.get("allowed").asBoolean == (field in privateAllowed),
                "private producer admits only output/reset/heartbeat: ${string(variant, "id")}")
        }

        val limit = fixture.getAsJsonObject("limits").get("encodedFrameBytes").asInt
        requireCon11(fixture.getAsJsonObject("limits").get("outputChunkBytes").asInt == 32768,
            "private RunStream reuses the public 32 KiB encoded OutputChunk cap")
        for (entry in fixture.getAsJsonArray("encodedFrameBoundaryVectors")) {
            val boundaryVector = entry.asJsonObject
            consume(boundaryVector, seen)
            val target = boundaryVector.get("serializedBytes").asInt
            val frame = createFrame(target)
            requireCon11(boundaryVector.get("limit").asInt == limit && frame.toByteArray().size == target
                && (target <= limit) == boundaryVector.get("valid").asBoolean,
                "private encoded StreamFrame boundary: ${string(boundaryVector, "id")}")
        }
    }

    private fun checkPrivateProtoContract(root: Path, vector: JsonObject) {
        val privateProto = Files.readString(root.resolve("internal/proto/arcforges/cf/v1/stream.proto"))
        val publicEventsProto = Files.readString(root.resolve("public/proto/arcforges/events/v1/events.proto"))
        val importRegex = Regex("(?m)^\\s*import\\s+\"([^\"]+)\"\\s*;")
        val privateImports = importRegex.findAll(privateProto).map { it.groupValues[1] }.toSet()
        requireCon11(privateImports == setOf(
            "arcforges/foundation/v1/foundation.proto",
            "arcforges/publicapi/v1/chat.proto",
            "arcforges/events/v1/events.proto",
        ), "private RunStream imports only its required foundation/publicapi/events files")
        requireCon11(importRegex.findAll(publicEventsProto).none { it.groupValues[1].contains("/cf/")
            || it.groupValues[1].contains("/internal/") }, "public event schema never imports the private projection")

        val serviceNames = Regex("(?m)^\\s*service\\s+([A-Za-z_]\\w*)\\s*\\{")
            .findAll(privateProto).map { it.groupValues[1] }.toList()
        requireCon11(serviceNames == listOf("RunStreamService"), "private file registers only RunStreamService")
        val serviceBody = Regex("(?s)service\\s+RunStreamService\\s*\\{(.*?)\\}")
            .find(privateProto)?.groupValues?.get(1)
        requireCon11(serviceBody != null && Regex(
            "(?m)^\\s*rpc\\s+Run\\s*\\(\\s*RunStreamRequest\\s*\\)\\s+returns\\s*\\(\\s*stream\\s+arcforges\\.events\\.v1\\.StreamFrame\\s*\\)\\s*;",
        ).containsMatchIn(serviceBody), "private RunStream source declares the fixture's server-streaming method")
        val requestBody = Regex("(?s)message\\s+RunStreamRequest\\s*\\{(.*?)\\}")
            .find(privateProto)?.groupValues?.get(1)
        requireCon11(requestBody != null, "private RunStreamRequest source exists")
        requireCon11(Regex("(?m)^\\s*optional\\s+uint64\\s+generation\\s*=\\s*3\\b")
            .containsMatchIn(requestBody!!), "private generation preserves explicit proto3 presence")
        val sourceFields = Regex("(?m)^\\s*(?:optional\\s+)?[A-Za-z0-9_.]+\\s+([A-Za-z_]\\w*)\\s*=\\s*(\\d+)(?:\\s*\\[([^\\]]*)\\])?\\s*;")
            .findAll(requestBody!!)
            .map { match ->
                val declaredName = match.groupValues[1]
                val jsonName = Regex("json_name\\s*=\\s*\"([^\"]+)\"")
                    .find(match.groupValues[3])?.groupValues?.get(1) ?: camel(declaredName)
                jsonName to match.groupValues[2].toInt()
            }.toList()
        requireCon11(sourceFields == fieldPairs(vector.getAsJsonArray("requestFields")),
            "private RunStream source fields/tags match its independent fixture")
    }

    private fun buildArchiveRecordBytes(target: Int): ByteArray {
        fun build(textLength: Int): ByteArray {
            val message = MessageView.newBuilder()
                .setMessageId(testId(1))
                .setConversationId(testId(2))
                .setBranchId(testId(3))
                .setRole("user")
                .addParts(MessagePart.newBuilder().setText("x".repeat(textLength)).build())
                .setState("complete")
                .setRevision(Revision.newBuilder().setValue(1L).build())
                .build()
            val historyMessage = HistoryMessage.newBuilder()
                .setOrdinal(1L)
                .setMessage(message)
                .setCreatedAt(Instant.newBuilder().setUnixSeconds(1L).build())
                .build()
            return HistoryArchiveRecord.newBuilder().setMessage(historyMessage).build().toByteArray()
        }
        var low = 0
        var high = target
        while (low <= high) {
            val length = low + (high - low) / 2
            val bytes = build(length)
            if (bytes.size == target) return bytes
            if (bytes.size < target) low = length + 1 else high = length - 1
        }
        throw IllegalStateException("Could not construct exact-sized HistoryArchiveRecord vector: $target")
    }

    private fun createChunk(encodedBytes: Int): OutputChunk {
        val baseSize = newChunk(0).toByteArray().size
        var low = 0
        var high = 32768
        while (low <= high) {
            val length = low + (high - low) / 2
            val size = baseSize + length + varintSize(length) - 1
            if (size == encodedBytes) {
                val chunk = newChunk(length)
                requireCon11(chunk.toByteArray().size == encodedBytes, "exact OutputChunk byte construction")
                return chunk
            }
            if (size < encodedBytes) low = length + 1 else high = length - 1
        }
        throw IllegalStateException("Could not construct exact-sized OutputChunk vector: $encodedBytes")
    }

    private fun newChunk(dataBytes: Int): OutputChunk {
        val owner = io.github.arcforges.contracts.publicapi.v1.ExecutionOwner.newBuilder()
            .setTaskId(testId(1))
            .build()
        val id = testId(2)
        val data = ByteArray(dataBytes)
        val chunkHash = MessageDigest.getInstance("SHA-256").digest(data)
            .joinToString("") { byte -> "%02x".format(Locale.ROOT, byte.toInt() and 0xff) }
        return OutputChunk.newBuilder()
            .setExecution(owner)
            .setOffset(1L)
            .setData(ByteString.copyFrom(data))
            .setChunkHash(chunkHash)
            .setKind("text")
            .setAttemptId(id)
            .setStreamId(id)
            .build()
    }

    private fun createFrame(encodedBytes: Int): StreamFrame {
        val baseFrame = newFrame(0)
        val baseSize = baseFrame.toByteArray().size
        val baseChunkSize = baseFrame.output.toByteArray().size
        val dataBytes = (0..32768).firstOrNull { length ->
            val dataDelta = length + varintSize(length) - 1
            val chunkSize = baseChunkSize + dataDelta
            val frameSize = baseSize + dataDelta + varintSize(chunkSize) - varintSize(baseChunkSize)
            frameSize == encodedBytes
        } ?: throw IllegalStateException("Could not construct exact-sized StreamFrame vector: $encodedBytes")
        val frame = newFrame(dataBytes)
        requireCon11(frame.toByteArray().size == encodedBytes, "exact StreamFrame byte construction")
        return frame
    }

    private fun newFrame(dataBytes: Int): StreamFrame = StreamFrame.newBuilder()
        .setMeta(ResponseMeta.newBuilder().setCorrelationId(testId(4)).build())
        .setPosition(StreamPosition.newBuilder().setCursor("c").setSequence(1L).setGeneration(1L).build())
        .setOutput(newChunk(dataBytes))
        .build()

    private fun testId(suffix: Int = 15): Id = Id.newBuilder()
        .setValue(ByteString.copyFrom(ByteArray(16) { index -> if (index == 15) suffix.toByte() else index.toByte() }))
        .build()

    private fun varintSize(initial: Int): Int {
        var value = initial
        var size = 1
        while (value >= 128) {
            size++
            value = value ushr 7
        }
        return size
    }

    private fun checkExactFields(type: Class<*>, fields: JsonArray, label: String) {
        checkExactFields(type, fieldPairs(fields), label)
    }

    private fun checkExactFields(type: Class<*>, expected: List<Pair<String, Int>>, label: String) {
        val actual = type.declaredFields.asSequence()
            .filter { Modifier.isStatic(it.modifiers) && it.name.endsWith("_FIELD_NUMBER") }
            .map { field -> camel(field.name.removeSuffix("_FIELD_NUMBER")) to field.getInt(null) }
            .sortedBy { it.second }
            .toList()
        requireCon11(actual == expected, "exact generated protobuf fields/tags: $label; expected=$expected actual=$actual")
    }

    private fun checkOneof(type: Class<*>, oneof: String, expected: List<Pair<String, Int>>, label: String) {
        requireCon11(caseEntries(type, oneof) == expected,
            "exact generated protobuf oneof alternatives/tags: $label/$oneof")
    }

    private fun caseEntries(type: Class<*>, oneof: String): List<Pair<String, Int>> {
        val method = type.getMethod("get${pascal(oneof)}Case")
        val caseType = method.returnType
        requireCon11(caseType.isEnum, "generated protobuf oneof case enum: ${type.simpleName}.$oneof")
        return caseType.enumConstants.map { it as Enum<*> }
            .filterNot { it.name.endsWith("_NOT_SET") }
            .map { case ->
                val number = (caseType.getMethod("getNumber").invoke(case) as Number).toInt()
                camel(case.name) to number
            }
    }

    private fun fieldNumber(type: Class<*>, jsonName: String): Int =
        type.getField("${snake(jsonName).uppercase(Locale.ROOT)}_FIELD_NUMBER").getInt(null)

    private fun messageClass(name: String, service: String? = null): Class<*> {
        if (name.contains('.')) return Class.forName("io.github.arcforges.contracts.${name.removePrefix("arcforges.")}")
        val packageName = when {
            service != null && service.startsWith("arcforges.publicapi.") -> "publicapi.v1"
            service != null -> "events.v1"
            name in applicationMessages -> "publicapi.v1"
            else -> "events.v1"
        }
        return Class.forName("io.github.arcforges.contracts.$packageName.$name")
    }

    private fun fieldPairs(fields: JsonArray): List<Pair<String, Int>> = fields.map { item ->
        val pair = item.asJsonArray
        pair[0].asString to pair[1].asInt
    }

    private fun fixtureIds(publicFixture: JsonObject, privateFixture: JsonObject): List<String> = buildList {
        fun addVectors(array: JsonArray) = array.forEach { add(string(it.asJsonObject, "id")) }
        fun addBoundaryGroups(groups: JsonObject) = groups.entrySet().forEach { addVectors(it.value.asJsonArray) }
        addVectors(publicFixture.getAsJsonArray("rpcVectors"))
        addVectors(publicFixture.getAsJsonArray("messageFieldVectors"))
        addVectors(publicFixture.getAsJsonArray("eventPayloadVectors"))
        addBoundaryGroups(publicFixture.getAsJsonObject("aggregateBoundaryVectors"))
        addVectors(publicFixture.getAsJsonArray("ownerBoundaryVectors"))
        addVectors(publicFixture.getAsJsonArray("opaqueCursorVectors"))
        addVectors(publicFixture.getAsJsonArray("cursorByteBoundaryVectors"))
        addVectors(publicFixture.getAsJsonArray("uint64BoundaryVectors"))
        addVectors(publicFixture.getAsJsonArray("unknownFieldVectors"))
        addVectors(publicFixture.getAsJsonArray("presenceBoundaryVectors"))
        addVectors(privateFixture.getAsJsonArray("rpcVectors"))
        addVectors(privateFixture.getAsJsonArray("runStreamFrameVariants"))
        addVectors(privateFixture.getAsJsonArray("encodedFrameBoundaryVectors"))
    }

    private fun consume(vector: JsonObject, seen: MutableSet<String>) {
        val id = string(vector, "id")
        requireCon11(seen.add(id), "fixture vector consumed once: $id")
    }

    private fun string(value: JsonObject, name: String): String = value.get(name).asString

    private fun snake(value: String): String = value.replace(Regex("([a-z0-9])([A-Z])"), "$1_$2")

    private fun camel(value: String): String = value.lowercase(Locale.ROOT).split('_')
        .mapIndexed { index, part -> if (index == 0) part else part.replaceFirstChar { it.uppercase(Locale.ROOT) } }
        .joinToString("")

    private fun pascal(value: String): String = camel(value).replaceFirstChar { it.uppercase(Locale.ROOT) }

    private fun requireCon11(condition: Boolean, label: String) {
        if (!condition) throw IllegalStateException("CON.11 Kotlin fixture failed: $label")
    }

    private data class CapturedSpec(val invokedMethod: String, val spec: MethodSpec<*, *>)

    private class CapturedMethod(val probe: MethodSpecProbe) : RuntimeException()

    private class MethodSpecProbe : InvocationHandler {
        val calls = mutableListOf<CapturedSpec>()
        val client: ProtocolClientInterface = Proxy.newProxyInstance(
            ProtocolClientInterface::class.java.classLoader,
            arrayOf(ProtocolClientInterface::class.java),
            this,
        ) as ProtocolClientInterface

        override fun invoke(proxy: Any?, method: Method, args: Array<out Any?>?): Any? {
            when (method.name) {
                "unary", "serverStream" -> {
                    val spec = args?.filterIsInstance<MethodSpec<*, *>>()?.singleOrNull()
                        ?: throw AssertionError("Connect ${method.name} did not receive exactly one MethodSpec")
                    calls.add(CapturedSpec(method.name, spec))
                    throw CapturedMethod(this)
                }
                "toString" -> return "CON.11 MethodSpec probe"
                "hashCode" -> return System.identityHashCode(proxy)
                "equals" -> return proxy === args?.firstOrNull()
                else -> throw AssertionError("Unexpected ProtocolClientInterface method: ${method.name}")
            }
        }
    }
}
