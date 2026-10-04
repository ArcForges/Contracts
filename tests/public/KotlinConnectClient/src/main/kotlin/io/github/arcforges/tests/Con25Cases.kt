// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.connectrpc.MethodSpec
import com.connectrpc.ProtocolClientInterface
import com.connectrpc.StreamType
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.protobuf.ByteString
import com.google.protobuf.CodedInputStream
import com.google.protobuf.MessageLite
import io.github.arcforges.contracts.fixtures.ContractFixtures
import io.github.arcforges.contracts.foundation.v1.ArcError
import io.github.arcforges.contracts.foundation.v1.Decimal
import io.github.arcforges.contracts.foundation.v1.EncodedBodyRef
import io.github.arcforges.contracts.foundation.v1.Id
import io.github.arcforges.contracts.foundation.v1.Instant
import io.github.arcforges.contracts.foundation.v1.PageRequest
import io.github.arcforges.contracts.foundation.v1.PageState
import io.github.arcforges.contracts.foundation.v1.Rational
import io.github.arcforges.contracts.foundation.v1.RequestMeta
import io.github.arcforges.contracts.foundation.v1.ResourceRef
import io.github.arcforges.contracts.foundation.v1.ResponseMeta
import io.github.arcforges.contracts.foundation.v1.Revision
import io.github.arcforges.contracts.publicapi.v1.ConnectorChallenge
import io.github.arcforges.contracts.publicapi.v1.ConnectorConnection
import io.github.arcforges.contracts.publicapi.v1.ConnectorDefinition
import io.github.arcforges.contracts.publicapi.v1.ConnectorProof
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceBeginConnectionRequest
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceBeginConnectionResponse
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceBeginConnectionValue
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceClientInterface
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceCompleteConnectionRequest
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceCompleteConnectionResponse
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceCompleteConnectionValue
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceGetConnectionRequest
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceGetConnectionResponse
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceGetConnectionValue
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceListConnectionsRequest
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceListConnectionsResponse
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceListConnectionsValue
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceListDefinitionsRequest
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceListDefinitionsResponse
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceListDefinitionsValue
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceRevokeConnectionRequest
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceRevokeConnectionResponse
import io.github.arcforges.contracts.publicapi.v1.ConnectorServiceRevokeConnectionValue
import io.github.arcforges.contracts.publicapi.v1.MetadataEntry
import io.github.arcforges.contracts.publicapi.v1.MetadataScalar
import io.github.arcforges.contracts.publicapi.v1.ScopeTime
import io.github.arcforges.contracts.simulation.v1.SimulationDataSegment
import io.github.arcforges.contracts.simulation.v1.SimulationEvent
import io.github.arcforges.contracts.simulation.v1.SimulationGap
import io.github.arcforges.contracts.simulation.v1.SimulationSample
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Modifier
import java.lang.reflect.Proxy
import java.math.BigInteger
import java.security.MessageDigest
import java.util.regex.Pattern
import kotlin.coroutines.Continuation
import kotlin.coroutines.intrinsics.COROUTINE_SUSPENDED
import kotlinx.coroutines.runBlocking

/**
 * CON.25 consumer: public ConnectorService (generated client surface, lite messages, fixture constraints applied by
 * explicit Kotlin checks because lite messages carry no validators) and the four af-segment.v1 Simulation records
 * (in-test canonical encoder and strict reader; no production code, no dependency beyond the published artifacts).
 */
internal object Con25Cases {
    private val connectorVectorIds = listOf(
        "definition-valid-oauth",
        "definition-valid-minimal-no-origins",
        "definition-bad-id-characters",
        "definition-uppercase-manifest-hash",
        "definition-short-manifest-hash",
        "definition-unknown-auth-kind",
        "definition-http-origin",
        "definition-origin-with-path",
        "definition-origin-with-credentials",
        "definition-too-many-origins",
        "definition-duplicate-scope",
        "definition-missing-package-version",
        "connection-valid-connected",
        "connection-valid-failed-with-reason",
        "connection-unknown-state",
        "connection-empty-name",
        "connection-name-too-long",
        "connection-zero-connection-id",
        "connection-missing-revision",
        "connection-duplicate-scope",
        "challenge-valid-oauth-url",
        "challenge-valid-personal-token-no-url",
        "challenge-http-url",
        "challenge-missing-expiry",
        "challenge-zero-flow-id",
        "proof-valid-callback-receipt",
        "proof-valid-personal-token",
        "proof-no-arm",
        "proof-empty-secret",
        "proof-oversize-secret",
        "begin-request-valid",
        "begin-request-missing-name",
        "begin-request-bad-definition-id",
        "complete-request-valid",
        "complete-request-missing-proof",
        "revoke-request-valid",
        "revoke-request-zero-connection-id",
        "list-connections-value-valid",
        "list-connections-value-over-page-bound",
    )

    private val positiveSegmentIds = listOf(
        "empty-segment-keeps-every-ordered-repeated-field",
        "numeric-digital-and-event-samples-in-delivered-order",
        "duplicate-delivery-differs-only-by-ordinal-and-fault-marker",
        "gap-and-fault-markers-with-and-without-channel",
        "binary64-bit-words-preserve-sign-and-extremes",
        "integral-extremes-use-exact-strings",
        "text-metadata-escapes-and-unicode",
    )

    private val refusalIds = listOf(
        "refuse-uppercase-uuid",
        "refuse-json-number-for-uint64",
        "refuse-leading-zero-uint64",
        "refuse-uint64-overflow",
        "refuse-negative-zero-sint64",
        "refuse-double-as-json-number",
        "refuse-uppercase-hex-double",
        "refuse-short-hex-double",
        "refuse-nan-bit-word",
        "refuse-infinity-bit-word",
        "refuse-unsorted-members",
        "refuse-missing-empty-repeated",
        "refuse-two-oneof-arms",
        "refuse-no-oneof-arm",
        "refuse-insignificant-whitespace",
        "refuse-null-for-absent-optional",
        "refuse-unknown-member",
        "refuse-duplicate-member",
        "refuse-wrong-encoding-profile",
        "refuse-wrong-execution-profile",
        "refuse-resource-metadata-arm",
        "refuse-out-of-order-ordinals",
        "refuse-duplicate-ordinal",
        "refuse-unknown-gap-kind",
        "refuse-zero-rate-denominator",
        "refuse-non-minimal-escape",
        "refuse-uppercase-escape-digits",
        "refuse-byte-order-mark",
    )

    private class Refused(reason: String) : RuntimeException(reason)

    private fun refuse(reason: String): Nothing = throw Refused(reason)

    fun run() {
        runConnector(loadFixture("con-25-connector"))
        runSegment(loadFixture("con-25-af-segment"))
        println("CON.25: published ConnectorService client, lite messages, 39 connector vectors, canonical af-segment.v1 encode/strict-read vectors and refusals passed.")
    }

    private fun loadFixture(name: String): JsonObject =
        ContractFixtures::class.java.getResourceAsStream("/arcforges/fixtures/$name.json")
            ?.bufferedReader(Charsets.UTF_8)?.use { JsonParser.parseReader(it).asJsonObject }
            ?: error("CON.25 public fixture $name is missing from the published contract-fixtures archive")

    // ---------------------------------------------------------------------------------------------------------
    // ConnectorService
    // ---------------------------------------------------------------------------------------------------------

    private class Op(
        val operationId: String, val rpc: String, val request: Class<*>, val value: Class<*>, val response: Class<*>,
        val encodedBody: Boolean, val idempotency: String, val risk: String, val approval: String, val stepUp: Boolean,
        val egress: String, val compatibility: String, val foreground: Boolean,
    )

    private val ops = listOf(
        Op("connector.listDefinitions", "ConnectorService/ListDefinitions", ConnectorServiceListDefinitionsRequest::class.java,
            ConnectorServiceListDefinitionsValue::class.java, ConnectorServiceListDefinitionsResponse::class.java,
            true, "Q", "R1", "none", false, "none", "AO", false),
        Op("connector.listConnections", "ConnectorService/ListConnections", ConnectorServiceListConnectionsRequest::class.java,
            ConnectorServiceListConnectionsValue::class.java, ConnectorServiceListConnectionsResponse::class.java,
            true, "Q", "R1", "none", false, "none", "AO", false),
        Op("connector.beginConnection", "ConnectorService/BeginConnection", ConnectorServiceBeginConnectionRequest::class.java,
            ConnectorServiceBeginConnectionValue::class.java, ConnectorServiceBeginConnectionResponse::class.java,
            false, "CC", "R3", "foreground-human-consent", true, "definition-hash-bound-provider-origins-scopes", "FR", true),
        Op("connector.completeConnection", "ConnectorService/CompleteConnection", ConnectorServiceCompleteConnectionRequest::class.java,
            ConnectorServiceCompleteConnectionValue::class.java, ConnectorServiceCompleteConnectionResponse::class.java,
            false, "NI", "R3", "original-foreground-human-consent-flow", true, "definition-hash-bound-provider-origins-scopes", "FR", true),
        Op("connector.getConnection", "ConnectorService/GetConnection", ConnectorServiceGetConnectionRequest::class.java,
            ConnectorServiceGetConnectionValue::class.java, ConnectorServiceGetConnectionResponse::class.java,
            true, "Q", "R1", "none", false, "none", "AO", false),
        Op("connector.revokeConnection", "ConnectorService/RevokeConnection", ConnectorServiceRevokeConnectionRequest::class.java,
            ConnectorServiceRevokeConnectionValue::class.java, ConnectorServiceRevokeConnectionResponse::class.java,
            false, "DE", "R2", "foreground-human-confirmation", false, "definition-hash-bound-existing-provider-revocation", "FR", true),
    )

    private fun fieldNumbers(type: Class<*>): Map<String, Int> = type.fields
        .filter { Modifier.isStatic(it.modifiers) && it.name.endsWith("_FIELD_NUMBER") && it.type == Int::class.javaPrimitiveType }
        .associate { it.name.removeSuffix("_FIELD_NUMBER") to it.getInt(null) }

