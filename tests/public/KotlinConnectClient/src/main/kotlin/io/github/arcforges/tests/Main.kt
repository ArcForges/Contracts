// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.tests

import com.connectrpc.Code
import com.connectrpc.ConnectException
import com.connectrpc.ProtocolClientConfig
import com.connectrpc.extensions.GoogleJavaLiteProtobufStrategy
import com.connectrpc.getOrThrow
import com.connectrpc.impl.ProtocolClient
import com.connectrpc.okhttp.ConnectOkHttpClient
import com.connectrpc.protocols.NetworkProtocol
import com.google.gson.JsonParser
import io.github.arcforges.contracts.fixtures.ContractFixtures
import io.github.arcforges.contracts.hello.v1.HelloServiceClient
import io.github.arcforges.contracts.hello.v1.HelloServiceClientInterface
import io.github.arcforges.contracts.hello.v1.SayHelloRequest
import io.github.arcforges.contracts.hello.v1.sayHelloRequest
import java.util.concurrent.atomic.AtomicInteger
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.OkHttpClient
import okhttp3.Protocol

fun main(args: Array<String>) = runBlocking {
    check(args.size == 2) { "Expected gRPC-Web and native gRPC fixture ports" }
    val fixture = ContractFixtures.openHello().bufferedReader(Charsets.UTF_8).use { JsonParser.parseReader(it).asJsonObject }
    for ((protocol, port) in listOf(NetworkProtocol.GRPC_WEB to args[0], NetworkProtocol.GRPC to args[1])) {
        val web = protocol == NetworkProtocol.GRPC_WEB
        val prefix = if (web) "/api" else ""
        val contentType = if (web) "application/grpc-web+proto" else "application/grpc+proto"
        val requests = AtomicInteger()
        val http = OkHttpClient.Builder()
            .protocols(listOf(if (web) Protocol.HTTP_1_1 else Protocol.H2_PRIOR_KNOWLEDGE))
            .addInterceptor { chain ->
                val request = chain.request()
                check(request.method == "POST")
                check(request.url.encodedPath == "$prefix/arcforges.hello.v1.HelloService/SayHello")
                check(request.body?.contentType().toString() == contentType)
                requests.incrementAndGet()
                chain.proceed(request)
            }
            .build()
        try {
            val client: HelloServiceClientInterface = HelloServiceClient(ProtocolClient(
                httpClient = ConnectOkHttpClient(http),
                config = ProtocolClientConfig(
                    host = "http://127.0.0.1:$port$prefix",
                    serializationStrategy = GoogleJavaLiteProtobufStrategy(),
                    networkProtocol = protocol,
                    ioCoroutineContext = Dispatchers.IO,
                    timeoutOracle = { 5.seconds },
                ),
            ))
            withTimeout(30.seconds) {
                for (entry in fixture.getAsJsonArray("cases")) {
                    val case = entry.asJsonObject
                    val request = sayHelloRequest { name = case["name"].asString }
                    check(SayHelloRequest.parseFrom(request.toByteArray()) == request)
                    check(client.sayHello(request).getOrThrow().message == case["message"].asString)
                }
                try {
                    client.sayHello(sayHelloRequest { name = "" }).getOrThrow()
                    error("Server accepted an empty name")
                } catch (error: ConnectException) {
                    check(error.code == Code.INVALID_ARGUMENT) { "Unexpected RPC status: ${error.code}" }
                    check(error.message?.contains("name must not be empty") == true)
                }
            }
            check(requests.get() == fixture.getAsJsonArray("cases").size() + 1)
        } finally {
            http.dispatcher.executorService.shutdown()
            http.connectionPool.evictAll()
        }
        println("Kotlin Connect archive consumer: real $protocol Hello success/error, binary protocol and base path checks passed.")
    }
}
