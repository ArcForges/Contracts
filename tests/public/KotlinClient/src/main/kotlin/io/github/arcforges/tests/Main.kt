// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.google.gson.JsonParser
import com.google.protobuf.InvalidProtocolBufferException
import io.github.arcforges.contracts.fixtures.ContractFixtures
import io.github.arcforges.contracts.hello.v1.HelloServiceGrpcKt.HelloServiceCoroutineStub
import io.github.arcforges.contracts.hello.v1.SayHelloRequest
import io.github.arcforges.contracts.hello.v1.sayHelloRequest
import io.grpc.Status
import io.grpc.StatusException
import io.grpc.okhttp.OkHttpChannelBuilder
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking

fun main(args: Array<String>) = runBlocking {
    val expectedIdentity = JsonParser.parseString(java.io.File(checkNotNull(System.getenv("ARCFORGES_EXPECTED_BUILD"))).readText()).asJsonObject
    for (module in listOf("contracts-proto", "contracts-client", "contract-fixtures")) {
        val resource = checkNotNull(ContractFixtures::class.java.classLoader.getResourceAsStream("META-INF/arcforges/$module/build-identity.json"))
        val identity = resource.bufferedReader(Charsets.UTF_8).use { JsonParser.parseReader(it).asJsonObject }
        check(identity["build"] == expectedIdentity) { "Published JVM build identity mismatch: $module" }
        check(identity.getAsJsonObject("axes").getAsJsonObject("ContractSet").getAsJsonArray("values")[0].asJsonObject["version"].asString == "1")
    }
    println("Published JVM module build identities verified.")
    val fixture = ContractFixtures.openHello().bufferedReader(Charsets.UTF_8).use { JsonParser.parseReader(it).asJsonObject }
    check(sayHelloRequest { name = "World" }.toByteArray().contentEquals(byteArrayOf(10, 5, 87, 111, 114, 108, 100)))
    val unknown = byteArrayOf(10, 1, 65, 120, 7)
    check(SayHelloRequest.parseFrom(unknown).toByteArray().contentEquals(unknown))
    try {
        SayHelloRequest.parseFrom(byteArrayOf(10, 3, 65))
        error("Truncated protobuf was accepted")
    } catch (_: InvalidProtocolBufferException) { }
    val channel = OkHttpChannelBuilder.forAddress("127.0.0.1", args.single().toInt()).usePlaintext().build()
    try {
        val client = HelloServiceCoroutineStub(channel).withDeadlineAfter(20, TimeUnit.SECONDS)
        for (entry in fixture.getAsJsonArray("cases")) {
            val case = entry.asJsonObject
            val request = sayHelloRequest { name = case["name"].asString }
            check(SayHelloRequest.parseFrom(request.toByteArray()) == request)
            check(client.sayHello(request).message == case["message"].asString)
        }
        try {
            client.sayHello(sayHelloRequest { name = "" })
            error("Server accepted an empty name")
        } catch (error: StatusException) {
            check(error.status.code == Status.Code.valueOf(fixture["emptyNameStatus"].asString))
        }
    } finally {
        channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS)
    }
    println("Kotlin archive consumer: published fixture, lite wire and real gRPC success/error checks passed.")
}
