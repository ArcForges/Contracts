# Bootstrap validation evidence

## Observed locally

On Windows x64, the bootstrap has passed:

- Locked .NET/npm dependency restoration with the pinned toolchain.
- Generation of C# and TypeScript from the same Grpc.Tools protoc.
- Regeneration comparison, .NET and strict TS builds, and ASCII/Unicode/wire
  field/malformed-payload tests.
- Creation and inspection of the actual NuGet and two npm archives, including
  public licences, runtime dependencies, source metadata, descriptor and hashes.
- Installation into an independent temporary directory with fresh caches.
- Real C# gRPC and TS gRPC-Web calls, including the server's InvalidArgument error.
- Native AOT publication and execution of the C# package consumer.

The initial local candidate was built from the bootstrap worktree and is marked
dirty/development; it is not eligible for registry upload. The generated evidence
lives in ignored `artifacts/evidence/win-x64`.

## CI and external evidence

GitHub repository setup was verified: the nuget/npm environments accept only
main and have no approval timer/reviewer gate; Actions defaults to read-only.
Private vulnerability reporting, Dependabot security updates, secret scanning
and push protection are enabled. NUGET_USER is set to the existing username;
NuGet/npm publication was disabled during that bootstrap. It is now enabled
with OIDC, as recorded in releasing.md. Maven publication has a separate switch
and requires the new account/signing setup.

Main branch protection requires a PR, up-to-date checks and resolved review
conversations. Required checks are Verify, Dependency review, Secret scan, CodeQL
and language-specific CodeQL jobs. Kotlin adds a manual Java/Kotlin build check. The required approval count is zero;
registry environments have no manual release approval gate.

[PR 1](https://github.com/ArcForges/Contracts/pull/1) validated implementation commit
`0de04b3d579a71d70d9541cddb1ed326a6100b66`:

- [CI run 34692732413](https://github.com/ArcForges/Contracts/actions/runs/34692732413)
  passed generation, compilation, archive/guard tests, both Windows/Linux JIT and
  Native AOT consumers, actual gRPC/gRPC-Web success/error calls and the Verify
  gate. Publication jobs were correctly skipped for the PR.
- [Security run 34692732422](https://github.com/ArcForges/Contracts/actions/runs/34692732422)
  passed dependency review, secret scanning and CodeQL for C#, TypeScript/JavaScript
  and Python.
- The immutable CI candidate is `1.0.0-ci.1.1`, built from GitHub's clean PR merge
  revision `da0bdb641d67192026c4c6de14313b96fc3002fc`. Its manifest and both consumer
  evidence archives were downloaded and inspected. This is CI artifact evidence,
  not a claim that version exists on a registry.

The evidence record itself was added after these runs; the implementation and
workflow files did not change when recording these results.

The initial bootstrap evidence did not establish registry upload/restore,
browser rendering, Android device operation,
production service AOT build or ArcForges business behavior has been verified by
the local results above. Registry identity setup and first publication require
the account configuration documented in releasing.md.

## Kotlin extension: local evidence

The Kotlin extension has passed on Windows x64 with JDK 17, Gradle 9.3.0,
Kotlin 2.3.21 and the existing pinned .NET/Node/Python toolchain:

- Regeneration of C#, TS, Java/Kotlin lite messages and coroutine service bindings
  from the same protoc/schema; no additional Mobile proto source.
- Strict Gradle dependency locks, checksum-verified generators/plugins and a
  producer build of all three Maven modules.
- Packing and deep inspection of all six packages, including 15 Maven publication
  files (main/source/documentation JARs, POMs and Gradle module metadata).
- A fresh Gradle cache and an independent temporary consumer, installed from the
  actual Maven candidate repository with no producer project references.
- Actual Kotlin/OkHttp gRPC calls to the C# host using the published fixture JAR:
  ASCII, Unicode and INVALID_ARGUMENT; lite binary field, unknown-field and
  truncated-payload checks. Existing C# JIT/AOT and TS gRPC-Web consumers passed.
- Seventeen release tests, including missing Maven publication files, wrong
  first-party versions, conflicting/partial registry data and uncertain-upload
  recovery guards. A throwaway local PGP key signed all 15 files; GnuPG verified
  every signature and the payloads remained byte-identical.

The local candidate is `1.0.0-ci.0.0`, marked dirty/development. It was not
uploaded. Evidence is in ignored `artifacts/evidence/win-x64` and local logs.
GitHub PR evidence will be recorded separately. No Maven account credentials,
real Central upload/restore or Android application/device were used for these
local checks; the JVM tests do not certify an Android application.

GitHub configuration for the Kotlin extension now includes a main-only
`maven-central` environment, `MAVEN_PUBLISH_ENABLED=false`, and required
`CodeQL (java-kotlin)`. Existing NuGet/npm OIDC variables and environments were
preserved. No Maven credentials were created or uploaded.

## Kotlin gRPC-Web extension: local evidence (2026-09-16)

The `codex/contracts-kotlin-grpc-web` worktree adds one generated Connect-Kotlin
client module for the existing Hello schema. Local Windows x64 validation used
.NET 10.0.400, JDK 17, Gradle 9.7.1, Kotlin 2.4.20 and Connect-Kotlin 0.9.0:

- Locked producer restore, deterministic regeneration comparison, C#/TS/Kotlin
  compilation, wire tests and formatting passed. Existing schema and C#/TS/
  grpc-kotlin generated APIs are unchanged.
- All seven package identities passed archive, dependency, metadata and hash
  inspection. The four Maven modules contain 20 unsigned publication files.
- All 17 release guard tests passed, including wrong proto dependency versions
  for both Kotlin clients and real detached signatures covering all 20 files.
  A temporary test key was used; signing preserved the tested payload bytes.
- Independent applications installed the actual candidate with fresh package
  caches and no producer project/class references. Both Kotlin projects also
  restored successfully with their committed third-party locks and checksums.
- The new Connect consumer, without the grpc-kotlin client dependency, called
  the C# fixture using binary gRPC-Web over HTTP/1.1 and gRPC over HTTP/2. Tests
  verified RPC paths, an `/api` prefix, ASCII/Unicode/whitespace responses and
  the server's `INVALID_ARGUMENT` status/message.
- Existing C# JIT, TS gRPC-Web, grpc-kotlin and published Windows Native AOT C#
  **client** calls passed against the same C# fixture.

Local Gradle Wrapper downloading encountered a TLS failure. The successful
consumer run invoked the already installed, matching Gradle 9.7.1 distribution;
NuGet/npm/Gradle dependency caches remained newly created and isolated. This was
an ignored local launcher adjustment, not a repository/CI configuration change.
CI runs the unchanged checksum-pinned Wrapper download path on Windows/Linux.

The local candidate is `1.0.0-ci.0.0`, marked dirty/development, with evidence in
ignored `artifacts/evidence/win-x64` and `artifacts/consume-local.log`. No registry
upload, Android application/device, Cloud deployment, production AOT **server**,
authentication or streaming RPC behavior is established by these tests. The
existing main-only publisher will include the new module after an accepted merge.
