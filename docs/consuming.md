# Installing and using the packages

Choose a version whose main CI candidate and relevant registry job both passed.
The release manifest supplies the exact version. An Actions artifact named candidate
is a tested archive; it becomes a registry package only after upload. Versions such
as `1.0.0-ci.12.1` below are illustrative, not assertions that those releases exist.
The [accepted WP03.00 publication](releasing.md#wp0300-accepted-publication)
records the complete published set and its channel identities at that time.

C# NuGet is the only first-party SDK channel for business clients (CON.40, P2-021
Decision 4). The TypeScript and Kotlin packages are
[retired from new publication](#retired-typescript-and-kotlin-packages).

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
service implementation, TLS endpoint and authentication. Public business clients,
including browser (Blazor WebAssembly) and Android (.NET MAUI) applications, use
binary gRPC-Web for the public Worker ingress; the application composes that
transport, its credentials and its lifecycle. The packages create no global channel.

## Internal npm package

`@arcforges/ai-internal` is the one retained npm package. It carries the internal
AI/Cloud HTTP schema records and validators for the Cloudflare thin adapters. It is
published to the public npm registry (`publishConfig` access `public`), but its
contract access is `internal`: public clients must not import it, and registry
visibility does not change that boundary. Install an exact version and commit the
lock:

```text
npm install --save-exact @arcforges/ai-internal@1.0.0-ci.12.1
```

Before the first stable release, CI advances its `latest` tag to the newest
published main build; afterwards, stable releases own `latest` and main builds use
`ci`. Moving a tag does not rewrite an existing application's dependency version or
lock file.

## Retired TypeScript and Kotlin packages

No new version of npm `@arcforges/proto`, `@arcforges/api-client`,
`@arcforges/contract-fixtures` or `@arcforges/operator-client`, or of Maven
`io.github.arcforges:contracts-proto`, `contracts-connect-client` or
`contract-fixtures`, is published (CON.40). Already published versions stay
immutable and resolvable: nothing is unpublished, deprecated or deleted, so an
existing exact pin and its lock keep restoring. They receive no further schema,
fixture or security update; a consumer that needs one moves to the C# packages.
The native-grpc-only Maven `contracts-client` was retired at WP03.00 in the same
way. The former TypeScript and Kotlin installation examples are history; see
[the retired Maven guide](maven-central.md) and the retired Kotlin plans linked from
the README.

## Updating a dependency

Select an accepted new version, update the explicit manifest/central version and
lock, then run the consuming application's tests before merging. Dependabot can
open these update PRs in each consuming repository; the producer cannot configure
an unrelated repository's update policy. Do not use floating `*` versions or a
moving dist-tag as a committed production dependency.

No consumer needs protoc, Git submodules, a checkout of Contracts or access to
DesktopPlatform. NuGet (and npm, for `@arcforges/ai-internal`) download the published
dependencies normally.
