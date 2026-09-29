// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.protobuf.ByteString
import io.github.arcforges.contracts.fixtures.ContractFixtures
import io.github.arcforges.contracts.foundation.v1.Id
import io.github.arcforges.contracts.foundation.v1.Instant
import io.github.arcforges.contracts.foundation.v1.PageRequest
import io.github.arcforges.contracts.foundation.v1.Rational
import io.github.arcforges.contracts.foundation.v1.Revision
import io.github.arcforges.contracts.simulation.v1.AstNode
import io.github.arcforges.contracts.simulation.v1.BinaryExpression
import io.github.arcforges.contracts.simulation.v1.FunctionExpression
import io.github.arcforges.contracts.simulation.v1.SimulationProfile
import io.github.arcforges.contracts.simulation.v1.SimulationRun
import io.github.arcforges.contracts.simulation.v1.SimulationServiceClientInterface
import io.github.arcforges.contracts.simulation.v1.UnaryExpression
import java.lang.reflect.Modifier
import java.util.Base64

internal object SimulationCases {
    fun run() {
        val fixture = ContractFixtures::class.java.getResourceAsStream("/arcforges/fixtures/con-21-simulation.json")
            ?.bufferedReader(Charsets.UTF_8)?.use { JsonParser.parseReader(it).asJsonObject }
            ?: error("CON.21 public simulation fixture is missing from the candidate")

        val operations = fixture.getAsJsonArray("operations").map { it.asJsonObject }
        check(operations.size == fixture.get("operationCount").asInt && operations.size == 13)
        val expectedMethods = operations.map { lowerCamel(it.get("method").asString) }.toSet()
        check(expectedMethods.size == operations.size)
        val declaredApiMethods = SimulationServiceClientInterface::class.java.declaredMethods
            .filter { Modifier.isAbstract(it.modifiers) && !it.isSynthetic }
            .map { it.name }
        val actualMethods = declaredApiMethods.toSet()
        check(declaredApiMethods.size == operations.size && actualMethods == expectedMethods) {
            "Simulation Connect API mismatch: expected=$expectedMethods actual=$declaredApiMethods"
        }
        val operationProfile = fixture.getAsJsonObject("operationProfile")
        check(operationProfile.get("kind").asString == "proto"
            && operationProfile.get("source").asString == "public/proto/arcforges/simulation/v1/simulation.proto"
            && operationProfile.get("scope").asString == "product-owner"
            && operationProfile.get("surface").asString == "public"
            && operationProfile.get("profile").asString == "human-owner"
            && operationProfile.get("sourceRule").asString == "docs/architecture/contracts/01-public-api-operations.md#91-arcscope-cloud-simulator"
            && operationProfile.get("capability").isJsonNull
            && operationProfile.get("approval").asString == "none"
            && !operationProfile.get("stepUp").asBoolean
            && !operationProfile.get("localPresence").asBoolean
            && operationProfile.get("egress").asString == "none"
            && !operationProfile.get("patEligible").asBoolean
            && operationProfile.getAsJsonArray("actorKinds").map { it.asString } == listOf("human"))
        for (operation in operations) {
            val idempotency = operation.get("class").asString
            val (risk, compatibility) = when (idempotency) {
                "Q" -> "R1" to "AO"
                "CC", "IW" -> "R2" to "FR"
                "NI" -> "R1" to "FR"
                else -> error("Unknown simulation idempotency class: $idempotency")
            }
            check(operation.get("risk").asString == risk && operation.get("compatibility").asString == compatibility) {
                operation.get("operationId").asString + " authorization profile"
            }
        }

        val allowedStates = fixture.getAsJsonArray("states").map { it.asString }.toSet()
        val rejectedStates = fixture.getAsJsonArray("stateRejected").map { it.asString }
        val allowedExtents = fixture.getAsJsonArray("extents").map { it.asString }.toSet()
        val rejectedExtents = fixture.getAsJsonArray("extentRejected").map { it.asString }
        check(allowedStates == setOf("queued", "starting", "running", "pausing", "paused", "stopping", "canceled", "succeeded", "failed"))
        check(rejectedStates == listOf("active", "completed", "cancelled", "unknown"))
        check(rejectedStates.none { it in allowedStates })
        check(allowedExtents == setOf("complete", "partial"))
        check(rejectedExtents == listOf("terminal", "full", "unknown"))
        check(rejectedExtents.none { it in allowedExtents })

        val base = fixture.getAsJsonObject("runShapeBase")
        val runVectors = fixture.getAsJsonArray("runExtentVectors").map { it.asJsonObject }
        check(runVectors.map { it.get("id").asString } == listOf(
            "active-partial-prefix", "succeeded-complete-range", "canceled-partial-range", "unknown-state-refused", "unsupported-extent-refused"))
        for (item in runVectors) {
            val state = item.get("state").asString
            val extent = item.get("extent").asString
            val logicalEnd = item.get("logicalEnd").asString.toLong()
            val valid = state in allowedStates && extent in allowedExtents
            check(valid == item.get("valid").asBoolean) { item.get("id").asString }
            val run = simulationRun(base, state, extent, logicalEnd)
            check(SimulationRun.parseFrom(run.toByteArray()) == run) { item.get("id").asString + " binary round-trip" }
        }

        val profile = fixture.getAsJsonObject("profile")
        val executionProfile = profile.get("executionProfile").asString
        val encodingProfile = profile.get("encodingProfile").asString
        val clockModes = profile.getAsJsonArray("clockModes").map { it.asString }.toSet()
        check(fixture.getAsJsonArray("generatorKinds").map { it.asString } == listOf(
            "constant", "sine", "square", "triangle", "sawtooth", "noise", "randomWalk", "pulse", "stepSequence", "csv"))
        check(fixture.getAsJsonArray("faultKinds").map { it.asString } == listOf(
            "latency", "jitter", "drop", "duplicate", "reorder", "disconnect", "malformed", "outlier"))
        val profileVectors = profile.getAsJsonArray("vectors").map { it.asJsonObject }
        check(profileVectors.map { it.get("id").asString } == listOf(
            "minimum-profile", "maximum-batch-profile", "zero-sample-count-refused", "zero-batch-refused",
            "oversized-batch-refused", "zero-rate-denominator-refused", "unsupported-execution-profile-refused"))
        for (item in profileVectors) {
            val value = item.getAsJsonObject("value")
            val rate = value.getAsJsonObject("rate")
            val valid = value.get("sampleCount").asString.toLong() >= 1L
                && value.get("batchSamples").asInt in 1..65536
                && rate.get("denominator").asString.toLong() >= 1L
                && value.get("executionProfile").asString == executionProfile
                && value.get("encodingProfile").asString == encodingProfile
                && value.get("clockMode").asString in clockModes
                && value.get("generatorVersion").asString.matches(Regex("^[A-Za-z0-9._:/-]{1,128}$"))
            check(valid == item.get("valid").asBoolean) { item.get("id").asString }
            if (valid) {
                val message = SimulationProfile.newBuilder()
                    .setSampleCount(value.get("sampleCount").asString.toLong())
                    .setBatchSamples(value.get("batchSamples").asInt)
                    .setRate(Rational.newBuilder()
                        .setNumerator(rate.get("numerator").asString.toLong())
                        .setDenominator(rate.get("denominator").asString.toLong()))
                    .setExecutionProfile(value.get("executionProfile").asString)
                    .setEncodingProfile(value.get("encodingProfile").asString)
                    .setClockMode(value.get("clockMode").asString)
                    .setGeneratorVersion(value.get("generatorVersion").asString)
                    .build()
                check(SimulationProfile.parseFrom(message.toByteArray()) == message) { item.get("id").asString + " binary round-trip" }
            }
        }

        val astVectors = fixture.getAsJsonArray("astVectors").map { it.asJsonObject }
        check(astVectors.map { it.get("id").asString } == listOf(
            "constant-expression", "variable-expression", "unary-expression", "binary-expression", "function-expression",
            "unrecognized-expression", "missing-expression", "multiple-oneof-arms-refused"))
        for (item in astVectors) {
            val value = item.getAsJsonObject("value")
            val knownArms = setOf("constant", "variable", "unary", "binary", "function")
            val selectedArms = value.keySet().intersect(knownArms)
            val valid = selectedArms.size == 1 && value.keySet() == selectedArms
            check(valid == item.get("valid").asBoolean) { item.get("id").asString }
            if (valid) {
                val node = astNode(value)
                check(AstNode.parseFrom(node.toByteArray()) == node) { item.get("id").asString + " binary round-trip" }
            }
        }

        val pageLimits = fixture.getAsJsonObject("listRuns").getAsJsonArray("pageLimits").map { it.asJsonObject }
        check(pageLimits.map { it.get("id").asString } == listOf("default", "minimum", "maximum", "zero", "above-maximum"))
        for (item in pageLimits) {
            val limit = item.get("limit")
            val valid = limit.isJsonNull || limit.asInt in 1..200
            check(valid == item.get("valid").asBoolean) { item.get("id").asString }
            if (!limit.isJsonNull) {
                val page = PageRequest.newBuilder().setLimit(limit.asInt).build()
                check(PageRequest.parseFrom(page.toByteArray()) == page) { item.get("id").asString + " binary round-trip" }
            }
        }

        val listRuns = fixture.getAsJsonObject("listRuns")
        val authorization = listRuns.getAsJsonObject("authorization")
        check(authorization.get("membership").asString == "current-workspace")
        check(authorization.get("role").asString == "read" && authorization.get("productId").asString == "arcscope")
        check(authorization.get("recheckEveryPage").asBoolean)
        check(listRuns.get("filters").asJsonArray.map { it.asString } == listOf("exact scenarioVersionId", "exact simulation_run state"))
        check(listRuns.get("order").asJsonArray.map { it.asString } == listOf("createdAt descending", "runId descending"))
        check(listRuns.get("pageStateBinds").asJsonArray.map { it.asString } ==
            listOf("realm", "workspace", "actor", "recoveryGeneration", "filters", "sort", "schema", "snapshot"))
        check(listRuns.get("includesRetainedPartialAndTerminalRuns").asBoolean)
        check(!listRuns.get("requiresKnownRunId").asBoolean && !listRuns.get("requiresTerminalNotification").asBoolean)
        println("CON.21 Kotlin Connect API and independent offline vectors passed; no simulator runtime executed.")
    }