    private fun snake(name: String): String = name.replace(Regex("([A-Z])"), "_$1").uppercase()

    private fun declared(pairs: JsonArray): List<Pair<String, Int>> =
        pairs.map { snake(it.asJsonArray[0].asString) to it.asJsonArray[1].asInt }

    private fun actualOrdered(type: Class<*>): List<Pair<String, Int>> =
        fieldNumbers(type).toList().sortedBy { it.second }

    private fun runConnector(fixture: JsonObject) {
        check(fixture["schemaVersion"].asString == "con-25-connector.v1")
        check(fixture["evidenceClass"].asString == "offline-contract-only-no-owner-service-or-provider")
        check(fixture["service"].asString == "arcforges.publicapi.v1.ConnectorService")
        check(fixture["keyPattern"].asString == keyPatternText) { "Fixture key pattern drifted from the Kotlin check" }
        verifyGeneratedSurface(fixture)

        val vectors = fixture.getAsJsonArray("vectors")
        val ids = vectors.map { it.asJsonObject["id"].asString }
        check(ids.size == connectorVectorIds.size && ids.toSet().size == ids.size && ids.toSet() == connectorVectorIds.toSet())
        val consumed = mutableSetOf<String>()
        var accepted = 0
        var rejected = 0
        for (element in vectors) {
            val vector = element.asJsonObject
            val id = vector["id"].asString
            check(id in connectorVectorIds) { "Unknown CON.25 connector vector $id" }
            check(consumed.add(id)) { "Duplicate CON.25 connector vector consumption: $id" }
            val type = vector["type"].asString
            val valid = vector["valid"].asBoolean
            val value = vector.getAsJsonObject("value")
            val reason = validateVector(type, value)
            if (valid) {
                check(reason == null) { "Valid connector vector $id was rejected: $reason" }
                accepted++
            } else {
                check(reason != null) { "Invalid connector vector $id was accepted" }
                rejected++
            }
        }
        check(consumed == connectorVectorIds.toSet()) { "Every CON.25 connector vector must be consumed exactly once" }
        check(accepted == 12 && rejected == 27) { "Connector vector split changed: $accepted accepted, $rejected rejected" }
    }

    private fun verifyGeneratedSurface(fixture: JsonObject) {
        val methods = ConnectorServiceClientInterface::class.java.declaredMethods
            .filter { Modifier.isAbstract(it.modifiers) && !it.isSynthetic }
        check(methods.map { it.name }.sorted() == listOf(
            "beginConnection", "completeConnection", "getConnection", "listConnections", "listDefinitions", "revokeConnection",
        ))
        val requestByMethod = mapOf(
            "listDefinitions" to ConnectorServiceListDefinitionsRequest::class.java,
            "listConnections" to ConnectorServiceListConnectionsRequest::class.java,
            "beginConnection" to ConnectorServiceBeginConnectionRequest::class.java,
            "completeConnection" to ConnectorServiceCompleteConnectionRequest::class.java,
            "getConnection" to ConnectorServiceGetConnectionRequest::class.java,
            "revokeConnection" to ConnectorServiceRevokeConnectionRequest::class.java,
        )
        check(methods.all { it.parameterTypes.firstOrNull() == requestByMethod[it.name] })

        val operations = fixture.getAsJsonArray("operations").map { it.asJsonObject }
        check(operations.size == ops.size)
        for (index in ops.indices) {
            val op = ops[index]
            val row = operations[index]
            check(row["operationId"].asString == op.operationId && row["rpc"].asString == op.rpc)
            check(row["requestType"].asString == op.request.simpleName)
            check(row["valueType"].asString == op.value.simpleName)
            check(row["responseType"].asString == op.response.simpleName)
            // Reflected generated tag constants must equal the fixture-declared field lists exactly (names, tags, order).
            check(actualOrdered(op.request) == declared(row.getAsJsonArray("requestFields"))) { "${op.request.simpleName} request fields" }
            check(actualOrdered(op.value) == declared(row.getAsJsonArray("valueFields"))) { "${op.value.simpleName} value fields" }
            val outcome = declared(row.getAsJsonArray("outcomeFields"))
            check(actualOrdered(op.response) == listOf("META" to 1) + outcome) { "${op.response.simpleName} response fields" }
            check(outcome.map { it.first } == (if (op.encodedBody) listOf("VALUE", "ERROR", "ENCODED_BODY") else listOf("VALUE", "ERROR")))
            check(outcome.map { it.second } == (if (op.encodedBody) listOf(2, 3, 4) else listOf(2, 3)))
            // Tag discipline: meta = 1, payload tags >= 10 for requests and values.
            val requestTags = actualOrdered(op.request)
            check(requestTags.first() == "META" to 1 && requestTags.drop(1).all { it.second >= 10 })
            check(actualOrdered(op.value).all { it.second >= 10 })

            val auth = row.getAsJsonObject("authorization")
            check(auth["scope"].asString == "assistant" && auth["capability"].isJsonNull)
            check(auth.getAsJsonArray("actorKinds").map { it.asString } == listOf("human"))
            check(!auth["localPresence"].asBoolean && !auth["patEligible"].asBoolean && !auth["toolReachable"].asBoolean)
            check(auth["idempotency"].asString == op.idempotency && auth["risk"].asString == op.risk)
            check(auth["approval"].asString == op.approval && auth["stepUp"].asBoolean == op.stepUp)
            check(auth["egress"].asString == op.egress && auth["compatibility"].asString == op.compatibility)
            check(auth["foreground"].asBoolean == op.foreground)
        }

        val records = fixture.getAsJsonObject("records")
        val recordClasses = mapOf(
            "ConnectorDefinition" to ConnectorDefinition::class.java,
            "ConnectorConnection" to ConnectorConnection::class.java,
            "ConnectorChallenge" to ConnectorChallenge::class.java,
            "ConnectorProof" to ConnectorProof::class.java,
        )
        check(records.keySet() == recordClasses.keys)
        for ((name, type) in recordClasses) {
            val fields = records.getAsJsonArray(name).map { it.asJsonArray }
            check(actualOrdered(type) == fields.map { snake(it[0].asString) to it[1].asInt }) { "$name record fields" }
            check(fields.map { it[2].asString.startsWith("repeated ") } ==
                fields.map { it[0].asString in setOf("origins", "scopes", "capabilities") })
        }
        check(RequestMeta.EXPECTED_REV_FIELD_NUMBER == 2) { "RequestMeta tag 2 is expectedRev" }
        check(ConnectorProof.CALLBACK_RECEIPT_FIELD_NUMBER == 1 && ConnectorProof.PERSONAL_TOKEN_FIELD_NUMBER == 2)
        check(ConnectorServiceRevokeConnectionRequest.META_FIELD_NUMBER == 1 &&
            ConnectorServiceRevokeConnectionRequest.CONNECTION_ID_FIELD_NUMBER == 10)
        check(fieldNumbers(ConnectorServiceRevokeConnectionRequest::class.java).keys == setOf("META", "CONNECTION_ID"))
        val local = fixture.getAsJsonObject("localTwin")
        check(local["package"].asString == "arcforges.local.platform.v1" && local["pageBound"].asInt == 200 && local["publicPageBound"].asInt == 100)

        verifyRpcRecorder()
        verifyOutcomes()
    }

    private fun verifyRpcRecorder() {
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
        val client = io.github.arcforges.contracts.publicapi.v1.ConnectorServiceClient(protocolClient)
        val meta = RequestMeta.getDefaultInstance()
        val anId = id("00112233445566778899aabbccddeeff")
        val rpcCalls: List<suspend () -> Unit> = listOf(
            { client.listDefinitions(ConnectorServiceListDefinitionsRequest.newBuilder().setMeta(meta).setPage(PageRequest.getDefaultInstance()).build()) },
            { client.listConnections(ConnectorServiceListConnectionsRequest.newBuilder().setMeta(meta).setPage(PageRequest.getDefaultInstance()).build()) },
            { client.beginConnection(ConnectorServiceBeginConnectionRequest.newBuilder().setMeta(meta).setConnectionId(anId).setDefinitionId("github.oauth").setName("n").build()) },
            { client.completeConnection(ConnectorServiceCompleteConnectionRequest.newBuilder().setMeta(meta).setFlowId(anId).setProof(ConnectorProof.newBuilder().setCallbackReceipt("r")).build()) },
            { client.getConnection(ConnectorServiceGetConnectionRequest.newBuilder().setMeta(meta).setConnectionId(anId).build()) },
            { client.revokeConnection(ConnectorServiceRevokeConnectionRequest.newBuilder().setMeta(meta).setConnectionId(anId).build()) },
        )
        check(rpcCalls.size == ops.size)
        for (rpcCall in rpcCalls) {
            try {
                runBlocking { rpcCall() }
                error("Generated Connect call did not reach the recorder")
            } catch (_: CapturedMethod) {
                // The fake protocol client records the generated method specification and stops before I/O.
            }
        }
        check(capturedMethods.map { it.path } == ops.map { "arcforges.publicapi.v1.${it.rpc}" })
        check(capturedMethods.map { it.requestClass.java } == ops.map { it.request })
        check(capturedMethods.map { it.responseClass.java } == ops.map { it.response })
        check(capturedMethods.all { it.streamType == StreamType.UNARY })
    }

    private class ResponseCase(val arm: String, val message: MessageLite, val parse: (ByteArray) -> MessageLite)

