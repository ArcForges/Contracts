# Installing and using the packages

Choose a version whose main CI candidate and relevant registry job both passed.
The release manifest supplies the exact common version. An Actions artifact named
candidate is a tested archive; it becomes a registry package only after upload.
Versions such as `1.0.0-ci.12.1` below are illustrative, not an assertion that
this version exists.

## C#

A repository using central package management adds these entries to
`Directory.Packages.props`:

```xml
<Project>
  <PropertyGroup>
    <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <PackageVersion Include="ArcForges.Contracts.PublicApi" Version="1.0.0-ci.12.1" />
    <PackageVersion Include="Grpc.Net.Client" Version="2.83.0" />
  </ItemGroup>
</Project>
```

The application's project references them without inline versions:

```xml
<ItemGroup>
  <PackageReference Include="ArcForges.Contracts.PublicApi" />
  <PackageReference Include="Grpc.Net.Client" />
</ItemGroup>
```

Enable `RestorePackagesWithLockFile`, commit `packages.lock.json`, and use
`dotnet restore --locked-mode` in CI. nuget.org is the public source; no publishing
credentials are required for a consumer.

```csharp
using ArcForges.Contracts.Hello.V1;
using Grpc.Net.Client;

using var channel = GrpcChannel.ForAddress("http://localhost:50051");
var client = new HelloService.HelloServiceClient(channel);
var reply = await client.SayHelloAsync(
    new SayHelloRequest { Name = "World" },
    deadline: DateTime.UtcNow.AddSeconds(5));
Console.WriteLine(reply.Message);
```

The local example server can be run from the Contracts checkout after restore:

```text
dotnet run --project tests/public/HelloHost -- --grpc-port 50051 --web-port 50052
```

That server is a loopback test fixture. A real application supplies its own
service implementation, TLS endpoint and authentication.

## TypeScript / Web

The default npm package page and a fresh install without a version follow
`latest`, which CI advances to the newest published main build. Check that both
npm publication results passed and use their common version; registry uploads
are not an atomic operation across packages. Moving `latest` does not rewrite an
existing application's dependency version or lock file.

Install exact package versions and commit the application's lock:

```text
npm install --save-exact @arcforges/proto@1.0.0-ci.12.1 @arcforges/api-client@1.0.0-ci.12.1
```

```ts
import { createHelloClient } from "@arcforges/api-client";

const client = createHelloClient({ baseUrl: "http://localhost:50052" });
const reply = await client.sayHello({ name: "World" }, { timeoutMs: 5000 });
console.log(reply.message);
```

The endpoint serves gRPC-Web. For a browser on another origin, the application
must configure CORS; the bootstrap test uses Node fetch against loopback and
does not claim a browser integration test.

For serialization alone, use `@arcforges/proto` with `@bufbuild/protobuf`.
Generated service descriptors also work with the caller's compatible transport.

## Kotlin / Android

Add `mavenCentral()` to the application's dependency repositories. Add the exact
common release and the Android-compatible transport (the versions below are
examples for the Contracts release):

```kotlin
dependencies {
    implementation("io.github.arcforges:contracts-client:1.0.0-ci.12.1")
    implementation("io.grpc:grpc-okhttp:1.84.0")
    testImplementation("io.github.arcforges:contract-fixtures:1.0.0-ci.12.1")
}
```

`contracts-client` brings the matching `contracts-proto`, coroutine and gRPC
runtime dependencies transitively. For serialization only, depend directly on
`contracts-proto`. JARs contain generated code, not copies of those dependencies.
Use JDK 17, JVM target 17 and Kotlin 2.3.21 or a compatible newer compiler. Android
apps configure their normal Java/desugaring toolchain and INTERNET permission.

```kotlin
import io.github.arcforges.contracts.hello.v1.HelloServiceGrpcKt.HelloServiceCoroutineStub
import io.github.arcforges.contracts.hello.v1.sayHelloRequest
import io.grpc.okhttp.OkHttpChannelBuilder
import java.util.concurrent.TimeUnit

// Own this channel at the application/service scope, not per UI recomposition.
val channel = OkHttpChannelBuilder.forAddress("api.example.com", 443)
    .useTransportSecurity()
    .build()
val client = HelloServiceCoroutineStub(channel)

// Call from an application-owned coroutine.
suspend fun hello(): String = client.withDeadlineAfter(5, TimeUnit.SECONDS)
    .sayHello(sayHelloRequest { name = "World" }).message

// On owner shutdown, stop the channel; do not block Android's UI thread waiting.
fun close() { channel.shutdown() }
```

The endpoint above is illustrative and must implement the Hello service. The
local test host uses plaintext loopback: choose `usePlaintext()` only for that
local test. Android emulator loopback to the development host normally uses
`10.0.2.2`; an app must explicitly permit any development cleartext traffic.
Production TLS, account tokens/interceptors, endpoint selection and lifecycle
belong to the application, not the generated package. Coroutine cancellation
cancels the call; gRPC failures are `StatusException` (for example
`INVALID_ARGUMENT` for this example's empty name).

Java callers can use `HelloServiceGrpc` from the same client JAR. Kotlin/Native,
iOS and React Native are not supplied by these JVM artifacts.

Commit application Gradle dependency locks and verification metadata. Use exact
versions, not `+`/`latest.release`/SNAPSHOT. No Maven publishing credential is
needed to download public packages. Maven search pages can lag publication; the
release is usable when CI's Maven job verifies the files in the public repository.

## Updating a dependency

Select an accepted new version, update the explicit manifest/central version and
lock, then run the consuming application's tests before merging. Dependabot can
open these update PRs in each consuming repository; the producer cannot configure
an unrelated repository's update policy. Do not use floating `*` versions or a
moving dist-tag as a committed production dependency.

No consumer needs protoc, Git submodules, a checkout of Contracts or access to
DesktopPlatform. NuGet/npm/Maven download the published dependencies normally.