    private fun simulationRun(base: JsonObject, state: String, extent: String, logicalEnd: Long): SimulationRun {
        fun id(key: String): Id {
            val encoded = base.getAsJsonObject(key).get("value").asString
            return Id.newBuilder().setValue(ByteString.copyFrom(Base64.getDecoder().decode(encoded))).build()
        }
        val revision = base.getAsJsonObject("revision").get("value").asString.toLong()
        val createdAt = base.getAsJsonObject("createdAt")
        return SimulationRun.newBuilder()
            .setRunId(id("runId"))
            .setScenarioVersionId(id("scenarioVersionId"))
            .setRevision(Revision.newBuilder().setValue(revision))
            .setCommittedSequence(base.get("committedSequence").asString.toLong())
            .setCreatedAt(Instant.newBuilder()
                .setUnixSeconds(createdAt.get("unixSeconds").asString.toLong())
                .setNanos(createdAt.get("nanos").asInt))
            .setState(state)
            .setExtent(extent)
            .setLogicalEnd(logicalEnd)
            .build()
    }

    private fun astNode(value: JsonObject): AstNode = when {
        value.has("constant") -> AstNode.newBuilder().setConstant(value.get("constant").asDouble).build()
        value.has("variable") -> AstNode.newBuilder().setVariable(value.get("variable").asString).build()
        value.has("unary") -> {
            val expression = value.getAsJsonObject("unary")
            AstNode.newBuilder().setUnary(UnaryExpression.newBuilder()
                .setOperator(expression.get("operator").asString)
                .setOperand(astNode(expression.getAsJsonObject("operand"))))
                .build()
        }
        value.has("binary") -> {
            val expression = value.getAsJsonObject("binary")
            AstNode.newBuilder().setBinary(BinaryExpression.newBuilder()
                .setOperator(expression.get("operator").asString)
                .setLeft(astNode(expression.getAsJsonObject("left")))
                .setRight(astNode(expression.getAsJsonObject("right"))))
                .build()
        }
        value.has("function") -> {
            val expression = value.getAsJsonObject("function")
            val function = FunctionExpression.newBuilder().setFunction(expression.get("function").asString)
            expression.getAsJsonArray("arguments").map { astNode(it.asJsonObject) }.forEach { function.addArguments(it) }
            AstNode.newBuilder().setFunction(function).build()
        }
        else -> error("No known AST oneof arm")
    }

    private fun lowerCamel(value: String): String = value.replaceFirstChar { it.lowercase() }
}