    private fun verifyOutcomes() {
        val meta = ResponseMeta.getDefaultInstance()
        val error = ArcError.getDefaultInstance()
        val encoded = EncodedBodyRef.getDefaultInstance()
        val page = PageState.newBuilder().setHasMore(false).build()
        val connection = connection(JsonParser.parseString(
            """{"connectionIdHex":"00112233445566778899aabbccddeeff","definitionId":"github.oauth","name":"n","state":"connected","scopes":["a"],"revision":"1"}""",
        ).asJsonObject)
        val challenge = ConnectorChallenge.getDefaultInstance()
        val cases = listOf(
            ResponseCase("VALUE", ConnectorServiceListDefinitionsResponse.newBuilder().setMeta(meta)
                .setValue(ConnectorServiceListDefinitionsValue.newBuilder().addItems(ConnectorDefinition.getDefaultInstance()).setPage(page)).build()) { ConnectorServiceListDefinitionsResponse.parseFrom(it) },
            ResponseCase("ERROR", ConnectorServiceListDefinitionsResponse.newBuilder().setMeta(meta).setError(error).build()) { ConnectorServiceListDefinitionsResponse.parseFrom(it) },
            ResponseCase("ENCODED_BODY", ConnectorServiceListDefinitionsResponse.newBuilder().setMeta(meta).setEncodedBody(encoded).build()) { ConnectorServiceListDefinitionsResponse.parseFrom(it) },
            ResponseCase("VALUE", ConnectorServiceListConnectionsResponse.newBuilder().setMeta(meta)
                .setValue(ConnectorServiceListConnectionsValue.newBuilder().addItems(connection).setPage(page)).build()) { ConnectorServiceListConnectionsResponse.parseFrom(it) },
            ResponseCase("ERROR", ConnectorServiceListConnectionsResponse.newBuilder().setMeta(meta).setError(error).build()) { ConnectorServiceListConnectionsResponse.parseFrom(it) },
            ResponseCase("ENCODED_BODY", ConnectorServiceListConnectionsResponse.newBuilder().setMeta(meta).setEncodedBody(encoded).build()) { ConnectorServiceListConnectionsResponse.parseFrom(it) },
            ResponseCase("VALUE", ConnectorServiceBeginConnectionResponse.newBuilder().setMeta(meta)
                .setValue(ConnectorServiceBeginConnectionValue.newBuilder().setChallenge(challenge)).build()) { ConnectorServiceBeginConnectionResponse.parseFrom(it) },
            ResponseCase("ERROR", ConnectorServiceBeginConnectionResponse.newBuilder().setMeta(meta).setError(error).build()) { ConnectorServiceBeginConnectionResponse.parseFrom(it) },
            ResponseCase("VALUE", ConnectorServiceCompleteConnectionResponse.newBuilder().setMeta(meta)
                .setValue(ConnectorServiceCompleteConnectionValue.newBuilder().setConnection(connection)).build()) { ConnectorServiceCompleteConnectionResponse.parseFrom(it) },
            ResponseCase("ERROR", ConnectorServiceCompleteConnectionResponse.newBuilder().setMeta(meta).setError(error).build()) { ConnectorServiceCompleteConnectionResponse.parseFrom(it) },
            ResponseCase("VALUE", ConnectorServiceGetConnectionResponse.newBuilder().setMeta(meta)
                .setValue(ConnectorServiceGetConnectionValue.newBuilder().setConnection(connection)).build()) { ConnectorServiceGetConnectionResponse.parseFrom(it) },
            ResponseCase("ERROR", ConnectorServiceGetConnectionResponse.newBuilder().setMeta(meta).setError(error).build()) { ConnectorServiceGetConnectionResponse.parseFrom(it) },
            ResponseCase("ENCODED_BODY", ConnectorServiceGetConnectionResponse.newBuilder().setMeta(meta).setEncodedBody(encoded).build()) { ConnectorServiceGetConnectionResponse.parseFrom(it) },
            ResponseCase("VALUE", ConnectorServiceRevokeConnectionResponse.newBuilder().setMeta(meta)
                .setValue(ConnectorServiceRevokeConnectionValue.newBuilder().setConnection(connection)).build()) { ConnectorServiceRevokeConnectionResponse.parseFrom(it) },
            ResponseCase("ERROR", ConnectorServiceRevokeConnectionResponse.newBuilder().setMeta(meta).setError(error).build()) { ConnectorServiceRevokeConnectionResponse.parseFrom(it) },
        )
        for (case in cases) {
            val decoded = roundTrip(case.message, case.parse)
            val outcomeCase = decoded.javaClass.getMethod("getOutcomeCase").invoke(decoded).toString()
            check(outcomeCase == case.arm) { "${decoded.javaClass.simpleName} outcome ${case.arm}" }
            val numbers = wireFieldNumbers(decoded)
            check(numbers.first() == 1 && numbers.size == 2 && numbers.all { it in fieldNumbers(decoded.javaClass).values })
        }
        check(cases.size == 15)
    }

    private fun validateVector(type: String, value: JsonObject): String? {
        val message: MessageLite
        val reason: String?
        when (type) {
            "ConnectorDefinition" -> {
                val decoded = roundTrip(definition(value)) { ConnectorDefinition.parseFrom(it) }
                message = decoded
                reason = validateDefinition(decoded)
            }
            "ConnectorConnection" -> {
                val decoded = roundTrip(connection(value)) { ConnectorConnection.parseFrom(it) }
                message = decoded
                reason = validateConnection(decoded)
            }
            "ConnectorChallenge" -> {
                val decoded = roundTrip(challenge(value)) { ConnectorChallenge.parseFrom(it) }
                message = decoded
                reason = validateChallenge(decoded)
            }
            "ConnectorProof" -> {
                val decoded = roundTrip(proof(value)) { ConnectorProof.parseFrom(it) }
                message = decoded
                reason = validateProof(decoded)
            }
            "ConnectorServiceBeginConnectionRequest" -> {
                val built = ConnectorServiceBeginConnectionRequest.newBuilder().setMeta(RequestMeta.getDefaultInstance())
                if (value.has("connectionIdHex")) built.setConnectionId(id(value["connectionIdHex"].asString))
                if (value.has("definitionId")) built.setDefinitionId(value["definitionId"].asString)
                if (value.has("name")) built.setName(value["name"].asString)
                val decoded = roundTrip(built.build()) { ConnectorServiceBeginConnectionRequest.parseFrom(it) }
                message = decoded
                reason = firstReason(
                    if (decoded.hasMeta()) null else "meta missing",
                    idReason(decoded.hasConnectionId(), decoded.connectionId, "connectionId"),
                    keyReason(decoded.hasDefinitionId(), decoded.definitionId, "definitionId"),
                    nameReason(decoded.hasName(), decoded.name),
                )
            }
            "ConnectorServiceCompleteConnectionRequest" -> {
                val built = ConnectorServiceCompleteConnectionRequest.newBuilder().setMeta(RequestMeta.getDefaultInstance())
                if (value.has("flowIdHex")) built.setFlowId(id(value["flowIdHex"].asString))
                if (value.has("proof")) built.setProof(proof(value.getAsJsonObject("proof")))
                val decoded = roundTrip(built.build()) { ConnectorServiceCompleteConnectionRequest.parseFrom(it) }
                message = decoded
                reason = firstReason(
                    if (decoded.hasMeta()) null else "meta missing",
                    idReason(decoded.hasFlowId(), decoded.flowId, "flowId"),
                    if (decoded.hasProof()) validateProof(decoded.proof) else "proof missing",
                )
            }
            "ConnectorServiceRevokeConnectionRequest" -> {
                val built = ConnectorServiceRevokeConnectionRequest.newBuilder().setMeta(RequestMeta.getDefaultInstance())
                if (value.has("connectionIdHex")) built.setConnectionId(id(value["connectionIdHex"].asString))
                val decoded = roundTrip(built.build()) { ConnectorServiceRevokeConnectionRequest.parseFrom(it) }
                message = decoded
                reason = firstReason(
                    if (decoded.hasMeta()) null else "meta missing",
                    idReason(decoded.hasConnectionId(), decoded.connectionId, "connectionId"),
                )
            }
            "ConnectorServiceListConnectionsValue" -> {
                val built = ConnectorServiceListConnectionsValue.newBuilder()
                value.getAsJsonArray("items")?.forEach { built.addItems(connection(it.asJsonObject)) }
                if (value.has("page")) built.setPage(PageState.newBuilder().setHasMore(value.getAsJsonObject("page")["hasMore"].asBoolean))
                val decoded = roundTrip(built.build()) { ConnectorServiceListConnectionsValue.parseFrom(it) }
                message = decoded
                reason = firstReason(
                    if (decoded.itemsCount <= 100) null else "items exceed the public page bound of 100",
                    decoded.itemsList.mapNotNull { validateConnection(it) }.firstOrNull(),
                    if (decoded.hasPage() && decoded.page.hasHasMore()) null else "page.hasMore missing",
                )
            }
            else -> error("Unknown CON.25 connector vector type $type")
        }
        // Every vector message, valid or not, must use only generated field numbers on the wire.
        val declaredNumbers = fieldNumbers(message.javaClass).values
        check(wireFieldNumbers(message).all { it in declaredNumbers }) { "$type wire tags outside the generated field set" }
        return reason
    }

    private fun firstReason(vararg reasons: String?): String? = reasons.firstOrNull { it != null }

    private const val keyPatternText = "^[A-Za-z0-9._:/-]{1,128}$"
    private val keyPattern = Regex("[A-Za-z0-9._:/-]{1,128}")
    private val hashPattern = Regex("[0-9a-f]{64}")
    private val authKinds = setOf("none", "oauth2", "personalToken")
    private val connectionStates = setOf("configured", "awaitingAuthorization", "connected", "expired", "revoked", "failed")
    private val dnsLabel = """[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"""
    private val originPattern = Regex(
        """https://(?:$dnsLabel(?:\.$dnsLabel)*|\[[0-9A-Fa-f:.]{2,45}\])(?::(6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{0,3}))?""",
    )
    private val urlPattern = Regex("""https://\S+""")

    private fun keyReason(has: Boolean, value: String, name: String): String? =
        if (!has) "$name missing" else if (!keyPattern.matches(value)) "$name violates the key pattern" else null

    private fun idReason(has: Boolean, value: Id, name: String): String? = when {
        !has -> "$name missing"
        value.value.size() != 16 -> "$name is not 16 bytes"
        value.value.toByteArray().all { it.toInt() == 0 } -> "$name is the zero Id"
        else -> null
    }

