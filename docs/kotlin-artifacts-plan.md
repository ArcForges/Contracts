# Kotlin artifacts implementation plan

## Baseline and boundary

The work starts at `4f6564a0fa15a18e92668efb995c25a88a9edf19` in the isolated
`codex/contracts-kotlin` worktree. The current handwritten schema is the Hello
World example. NuGet and npm already publish automatically after a main push.
This change adds a complete Kotlin/JVM package path for that same schema; it
does not implement the future product API catalog or an Android application.

## Collected gaps and decisions

1. There are no Java/Kotlin bindings, Maven artifacts or Kotlin consumers. Add
   `io.github.arcforges:contracts-proto`, `contracts-client` and
   `contract-fixtures`. Use Java/Kotlin protobuf lite and gRPC Kotlin coroutine
   bindings. Callers own channels, TLS, authentication and channel shutdown.
   Kotlin/JVM is the Android target; Kotlin/Native and iOS are outside this task.
2. Preserve a single schema and compiler: use the locked Grpc.Tools protoc for
   all languages, with pinned Java/Kotlin gRPC plugins. Commit generated output
   and check regeneration. Java package options must not change wire names,
   field numbers, C# namespaces or the existing TypeScript API.
3. Add a checksum-pinned Gradle 9.3.0 wrapper, JDK 17, Kotlin 2.3.21, exact
   dependency versions, strict dependency locks and checksum verification.
   Restore/build/generate/pack entry points must include Kotlin. Dependencies
   are ordinary Maven dependencies, never copied into the published JARs.
4. Build three Maven modules with POMs, Gradle metadata, sources and API docs.
   Bundle the unsigned Maven repository alongside existing candidate archives.
   Every module carries Apache-2.0, NOTICE, resolved dependency inventory and
   source/schema identity. Archive checks reject missing classes, schema,
   fixtures, documentation, dependency metadata or inconsistent versions.
5. Extend the isolated Windows/Linux consumer gate to install the Maven bundle
   into a fresh Gradle cache outside this checkout and call the real C# host.
   Verify ASCII, Unicode, wire serialization and INVALID_ARGUMENT using the
   published fixture JAR. Keep existing C#, AOT and TypeScript gates. An Android
   app/device, production service and registry restore remain separate evidence.
6. Add main-only Maven Central publication after the common Verify gate. Sign
   already-tested files with an in-memory PGP key, add checksums, upload with
   automatic publication, poll deployment status and compare registry bytes.
   Never rebuild in the publish job. Reject wrong source, dirty candidates,
   conflicting existing versions and ambiguous retries; retain a deployment
   receipt to resume a failed job without repeating an accepted upload.
7. Extend CodeQL with an actual Java/Kotlin build, Dependabot with Gradle and
   wrapper updates, repository hygiene and usage/release documentation. Preserve
   existing registry identities and protections. Configure a main-only
   `maven-central` GitHub environment and disabled publication variable until
   its external account and secrets are supplied. No credentials are invented.

## Execution and closure

Implement in order: toolchain/modules and generation; package metadata and
archive verification; isolated consumers; publication and failure tests; CI and
repository policies; documentation and GitHub settings. Then run the complete
candidate/consumer gates, inspect the final diff, submit a PR and inspect its
checks. Fix concrete failures within this scope, without expanding Hello World
into product APIs. Account registration instructions follow PR creation.

Closure requires generated files to match, all six package identities to share
one release and descriptor, real package consumers to pass, negative release
guards to pass, and PR CI/security checks to pass. Maven publication and public
restore can only be recorded after the account is configured and main publishes;
a skipped publisher or successful local candidate is not that evidence.

## Primary references

- [Kotlin/Gradle compatibility](https://kotlinlang.org/docs/gradle-configure-project.html)
- [Official gRPC Kotlin lite example](https://github.com/grpc/grpc-kotlin/blob/master/examples/stub-lite/build.gradle.kts)
- [Dokka API documentation archives](https://kotlinlang.org/docs/dokka-gradle.html)
- [Central publication requirements](https://central.sonatype.org/publish/requirements/)
- [Central Publisher API](https://central.sonatype.org/publish/publish-portal-api/)
- [Gradle in-memory signing](https://docs.gradle.org/current/userguide/signing_plugin.html)
