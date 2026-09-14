# ArcForges contracts-proto

`io.github.arcforges:contracts-proto` supplies generated Java protobuf-lite
messages, Kotlin message builders, the authored proto and its descriptor set.
The current schema is the Hello World packaging example, not a product API.

Use Java 17 and Kotlin 2.4.20 or a compatible newer Kotlin compiler. Android
applications consume this ordinary JVM JAR; they do not run protoc. This package
does not target Kotlin/Native or iOS. Runtime dependencies are declared in its
POM and Gradle module metadata, not bundled into the JAR. Apache-2.0.

```kotlin
import io.github.arcforges.contracts.hello.v1.sayHelloRequest

val request = sayHelloRequest { name = "World" }
val bytes = request.toByteArray()
```

For network calls, install `contracts-client` at the same exact version. See
[installation and channel ownership](https://github.com/ArcForges/Contracts/blob/main/docs/consuming.md).