    private fun nameReason(has: Boolean, value: String): String? {
        if (!has) return "name missing"
        val scalars = value.codePointCount(0, value.length)
        return if (scalars < 1 || scalars > 256) "name length" else null
    }

    private fun keyListReason(values: List<String>, name: String): String? = when {
        values.size > 32 -> "$name exceeds 32 items"
        values.toSet().size != values.size -> "$name is not unique"
        values.any { !keyPattern.matches(it) } -> "$name item violates the key pattern"
        else -> null
    }

    private fun originReason(origin: String): String? {
        if (origin.toByteArray(Charsets.UTF_8).size > 2048) return "origin exceeds 2048 bytes"
        val match = originPattern.matchEntire(origin) ?: return "origin is not https host[:port]"
        if (origin.startsWith("https://[") && origin.count { it == ':' } < 2) return "IPv6 origin needs colons"
        return if (match.value == origin) null else "origin"
    }

    private fun instantReason(value: Instant): String? = when {
        !value.hasUnixSeconds() || !value.hasNanos() -> "instant member missing"
        value.unixSeconds < -62135596800L || value.unixSeconds > 253402300799L -> "instant seconds out of range"
        value.nanos < 0 || value.nanos > 999_999_999 -> "instant nanos out of range"
        else -> null
    }

    private fun validateDefinition(value: ConnectorDefinition): String? = firstReason(
        keyReason(value.hasDefinitionId(), value.definitionId, "definitionId"),
        keyReason(value.hasPackageId(), value.packageId, "packageId"),
        keyReason(value.hasPackageVersion(), value.packageVersion, "packageVersion"),
        if (!value.hasManifestHash()) "manifestHash missing" else if (!hashPattern.matches(value.manifestHash)) "manifestHash is not 64 lower-case hex" else null,
        keyReason(value.hasAuthKind(), value.authKind, "authKind"),
        if (value.hasAuthKind() && value.authKind !in authKinds) "authKind outside the closed set" else null,
        if (value.originsCount > 32) "origins exceed 32 items" else null,
        if (value.originsList.toSet().size != value.originsCount) "origins are not unique" else null,
        value.originsList.mapNotNull { originReason(it) }.firstOrNull(),
        keyListReason(value.scopesList, "scopes"),
        keyListReason(value.capabilitiesList, "capabilities"),
    )

    private fun validateConnection(value: ConnectorConnection): String? = firstReason(
        idReason(value.hasConnectionId(), value.connectionId, "connectionId"),
        keyReason(value.hasDefinitionId(), value.definitionId, "definitionId"),
        nameReason(value.hasName(), value.name),
        keyReason(value.hasState(), value.state, "state"),
        if (value.hasState() && value.state !in connectionStates) "state outside the closed set" else null,
        keyListReason(value.scopesList, "scopes"),
        if (value.hasRevision()) null else "revision missing",
        if (value.hasExpiresAt()) instantReason(value.expiresAt) else null,
        if (value.hasReason()) keyReason(true, value.reason, "reason") else null,
    )

    private fun validateChallenge(value: ConnectorChallenge): String? = firstReason(
        idReason(value.hasFlowId(), value.flowId, "flowId"),
        idReason(value.hasConnectionId(), value.connectionId, "connectionId"),
        if (value.hasAuthorizationUrl() &&
            (!urlPattern.matches(value.authorizationUrl) || value.authorizationUrl.toByteArray(Charsets.UTF_8).size > 2048)
        ) "authorizationUrl must be https without whitespace and at most 2048 bytes" else null,
        if (!value.hasExpiresAt()) "expiresAt missing" else instantReason(value.expiresAt),
    )

    private fun validateProof(value: ConnectorProof): String? {
        val secret = when (value.proofCase) {
            ConnectorProof.ProofCase.CALLBACK_RECEIPT -> value.callbackReceipt
            ConnectorProof.ProofCase.PERSONAL_TOKEN -> value.personalToken
            ConnectorProof.ProofCase.PROOF_NOT_SET -> return "exactly one proof arm is required"
        }
        return if (secret.isEmpty() || secret.toByteArray(Charsets.UTF_8).size > 8192) "secret must be 1..8192 bytes" else null
    }

    private fun id(hex: String): Id {
        check(hex.length == 32 && hex.all { it in "0123456789abcdef" })
        val bytes = hex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        return Id.newBuilder().setValue(ByteString.copyFrom(bytes)).build()
    }

    private fun instant(value: JsonObject): Instant {
        val built = Instant.newBuilder()
        if (value.has("unixSeconds")) built.setUnixSeconds(value["unixSeconds"].asString.toLong())
        if (value.has("nanos")) built.setNanos(value["nanos"].asInt)
        return built.build()
    }

    private fun definition(value: JsonObject): ConnectorDefinition {
        val built = ConnectorDefinition.newBuilder()
        if (value.has("definitionId")) built.setDefinitionId(value["definitionId"].asString)
        if (value.has("packageId")) built.setPackageId(value["packageId"].asString)
        if (value.has("packageVersion")) built.setPackageVersion(value["packageVersion"].asString)
        if (value.has("manifestHash")) built.setManifestHash(value["manifestHash"].asString)
        if (value.has("authKind")) built.setAuthKind(value["authKind"].asString)
        value.getAsJsonArray("origins")?.forEach { built.addOrigins(it.asString) }
        value.getAsJsonArray("scopes")?.forEach { built.addScopes(it.asString) }
        value.getAsJsonArray("capabilities")?.forEach { built.addCapabilities(it.asString) }
        return built.build()
    }

    private fun connection(value: JsonObject): ConnectorConnection {
        val built = ConnectorConnection.newBuilder()
        if (value.has("connectionIdHex")) built.setConnectionId(id(value["connectionIdHex"].asString))
        if (value.has("definitionId")) built.setDefinitionId(value["definitionId"].asString)
        if (value.has("name")) built.setName(value["name"].asString)
        if (value.has("state")) built.setState(value["state"].asString)
        value.getAsJsonArray("scopes")?.forEach { built.addScopes(it.asString) }
        if (value.has("revision")) built.setRevision(Revision.newBuilder().setValue(value["revision"].asString.toLong()))
        if (value.has("expiresAt")) built.setExpiresAt(instant(value.getAsJsonObject("expiresAt")))
        if (value.has("reason")) built.setReason(value["reason"].asString)
        return built.build()
    }

    private fun challenge(value: JsonObject): ConnectorChallenge {
        val built = ConnectorChallenge.newBuilder()
        if (value.has("flowIdHex")) built.setFlowId(id(value["flowIdHex"].asString))
        if (value.has("connectionIdHex")) built.setConnectionId(id(value["connectionIdHex"].asString))
        if (value.has("authorizationUrl")) built.setAuthorizationUrl(value["authorizationUrl"].asString)
        if (value.has("expiresAt")) built.setExpiresAt(instant(value.getAsJsonObject("expiresAt")))
        return built.build()
    }

    private fun proof(value: JsonObject): ConnectorProof {
        val built = ConnectorProof.newBuilder()
        if (value.has("callbackReceipt")) built.setCallbackReceipt(value["callbackReceipt"].asString)
        if (value.has("personalToken")) built.setPersonalToken(value["personalToken"].asString)
        return built.build()
    }

    private fun <T : MessageLite> roundTrip(message: T, parse: (ByteArray) -> T): T {
        val bytes = message.toByteArray()
        val decoded = parse(bytes)
        check(decoded == message && decoded.toByteArray().contentEquals(bytes))
        return decoded
    }

    private fun wireFieldNumbers(message: MessageLite): List<Int> {
        val input = CodedInputStream.newInstance(message.toByteArray())
        val numbers = mutableListOf<Int>()
        while (true) {
            val tag = input.readTag()
            if (tag == 0) break
            numbers.add(tag ushr 3)
            check(input.skipField(tag))
        }
        return numbers
    }

    private class CapturedMethod : RuntimeException()

    // ---------------------------------------------------------------------------------------------------------
    // af-segment.v1 canonical encoder (message -> text)
    // ---------------------------------------------------------------------------------------------------------

    private fun obj(vararg members: Pair<String, String>?): String = members.filterNotNull()
        .sortedWith { left, right -> left.first.compareTo(right.first) }
        .joinToString(",", "{", "}") { quote(it.first) + ":" + it.second }

    private fun arr(items: List<String>): String = items.joinToString(",", "[", "]")

    private fun quote(text: String): String {
        val out = StringBuilder("\"")
        var index = 0
        while (index < text.length) {
            val c = text[index]
            when {
                Character.isHighSurrogate(c) -> {
                    if (index + 1 >= text.length || !Character.isLowSurrogate(text[index + 1])) refuse("unpaired high surrogate")
                    out.append(c).append(text[index + 1])
                    index++
                }
                Character.isLowSurrogate(c) -> refuse("unpaired low surrogate")
                c == '"' -> out.append("\\\"")
                c == '\\' -> out.append("\\\\")
                c == '\b' -> out.append("\\b")
                c == '\t' -> out.append("\\t")
                c == '\n' -> out.append("\\n")
                c == '\u000c' -> out.append("\\f")
                c == '\r' -> out.append("\\r")
                c.code < 0x20 -> out.append("\\u00").append("%02x".format(c.code))
                else -> out.append(c)
            }
            index++
        }
        return out.append('"').toString()
    }

    private fun uuid(value: Id): String {
        val bytes = value.value.toByteArray()
        if (bytes.size != 16) refuse("Id is not 16 bytes")
        val hex = bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
        return "${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}"
    }

    private fun u64(value: Long): String = quote(java.lang.Long.toUnsignedString(value))
    private fun s64(value: Long): String = quote(value.toString())
    private fun u32(value: Int): String = quote(Integer.toUnsignedString(value))

    private fun doubleWord(value: Double): String {
        if (value.isNaN() || value.isInfinite()) refuse("nonfinite double")
        return quote(java.lang.Long.toHexString(java.lang.Double.doubleToRawLongBits(value)).padStart(16, '0'))
    }

