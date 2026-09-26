# Installing and using the packages

Choose a version whose main CI candidate and relevant registry job both passed.
The release manifest supplies the exact NuGet/npm version and the separate
Maven channel version. An Actions artifact named candidate is a tested archive;
it becomes a registry package only after upload. Versions such as
`1.0.0-ci.12.1` and the formal Maven version `1.0.0` below are illustrative, not
assertions that those releases exist. The
[accepted WP03.00 publication](releasing.md#wp0300-accepted-publication)
records the complete published set and its channel identities.

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
    <PackageVersion Include="Grpc.Net.Client" Version="2.84.0" />
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
`latest`. Before the first stable release, CI advances it to the newest published
main build; afterwards, stable releases own `latest` and main builds use `ci`.
Check that publication succeeded for every package in the producer catalog and
use the accepted common version for the packages your application consumes;
registry uploads are not atomic across packages. Moving a tag does not rewrite
an existing application's dependency version or lock file. Public Web clients
must not import the private AI or operator packages.

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

### gRPC-Web for the Worker ingress

Use `contracts-connect-client` with an exact formal version from a successful
Maven Central publication containing that module. The version shown here is an
example, not an already published formal release. Main currently publishes
`1.0.0-SNAPSHOT` through the separate [development channel](maven-central.md);
its NuGet/npm CI version is not a Maven Central release coordinate. For a
published formal release, add `mavenCentral()`:

```kotlin
dependencies {
    implementation("io.github.arcforges:contracts-connect-client:1.0.0")
    implementation("com.connectrpc:connect-kotlin-okhttp:0.9.0")
    implementation("com.connectrpc:connect-kotlin-google-javalite-ext:0.9.0")
}
```

The package brings the exact matching lite `contracts-proto` and Connect-Kotlin
core. Commit application dependency locks. No proto copy or generator is needed.

```kotlin
import com.connectrpc.ProtocolClientConfig
import com.connectrpc.extensions.GoogleJavaLiteProtobufStrategy
import com.connectrpc.getOrThrow
import com.connectrpc.impl.ProtocolClient
import com.connectrpc.okhttp.ConnectOkHttpClient
import com.connectrpc.protocols.NetworkProtocol
import io.github.arcforges.contracts.hello.v1.HelloServiceClient
import io.github.arcforges.contracts.hello.v1.sayHelloRequest
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.Dispatchers
import okhttp3.OkHttpClient

// Create these once at application/service scope, not per recomposition.
val http = OkHttpClient()
val client = HelloServiceClient(ProtocolClient(
    httpClient = ConnectOkHttpClient(http),
    config = ProtocolClientConfig(
        host = "https://arcforges.com/api",
        serializationStrategy = GoogleJavaLiteProtobufStrategy(),
        networkProtocol = NetworkProtocol.GRPC_WEB,
        ioCoroutineContext = Dispatchers.IO,
        timeoutOracle = { 10.seconds },
    ),
))

// Invoke from an application-owned coroutine. RPC errors throw ConnectException.
suspend fun hello(): String = client.sayHello(
    sayHelloRequest { name = "World" },
).getOrThrow().message
```

The URL illustrates the public Worker ingress. Historical local loopback
diagnostics covered the `/api` prefix; this producer candidate does not establish
current Cloud deployment or Android device behavior. Do not use the Connect
protocol default against ASP.NET gRPC. Keep request compression disabled
(the default) for the current Hello ingress. The application owns credentials,
TLS, coroutine cancellation and transport cleanup. Use JDK/JVM target 17 or newer
and Kotlin 2.4.20 or a compatible compiler; Android also needs INTERNET permission.

For a future native gRPC endpoint, the same generated Connect client can select
`NetworkProtocol.GRPC` with a working HTTP/2 transport and that endpoint's URL.
Changing the protocol alone does not enable native gRPC on the current Worker.
The native-grpc-only `contracts-client` is retired from new publications at
WP03.00. Historical releases and exact existing consumer pins are unchanged.
New Android/JVM consumption uses the selected Connect client; no removed
native-grpc client package or runtime diagnostic is claimed for this candidate.
Kotlin/Native, iOS and React Native are not supplied by these JVM artifacts.

Commit application Gradle dependency locks and verification metadata. Use exact
versions, not `+`/`latest.release`/SNAPSHOT. No Maven publishing credential is
needed to download public packages. Maven search pages can lag publication; the
publisher completes when the provider reports the expected upload/deployment status.
CI does not download public files to prove propagation; ordinary dependency restore remains the consumer's operation.

## Updating a dependency

Select an accepted new version, update the explicit manifest/central version and
lock, then run the consuming application's tests before merging. Dependabot can
open these update PRs in each consuming repository; the producer cannot configure
an unrelated repository's update policy. Do not use floating `*` versions or a
moving dist-tag as a committed production dependency.

No consumer needs protoc, Git submodules, a checkout of Contracts or access to
DesktopPlatform. NuGet/npm/Maven download the published dependencies normally.