    private fun encodeRational(value: Rational): String = obj(
        if (value.hasDenominator()) "denominator" to u64(value.denominator) else null,
        if (value.hasNumerator()) "numerator" to s64(value.numerator) else null,
    )

    private fun encodeTime(value: ScopeTime): String = obj(
        if (value.hasRate()) "rate" to encodeRational(value.rate) else null,
        if (value.hasTicks()) "ticks" to s64(value.ticks) else null,
    )

    private fun encodeScalar(value: MetadataScalar): String = when (value.valueCase) {
        MetadataScalar.ValueCase.TEXT -> obj("text" to quote(value.text))
        MetadataScalar.ValueCase.BOOLEAN -> obj("boolean" to value.boolean.toString())
        MetadataScalar.ValueCase.INTEGER -> obj("integer" to s64(value.integer))
        MetadataScalar.ValueCase.NUMBER -> obj("number" to doubleWord(value.number))
        MetadataScalar.ValueCase.DECIMAL -> obj(
            "decimal" to obj(if (value.decimal.hasValue()) "value" to quote(value.decimal.value) else null),
        )
        MetadataScalar.ValueCase.INSTANT -> obj(
            "instant" to obj(
                if (value.instant.hasNanos()) "nanos" to u32(value.instant.nanos) else null,
                if (value.instant.hasUnixSeconds()) "unixSeconds" to s64(value.instant.unixSeconds) else null,
            ),
        )
        MetadataScalar.ValueCase.RESOURCE -> refuse("the resource arm is not representable in af-segment.v1")
        MetadataScalar.ValueCase.VALUE_NOT_SET -> refuse("a metadata scalar needs exactly one arm")
    }

    private fun encodeEntry(value: MetadataEntry): String = obj(
        if (value.hasName()) "name" to quote(value.name) else null,
        if (value.hasValue()) "value" to encodeScalar(value.value) else null,
    )

    private fun encodeSample(value: SimulationSample): String = obj(
        if (value.hasChannelId()) "channelId" to quote(uuid(value.channelId)) else null,
        if (value.hasDeliveredOrdinal()) "deliveredOrdinal" to u64(value.deliveredOrdinal) else null,
        "faultIds" to arr(value.faultIdsList.map { quote(uuid(it)) }),
        if (value.hasTick()) "tick" to u64(value.tick) else null,
        if (value.hasTime()) "time" to encodeTime(value.time) else null,
        when (value.valueCase) {
            SimulationSample.ValueCase.NUMERIC -> "numeric" to doubleWord(value.numeric)
            SimulationSample.ValueCase.DIGITAL -> "digital" to value.digital.toString()
            SimulationSample.ValueCase.EVENT_ID -> "eventId" to quote(uuid(value.eventId))
            SimulationSample.ValueCase.VALUE_NOT_SET -> refuse("a sample needs exactly one value arm")
        },
    )

    private fun encodeEvent(value: SimulationEvent): String = obj(
        if (value.hasChannelId()) "channelId" to quote(uuid(value.channelId)) else null,
        if (value.hasDuration()) "duration" to encodeTime(value.duration) else null,
        if (value.hasEventId()) "eventId" to quote(uuid(value.eventId)) else null,
        if (value.hasFaultId()) "faultId" to quote(uuid(value.faultId)) else null,
        "fields" to arr(value.fieldsList.map(::encodeEntry)),
        if (value.hasKind()) "kind" to quote(value.kind) else null,
        if (value.hasStart()) "start" to encodeTime(value.start) else null,
    )

    private fun encodeGap(value: SimulationGap): String = obj(
        if (value.hasChannelId()) "channelId" to quote(uuid(value.channelId)) else null,
        if (value.hasFaultId()) "faultId" to quote(uuid(value.faultId)) else null,
        if (value.hasKind()) "kind" to quote(value.kind) else null,
        if (value.hasStartTick()) "startTick" to u64(value.startTick) else null,
        if (value.hasTickCount()) "tickCount" to u64(value.tickCount) else null,
    )

    private fun encodeSegment(value: SimulationDataSegment): String = obj(
        if (value.hasEncodingProfile()) "encodingProfile" to quote(value.encodingProfile) else null,
        "events" to arr(value.eventsList.map(::encodeEvent)),
        if (value.hasExecutionProfile()) "executionProfile" to quote(value.executionProfile) else null,
        "gaps" to arr(value.gapsList.map(::encodeGap)),
        "records" to arr(value.recordsList.map(::encodeSample)),
        if (value.hasStartTick()) "startTick" to u64(value.startTick) else null,
        if (value.hasTickCount()) "tickCount" to u64(value.tickCount) else null,
    )

    // ---------------------------------------------------------------------------------------------------------
    // Semantic constraints (message level; the Kotlin equivalent of the generated shape validators)
    // ---------------------------------------------------------------------------------------------------------

    private val gapKinds = setOf("drop", "disconnect", "malformed")
    private val decimalPattern = Regex("""-?(0|[1-9][0-9]*)(\.[0-9]{1,9})?""")

    private fun wellFormed(text: String): Boolean {
        var index = 0
        while (index < text.length) {
            val c = text[index]
            if (Character.isHighSurrogate(c)) {
                if (index + 1 >= text.length || !Character.isLowSurrogate(text[index + 1])) return false
                index++
            } else if (Character.isLowSurrogate(c)) return false
            index++
        }
        return true
    }

    private fun checkId(has: Boolean, value: Id, name: String) {
        if (!has) refuse("$name missing")
        if (value.value.size() != 16 || value.value.toByteArray().all { it.toInt() == 0 }) refuse("$name is not a nonzero 16-byte Id")
    }

    private fun checkKey(has: Boolean, value: String, name: String) {
        if (!has || !keyPattern.matches(value)) refuse("$name violates the key pattern")
    }

    private fun checkTime(has: Boolean, value: ScopeTime, name: String) {
        if (!has) refuse("$name missing")
        if (!value.hasTicks() || !value.hasRate()) refuse("$name needs ticks and rate")
        val rate = value.rate
        if (!rate.hasNumerator() || !rate.hasDenominator()) refuse("$name rate incomplete")
        if (rate.numerator <= 0L) refuse("$name rate numerator must be positive")
        if (rate.denominator == 0L) refuse("$name rate denominator must be at least 1")
        val gcd = BigInteger.valueOf(rate.numerator).gcd(BigInteger(java.lang.Long.toUnsignedString(rate.denominator)))
        if (gcd != BigInteger.ONE) refuse("$name rate is not reduced")
    }

    private fun checkDecimal(text: String) {
        if (!decimalPattern.matches(text) || text == "-0" || (text.contains('.') && text.endsWith('0'))) refuse("decimal is not canonical")
        if (text.replace("-", "").replace(".", "").trimStart('0').length > 28) refuse("decimal has too many digits")
    }

    private fun checkScalar(value: MetadataScalar) {
        when (value.valueCase) {
            MetadataScalar.ValueCase.TEXT -> if (!wellFormed(value.text)) refuse("text has an unpaired surrogate")
            MetadataScalar.ValueCase.BOOLEAN, MetadataScalar.ValueCase.INTEGER -> Unit
            MetadataScalar.ValueCase.NUMBER -> if (value.number.isNaN() || value.number.isInfinite()) refuse("number is nonfinite")
            MetadataScalar.ValueCase.DECIMAL -> {
                if (!value.decimal.hasValue()) refuse("decimal value missing")
                checkDecimal(value.decimal.value)
            }
            MetadataScalar.ValueCase.INSTANT -> instantReason(value.instant)?.let { refuse(it) }
            MetadataScalar.ValueCase.RESOURCE -> refuse("the resource arm is not representable in af-segment.v1")
            MetadataScalar.ValueCase.VALUE_NOT_SET -> refuse("a metadata scalar needs exactly one arm")
        }
    }

    private fun semanticCheck(segment: SimulationDataSegment) {
        if (!segment.hasEncodingProfile() || segment.encodingProfile != "af-segment.v1") refuse("encodingProfile must be af-segment.v1")
        if (!segment.hasExecutionProfile() || segment.executionProfile != "af-sim.v1") refuse("executionProfile must be af-sim.v1")
        if (!segment.hasStartTick() || !segment.hasTickCount()) refuse("startTick and tickCount are required")
        var previous: Long? = null
        for (sample in segment.recordsList) {
            checkId(sample.hasChannelId(), sample.channelId, "sample.channelId")
            if (!sample.hasTick() || !sample.hasDeliveredOrdinal()) refuse("sample tick and deliveredOrdinal are required")
            checkTime(sample.hasTime(), sample.time, "sample.time")
            when (sample.valueCase) {
                SimulationSample.ValueCase.NUMERIC -> if (sample.numeric.isNaN() || sample.numeric.isInfinite()) refuse("numeric is nonfinite")
                SimulationSample.ValueCase.DIGITAL -> Unit
                SimulationSample.ValueCase.EVENT_ID -> checkId(true, sample.eventId, "sample.eventId")
                SimulationSample.ValueCase.VALUE_NOT_SET -> refuse("a sample needs exactly one value arm")
            }
            sample.faultIdsList.forEach { checkId(true, it, "sample.faultIds") }
            val last = previous
            if (last != null && java.lang.Long.compareUnsigned(last, sample.deliveredOrdinal) >= 0) {
                refuse("records must ascend strictly by deliveredOrdinal")
            }
            previous = sample.deliveredOrdinal
        }
        for (event in segment.eventsList) {
            checkId(event.hasEventId(), event.eventId, "event.eventId")
            checkId(event.hasChannelId(), event.channelId, "event.channelId")
            checkTime(event.hasStart(), event.start, "event.start")
            if (event.hasDuration()) checkTime(true, event.duration, "event.duration")
            checkKey(event.hasKind(), event.kind, "event.kind")
            if (event.hasFaultId()) checkId(true, event.faultId, "event.faultId")
            for (entry in event.fieldsList) {
                checkKey(entry.hasName(), entry.name, "entry.name")
                if (!entry.hasValue()) refuse("entry value missing")
                checkScalar(entry.value)
            }
        }
        for (gap in segment.gapsList) {
            if (gap.hasChannelId()) checkId(true, gap.channelId, "gap.channelId")
            if (!gap.hasStartTick() || !gap.hasTickCount()) refuse("gap startTick and tickCount are required")
            checkId(gap.hasFaultId(), gap.faultId, "gap.faultId")
            if (!gap.hasKind() || gap.kind !in gapKinds) refuse("gap kind must be drop, disconnect or malformed")
        }
    }

    // ---------------------------------------------------------------------------------------------------------
    // Strict JSON reader (duplicate members, BOM, lenient forms and wrong types are refused)
    // ---------------------------------------------------------------------------------------------------------

    private sealed class J
    private class JO(val members: List<Pair<String, J>>) : J()
    private class JA(val items: List<J>) : J()
    private class JS(val value: String) : J()
    private class JN(val raw: String) : J()
    private class JB(val value: Boolean) : J()
    private object JNull : J()

    private class StrictJson(private val text: String) {
        private var pos = 0
        private val number = Pattern.compile("-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")

        fun parse(): J {
            if (text.startsWith("﻿")) refuse("byte order mark")
            val result = value(0)
            whitespace()
            if (pos != text.length) refuse("trailing content")
            return result
        }

        private fun whitespace() {
            while (pos < text.length && (text[pos] == ' ' || text[pos] == '\t' || text[pos] == '\n' || text[pos] == '\r')) pos++
        }

        private fun expect(c: Char) {
            if (pos >= text.length || text[pos] != c) refuse("expected '$c' at $pos")
            pos++
        }

        private fun literal(word: String, result: J): J {
            if (!text.startsWith(word, pos)) refuse("bad literal at $pos")
            pos += word.length
            return result
        }

        private fun value(depth: Int): J {
            if (depth > 64) refuse("nesting too deep")
            whitespace()
            if (pos >= text.length) refuse("unexpected end")
            return when (val c = text[pos]) {
                '{' -> objectValue(depth)
                '[' -> arrayValue(depth)
                '"' -> JS(string())
                't' -> literal("true", JB(true))
                'f' -> literal("false", JB(false))
                'n' -> literal("null", JNull)
                else -> if (c == '-' || c in '0'..'9') numberValue() else refuse("unexpected '$c' at $pos")
            }
        }

        private fun numberValue(): J {
            val matcher = number.matcher(text).region(pos, text.length)
            if (!matcher.lookingAt()) refuse("bad number at $pos")
            pos = matcher.end()
            return JN(matcher.group())
        }

        private fun objectValue(depth: Int): J {
            expect('{')
            val members = mutableListOf<Pair<String, J>>()
            val seen = HashSet<String>()
            whitespace()
            if (pos < text.length && text[pos] == '}') {
                pos++
                return JO(members)
            }
            while (true) {
                whitespace()
                val key = string()
                if (!seen.add(key)) refuse("duplicate member $key")
                whitespace()
                expect(':')
                members.add(key to value(depth + 1))
                whitespace()
                if (pos < text.length && text[pos] == ',') {
                    pos++
                    continue
                }
                expect('}')
                return JO(members)
            }
        }

        private fun arrayValue(depth: Int): J {
            expect('[')
            val items = mutableListOf<J>()
            whitespace()
            if (pos < text.length && text[pos] == ']') {
                pos++
                return JA(items)
            }
            while (true) {
                items.add(value(depth + 1))
                whitespace()
                if (pos < text.length && text[pos] == ',') {
                    pos++
                    continue
                }
                expect(']')
                return JA(items)
            }
        }

        private fun string(): String {
            expect('"')
            val out = StringBuilder()
            while (true) {
                if (pos >= text.length) refuse("unterminated string")
                val c = text[pos++]
                when {
                    c == '"' -> break
                    c < ' ' -> refuse("raw control character in string")
                    c == '\\' -> {
                        if (pos >= text.length) refuse("dangling escape")
                        when (val e = text[pos++]) {
                            '"' -> out.append('"')
                            '\\' -> out.append('\\')
                            '/' -> out.append('/')
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000c')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (pos + 4 > text.length) refuse("short unicode escape")
                                val hex = text.substring(pos, pos + 4)
                                if (!hex.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) refuse("bad unicode escape")
                                out.append(hex.toInt(16).toChar())
                                pos += 4
                            }
                            else -> refuse("bad escape \\$e")
                        }
                    }
                    else -> out.append(c)
                }
            }
            val result = out.toString()
            if (!wellFormed(result)) refuse("unpaired surrogate")
            return result
        }
    }

    // ---------------------------------------------------------------------------------------------------------
    // Strict read (J -> message), then semantic check, then byte-identical re-encode
    // ---------------------------------------------------------------------------------------------------------

    private val u64Text = Regex("0|[1-9][0-9]*")
    private val s64Text = Regex("0|-?[1-9][0-9]*")
    private val hexWord = Regex("[0-9a-f]{16}")
    private val uuidText = Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    private fun J.asObject(allowed: Set<String>, required: Set<String>): JO {
        val o = this as? JO ?: refuse("object expected")
        if (o.members.any { it.first !in allowed }) refuse("unknown member in a closed object")
        if (required.any { name -> o.members.none { it.first == name } }) refuse("required member missing")
        return o
    }

    private fun JO.member(name: String): J? = members.firstOrNull { it.first == name }?.second
    private fun J.text(): String = (this as? JS)?.value ?: refuse("string expected")
    private fun J.list(): List<J> = (this as? JA)?.items ?: refuse("array expected")

    private fun J.readU64(): Long {
        val text = text()
        if (!u64Text.matches(text)) refuse("uint64 must be an exact base10 string")
        val big = BigInteger(text)
        if (big.bitLength() > 64) refuse("uint64 out of range")
        return big.toLong()
    }

    private fun J.readS64(): Long {
        val text = text()
        if (!s64Text.matches(text)) refuse("sint64 must be an exact base10 string")
        val big = BigInteger(text)
        if (big.bitLength() > 63) refuse("sint64 out of range")
        return big.toLong()
    }

    private fun J.readU32(): Int {
        val text = text()
        if (!u64Text.matches(text)) refuse("uint32 must be an exact base10 string")
        val big = BigInteger(text)
        if (big.bitLength() > 32) refuse("uint32 out of range")
        return big.toLong().toInt()
    }

    private fun J.readDouble(): Double {
        val text = text()
        if (!hexWord.matches(text)) refuse("double must be 16 lower-case hex digits")
        val bits = java.lang.Long.parseUnsignedLong(text, 16)
        if (((bits ushr 52) and 0x7ffL) == 0x7ffL) refuse("nonfinite double")
        return java.lang.Double.longBitsToDouble(bits)
    }

    private fun J.readBool(): Boolean = (this as? JB)?.value ?: refuse("boolean expected")

    private fun J.readId(): Id {
        val text = text()
        if (!uuidText.matches(text)) refuse("Id must be a lower-case hyphenated UUID")
        return id(text.replace("-", ""))
    }

    private fun J.readTime(): ScopeTime {
        val o = asObject(setOf("rate", "ticks"), setOf("rate", "ticks"))
        val rate = o.member("rate")!!.asObject(setOf("denominator", "numerator"), setOf("denominator", "numerator"))
        return ScopeTime.newBuilder().setTicks(o.member("ticks")!!.readS64())
            .setRate(Rational.newBuilder().setNumerator(rate.member("numerator")!!.readS64()).setDenominator(rate.member("denominator")!!.readU64()))
            .build()
    }

    private fun J.readScalar(): MetadataScalar {
        val o = this as? JO ?: refuse("object expected")
        if (o.members.size != 1) refuse("a metadata scalar carries exactly one arm")
        val (name, arm) = o.members.single()
        val built = MetadataScalar.newBuilder()
        when (name) {
            "text" -> built.setText(arm.text())
            "boolean" -> built.setBoolean(arm.readBool())
            "integer" -> built.setInteger(arm.readS64())
            "number" -> built.setNumber(arm.readDouble())
            "decimal" -> built.setDecimal(Decimal.newBuilder().setValue(arm.asObject(setOf("value"), setOf("value")).member("value")!!.text()))
            "instant" -> {
                val instant = arm.asObject(setOf("nanos", "unixSeconds"), setOf("nanos", "unixSeconds"))
                built.setInstant(Instant.newBuilder().setNanos(instant.member("nanos")!!.readU32()).setUnixSeconds(instant.member("unixSeconds")!!.readS64()))
            }
            else -> refuse("metadata scalar arm $name is not representable in af-segment.v1")
        }
        return built.build()
    }

    private fun J.readSample(): SimulationSample {
        val o = asObject(
            setOf("channelId", "deliveredOrdinal", "faultIds", "tick", "time", "numeric", "digital", "eventId"),
            setOf("channelId", "deliveredOrdinal", "faultIds", "tick", "time"),
        )
        val built = SimulationSample.newBuilder()
            .setChannelId(o.member("channelId")!!.readId())
            .setDeliveredOrdinal(o.member("deliveredOrdinal")!!.readU64())
            .setTick(o.member("tick")!!.readU64())
            .setTime(o.member("time")!!.readTime())
        o.member("faultIds")!!.list().forEach { built.addFaultIds(it.readId()) }
        val arms = listOf("numeric", "digital", "eventId").filter { o.member(it) != null }
        if (arms.size != 1) refuse("a sample carries exactly one value arm")
        when (arms.single()) {
            "numeric" -> built.setNumeric(o.member("numeric")!!.readDouble())
            "digital" -> built.setDigital(o.member("digital")!!.readBool())
            else -> built.setEventId(o.member("eventId")!!.readId())
        }
        return built.build()
    }

    private fun J.readEvent(): SimulationEvent {
        val o = asObject(
            setOf("channelId", "duration", "eventId", "faultId", "fields", "kind", "start"),
            setOf("channelId", "eventId", "fields", "kind", "start"),
        )
        val built = SimulationEvent.newBuilder()
            .setChannelId(o.member("channelId")!!.readId())
            .setEventId(o.member("eventId")!!.readId())
            .setKind(o.member("kind")!!.text())
            .setStart(o.member("start")!!.readTime())
        o.member("duration")?.let { built.setDuration(it.readTime()) }
        o.member("faultId")?.let { built.setFaultId(it.readId()) }
        for (field in o.member("fields")!!.list()) {
            val entry = field.asObject(setOf("name", "value"), setOf("name", "value"))
            built.addFields(MetadataEntry.newBuilder().setName(entry.member("name")!!.text()).setValue(entry.member("value")!!.readScalar()))
        }
        return built.build()
    }

    private fun J.readGap(): SimulationGap {
        val o = asObject(
            setOf("channelId", "faultId", "kind", "startTick", "tickCount"),
            setOf("faultId", "kind", "startTick", "tickCount"),
        )
        val built = SimulationGap.newBuilder()
            .setFaultId(o.member("faultId")!!.readId())
            .setKind(o.member("kind")!!.text())
            .setStartTick(o.member("startTick")!!.readU64())
            .setTickCount(o.member("tickCount")!!.readU64())
        o.member("channelId")?.let { built.setChannelId(it.readId()) }
        return built.build()
    }

    private fun strictRead(text: String): SimulationDataSegment {
        val names = setOf("encodingProfile", "events", "executionProfile", "gaps", "records", "startTick", "tickCount")
        val o = StrictJson(text).parse().asObject(names, names)
        val built = SimulationDataSegment.newBuilder()
            .setEncodingProfile(o.member("encodingProfile")!!.text())
            .setExecutionProfile(o.member("executionProfile")!!.text())
            .setStartTick(o.member("startTick")!!.readU64())
            .setTickCount(o.member("tickCount")!!.readU64())
        o.member("records")!!.list().forEach { built.addRecords(it.readSample()) }
        o.member("events")!!.list().forEach { built.addEvents(it.readEvent()) }
        o.member("gaps")!!.list().forEach { built.addGaps(it.readGap()) }
        val segment = built.build()
        semanticCheck(segment)
        if (encodeSegment(segment) != text) refuse("the text is not the canonical byte form")
        return segment
    }

    // ---------------------------------------------------------------------------------------------------------
    // Segment vectors
    // ---------------------------------------------------------------------------------------------------------

    private fun modelId(text: String): Id = id(text.replace("-", ""))

    private fun modelTime(value: JsonObject): ScopeTime {
        val rate = value.getAsJsonObject("rate")
        return ScopeTime.newBuilder().setTicks(value["ticks"].asString.toLong())
            .setRate(Rational.newBuilder().setNumerator(rate["numerator"].asString.toLong())
                .setDenominator(java.lang.Long.parseUnsignedLong(rate["denominator"].asString)))
            .build()
    }

    private fun modelScalar(value: JsonObject): MetadataScalar {
        val built = MetadataScalar.newBuilder()
        when {
            value.has("text") -> built.setText(value["text"].asString)
            value.has("boolean") -> built.setBoolean(value["boolean"].asBoolean)
            value.has("integer") -> built.setInteger(value["integer"].asString.toLong())
            value.has("number") -> built.setNumber(value["number"].asString.toDouble())
            value.has("decimal") -> built.setDecimal(Decimal.newBuilder().setValue(value["decimal"].asString))
            value.has("instant") -> {
                val instant = value.getAsJsonObject("instant")
                built.setInstant(Instant.newBuilder().setUnixSeconds(instant["unixSeconds"].asString.toLong())
                    .setNanos(java.lang.Long.parseUnsignedLong(instant["nanos"].asString).toInt()))
            }
            else -> error("Unknown scalar model")
        }
        return built.build()
    }

    private fun modelSegment(model: JsonObject): SimulationDataSegment {
        val built = SimulationDataSegment.newBuilder()
            .setEncodingProfile(model["encodingProfile"].asString)
            .setExecutionProfile(model["executionProfile"].asString)
            .setStartTick(java.lang.Long.parseUnsignedLong(model["startTick"].asString))
            .setTickCount(java.lang.Long.parseUnsignedLong(model["tickCount"].asString))
        for (element in model.getAsJsonArray("records")) {
            val record = element.asJsonObject
            val sample = SimulationSample.newBuilder()
                .setChannelId(modelId(record["channelId"].asString))
                .setTick(java.lang.Long.parseUnsignedLong(record["tick"].asString))
                .setDeliveredOrdinal(java.lang.Long.parseUnsignedLong(record["deliveredOrdinal"].asString))
                .setTime(modelTime(record.getAsJsonObject("time")))
            record.getAsJsonArray("faultIds").forEach { sample.addFaultIds(modelId(it.asString)) }
            val arm = record.getAsJsonObject("value")
            when {
                arm.has("numeric") -> sample.setNumeric(arm["numeric"].asString.toDouble())
                arm.has("digital") -> sample.setDigital(arm["digital"].asBoolean)
                arm.has("eventId") -> sample.setEventId(modelId(arm["eventId"].asString))
                else -> error("Unknown sample arm")
            }
            built.addRecords(sample)
        }
        for (element in model.getAsJsonArray("events")) {
            val event = element.asJsonObject
            val builder = SimulationEvent.newBuilder()
                .setEventId(modelId(event["eventId"].asString))
                .setChannelId(modelId(event["channelId"].asString))
                .setKind(event["kind"].asString)
                .setStart(modelTime(event.getAsJsonObject("start")))
            if (event.has("duration")) builder.setDuration(modelTime(event.getAsJsonObject("duration")))
            if (event.has("faultId")) builder.setFaultId(modelId(event["faultId"].asString))
            for (field in event.getAsJsonArray("fields")) {
                builder.addFields(MetadataEntry.newBuilder().setName(field.asJsonObject["name"].asString)
                    .setValue(modelScalar(field.asJsonObject.getAsJsonObject("value"))))
            }
            built.addEvents(builder)
        }
        for (element in model.getAsJsonArray("gaps")) {
            val gap = element.asJsonObject
            val builder = SimulationGap.newBuilder()
                .setStartTick(java.lang.Long.parseUnsignedLong(gap["startTick"].asString))
                .setTickCount(java.lang.Long.parseUnsignedLong(gap["tickCount"].asString))
                .setFaultId(modelId(gap["faultId"].asString))
                .setKind(gap["kind"].asString)
            if (gap.has("channelId")) builder.setChannelId(modelId(gap["channelId"].asString))
            built.addGaps(builder)
        }
        return built.build()
    }

    private fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }

    private fun bits(value: Double): Long = java.lang.Double.doubleToRawLongBits(value)

    private fun runSegment(fixture: JsonObject) {
        check(fixture["schemaVersion"].asString == "con-25-af-segment.v1")
        check(fixture["evidenceClass"].asString == "offline-contract-only-no-simulator-or-native-reader")
        val profile = fixture.getAsJsonObject("profile")
        check(profile["id"].asString == "af-segment.v1" && profile["executionProfile"].asString == "af-sim.v1")
        check(profile.getAsJsonArray("rules").size() == 13)

        // Generated field-number facts for the four records.
        check(fieldNumbers(SimulationEvent::class.java) == mapOf(
            "EVENT_ID" to 1, "CHANNEL_ID" to 2, "START" to 3, "DURATION" to 4, "KIND" to 5, "FIELDS" to 6, "FAULT_ID" to 7))
        check(fieldNumbers(SimulationSample::class.java) == mapOf(
            "CHANNEL_ID" to 1, "TICK" to 2, "DELIVERED_ORDINAL" to 3, "TIME" to 4, "NUMERIC" to 5, "DIGITAL" to 6, "EVENT_ID" to 7, "FAULT_IDS" to 8))
        check(fieldNumbers(SimulationGap::class.java) == mapOf(
            "CHANNEL_ID" to 1, "START_TICK" to 2, "TICK_COUNT" to 3, "FAULT_ID" to 4, "KIND" to 5))
        check(fieldNumbers(SimulationDataSegment::class.java) == mapOf(
            "ENCODING_PROFILE" to 1, "EXECUTION_PROFILE" to 2, "START_TICK" to 3, "TICK_COUNT" to 4, "RECORDS" to 5, "EVENTS" to 6, "GAPS" to 7))

        val vectors = fixture.getAsJsonArray("vectors").map { it.asJsonObject }
        val vectorIds = vectors.map { it["id"].asString }
        check(vectorIds.size == positiveSegmentIds.size && vectorIds.toSet().size == vectorIds.size && vectorIds.toSet() == positiveSegmentIds.toSet())
        val refusals = fixture.getAsJsonArray("refusals").map { it.asJsonObject }
        val refusalFixtureIds = refusals.map { it["id"].asString }
        check(refusalFixtureIds.size == refusalIds.size && refusalFixtureIds.toSet().size == refusalFixtureIds.size && refusalFixtureIds.toSet() == refusalIds.toSet())

        val consumed = mutableSetOf<String>()
        val decodedById = mutableMapOf<String, SimulationDataSegment>()
        val canonicalTexts = mutableSetOf<String>()
        for (vector in vectors) {
            val id = vector["id"].asString
            check(consumed.add(id)) { "Duplicate CON.25 af-segment vector consumption: $id" }
            val model = vector.getAsJsonObject("segment")
            val canonical = vector["canonicalJson"].asString
            canonicalTexts.add(canonical)

            // (a) ENCODE: generated message from the model, in-test canonical encoder, bytes and SHA-256.
            val message = modelSegment(model)
            semanticCheck(message)
            val encoded = encodeSegment(message)
            check(encoded == canonical) { "$id canonical encoding differs from the fixture" }
            val utf8 = encoded.toByteArray(Charsets.UTF_8)
            check(utf8.size == vector["utf8Bytes"].asInt) { "$id utf8Bytes" }
            check(sha256Hex(utf8) == vector["sha256"].asString) { "$id sha256" }
            check(utf8.size < 3 || !(utf8[0] == 0xEF.toByte() && utf8[1] == 0xBB.toByte() && utf8[2] == 0xBF.toByte()))

            // Protobuf round trip preserves optional, oneof and repeated presence.
            val decoded = roundTrip(message) { SimulationDataSegment.parseFrom(it) }
            check(decoded.hasEncodingProfile() && decoded.hasExecutionProfile() && decoded.hasStartTick() && decoded.hasTickCount())
            check(decoded.recordsCount == model.getAsJsonArray("records").size())
            check(decoded.eventsCount == model.getAsJsonArray("events").size())
            check(decoded.gapsCount == model.getAsJsonArray("gaps").size())
            for ((index, element) in model.getAsJsonArray("records").withIndex()) {
                val arm = element.asJsonObject.getAsJsonObject("value")
                val record = decoded.getRecords(index)
                val expectedCase = when {
                    arm.has("numeric") -> SimulationSample.ValueCase.NUMERIC
                    arm.has("digital") -> SimulationSample.ValueCase.DIGITAL
                    else -> SimulationSample.ValueCase.EVENT_ID
                }
                check(record.valueCase == expectedCase)
                check(record.faultIdsCount == element.asJsonObject.getAsJsonArray("faultIds").size())
                if (arm.has("digital")) check(record.digital == arm["digital"].asBoolean)
                if (arm.has("numeric")) check(bits(record.numeric) == bits(arm["numeric"].asString.toDouble()))
            }
            for ((index, element) in model.getAsJsonArray("events").withIndex()) {
                val event = decoded.getEvents(index)
                check(event.hasDuration() == element.asJsonObject.has("duration"))
                check(event.hasFaultId() == element.asJsonObject.has("faultId"))
                check(event.fieldsCount == element.asJsonObject.getAsJsonArray("fields").size())
            }
            for ((index, element) in model.getAsJsonArray("gaps").withIndex()) {
                check(decoded.getGaps(index).hasChannelId() == element.asJsonObject.has("channelId"))
            }
            check(encodeSegment(decoded) == canonical)

            // (b) STRICT READ of the canonical text: accepted, equal to the generated message, byte-identical re-encode.
            val read = strictRead(canonical)
            check(read == message && encodeSegment(read) == canonical)
            decodedById[id] = decoded
        }
        check(consumed == positiveSegmentIds.toSet()) { "Every CON.25 af-segment vector must be consumed exactly once" }
        check(canonicalTexts.size == vectors.size)

        verifyBinary64(decodedById.getValue("binary64-bit-words-preserve-sign-and-extremes"))
        verifyEdges(decodedById)

        val consumedRefusals = mutableSetOf<String>()
        for (refusal in refusals) {
            val id = refusal["id"].asString
            check(consumedRefusals.add(id)) { "Duplicate CON.25 refusal consumption: $id" }
            check(refusal["reason"].asString.isNotBlank())
            val text = refusal["canonicalJson"].asString
            check(text !in canonicalTexts) { "$id must differ from every positive text" }
            val refused = try {
                strictRead(text)
                false
            } catch (_: Refused) {
                true
            }
            check(refused) { "Strict reader accepted refusal vector $id" }
        }
        check(consumedRefusals == refusalIds.toSet()) { "Every CON.25 refusal must be consumed exactly once" }
        verifyRefusalDiscrimination(canonicalTexts)
    }

    private fun verifyBinary64(segment: SimulationDataSegment) {
        val words = segment.recordsList.map { bits(it.numeric) }
        check(words == listOf(
            java.lang.Long.MIN_VALUE, 0L, 1L, 0x7fefffffffffffffL, 0x3fb999999999999aL, -0x4008000000000000L,
        )) { "binary64 words" }
        check(segment.recordsList.map { it.deliveredOrdinal } == (0L..5L).toList())
    }

    private fun verifyEdges(decoded: Map<String, SimulationDataSegment>) {
        val integral = decoded.getValue("integral-extremes-use-exact-strings")
        check(integral.startTick == -2L && integral.recordsList.map { it.tick } == listOf(-2L, -1L))
        check(integral.recordsList.map { it.time.ticks } == listOf(Long.MIN_VALUE, Long.MAX_VALUE))
        val text = decoded.getValue("text-metadata-escapes-and-unicode").getEvents(0).getFields(0).value.text
        check(text == "a\"b\\c\n\t\u0001\u001b\u007fé中😀")
        val mixed = decoded.getValue("numeric-digital-and-event-samples-in-delivered-order")
        check(mixed.getEvents(0).fieldsList.map { it.value.valueCase } == listOf(
            MetadataScalar.ValueCase.TEXT, MetadataScalar.ValueCase.BOOLEAN, MetadataScalar.ValueCase.INTEGER,
            MetadataScalar.ValueCase.NUMBER, MetadataScalar.ValueCase.DECIMAL, MetadataScalar.ValueCase.INSTANT,
        ))
        check(mixed.getEvents(0).hasDuration() && !mixed.getEvents(1).hasDuration() && !mixed.getEvents(0).hasFaultId())
        val gaps = decoded.getValue("gap-and-fault-markers-with-and-without-channel")
        check(gaps.gapsList.map { it.hasChannelId() } == listOf(true, false, true))
        check(gaps.gapsList.map { it.kind } == listOf("drop", "disconnect", "malformed"))
        check(!gaps.getRecords(0).digital && gaps.getRecords(0).valueCase == SimulationSample.ValueCase.DIGITAL)
        val empty = decoded.getValue("empty-segment-keeps-every-ordered-repeated-field")
        check(empty.recordsCount == 0 && empty.eventsCount == 0 && empty.gapsCount == 0 && empty.hasStartTick() && empty.hasTickCount())
        val duplicate = decoded.getValue("duplicate-delivery-differs-only-by-ordinal-and-fault-marker")
        check(duplicate.getRecords(0).copyWithoutOrdinalAndFaults() == duplicate.getRecords(1).copyWithoutOrdinalAndFaults())
        check(duplicate.getRecords(0).faultIdsCount == 0 && duplicate.getRecords(1).faultIdsCount == 1)
    }

    private fun SimulationSample.copyWithoutOrdinalAndFaults(): SimulationSample =
        toBuilder().clearDeliveredOrdinal().clearFaultIds().build()

    /** Proves the message-level validator and encoder are discriminating on their own, not only through byte equality. */
    private fun verifyRefusalDiscrimination(canonicalTexts: Set<String>) {
        check(canonicalTexts.isNotEmpty())
        val withEvents = strictRead(canonicalTexts.single { it.contains("\"text\":\"edge\"") })
        val withGaps = strictRead(canonicalTexts.single { it.contains("\"kind\":\"malformed\"") })
        val zeroId = Id.newBuilder().setValue(ByteString.copyFrom(ByteArray(16))).build()
        val mutations: List<Pair<String, SimulationDataSegment>> = listOf(
            "wrong encoding profile" to withGaps.toBuilder().setEncodingProfile("af-segment.v2").build(),
            "wrong execution profile" to withGaps.toBuilder().setExecutionProfile("af-sim.v2").build(),
            "unknown gap kind" to withGaps.toBuilder().setGaps(0, withGaps.getGaps(0).toBuilder().setKind("explode")).build(),
            "zero Id" to withGaps.toBuilder().setRecords(0, withGaps.getRecords(0).toBuilder().setChannelId(zeroId)).build(),
            "missing oneof" to withGaps.toBuilder().setRecords(0, withGaps.getRecords(0).toBuilder().clearValue()).build(),
            "descending ordinals" to withGaps.toBuilder()
                .setRecords(0, withGaps.getRecords(0).toBuilder().setDeliveredOrdinal(5L))
                .setRecords(1, withGaps.getRecords(1).toBuilder().setDeliveredOrdinal(5L)).build(),
            "nonfinite numeric" to withEvents.toBuilder().setRecords(0, withEvents.getRecords(0).toBuilder().setNumeric(Double.NaN)).build(),
            "zero rate denominator" to withEvents.toBuilder().setEvents(0, withEvents.getEvents(0).toBuilder()
                .setStart(withEvents.getEvents(0).start.toBuilder().setRate(Rational.newBuilder().setNumerator(1000L).setDenominator(0L)))).build(),
            "resource arm" to withEvents.toBuilder().setEvents(0, withEvents.getEvents(0).toBuilder()
                .setFields(0, MetadataEntry.newBuilder().setName("r").setValue(MetadataScalar.newBuilder().setResource(ResourceRef.getDefaultInstance())))).build(),
            "unpaired surrogate text" to withEvents.toBuilder().setEvents(0, withEvents.getEvents(0).toBuilder()
                .setFields(0, MetadataEntry.newBuilder().setName("t").setValue(MetadataScalar.newBuilder().setText("\uD800")))).build(),
            "missing gap fault id" to withGaps.toBuilder().setGaps(0, withGaps.getGaps(0).toBuilder().clearFaultId()).build(),
            "bad event kind" to withEvents.toBuilder().setEvents(0, withEvents.getEvents(0).toBuilder().setKind("has space")).build(),
        )
        for ((label, mutated) in mutations) {
            val refused = try {
                semanticCheck(mutated)
                false
            } catch (_: Refused) {
                true
            }
            check(refused) { "Semantic validation accepted: $label" }
        }
        // The encoder itself refuses what af-segment.v1 cannot represent.
        for ((label, mutated) in mutations.filter { it.first in setOf("missing oneof", "nonfinite numeric", "resource arm", "unpaired surrogate text") }) {
            val refused = try {
                encodeSegment(mutated)
                false
            } catch (_: Refused) {
                true
            }
            check(refused) { "Encoder emitted unrepresentable content: $label" }
        }
        // Positive control: the unmutated messages remain valid after the same builder round trip.
        semanticCheck(withEvents.toBuilder().build())
        semanticCheck(withGaps.toBuilder().build())
    }
}
