# WP02.04 build identity and independent version axes

The accepted [Design profile](https://github.com/ArcForges/ArcForges-Design/blob/257f77ce8d476a4efd8746fc0b7e4e6358c32a67/docs/assurance/wp02-04-version-identity-profile.md)
governs this Apache-2.0 implementation. Contracts implements its own tooling;
it does not import DesktopPlatform build policy or its AGPL implementation.

All seven packages contain `build-identity.json`, with schema
`arcforges.build-identity.v1`. Artifact identity records the actual distribution
coordinate. Maven main uses `1.0.0-SNAPSHOT`, whereas the build identity retains
the unique GitHub run/attempt and full source commit. Formal tags keep their
existing publication channel. No package IDs, runtime dependencies or wire
definitions change.

`eng/version-sources.json` declares all nine axes and their independent sources.
ContractSet reads the authored proto namespace major and retains the descriptor
digest; a package release does not change it. PackageVersion contains the exact
resolved runtime dependency closure from the package SBOM. Library AppVersion
and an absent native C ABI are explicitly not applicable. Future capabilities,
portable formats, storage migrations, policy schemas and extension protocols
name their later producers and remain not produced. This report establishes
neither production business contracts nor product readiness.

Build metadata distinguishes local and CI artifacts, rejects incomplete or
dirty CI inputs, and uses the commit timestamp as `sourceDateEpoch`, not the
wall-clock compilation time. Re-running failed publisher jobs can use the
earlier attempt's exact candidate from the same run. A different source/run or
a changed package report fails candidate verification.

Every owned .NET project, including Codegen and test tools, receives compiled
`ArcForges.SourceCommit`, `ArcForges.SourceDateEpoch`, `ArcForges.BuildKind`,
`ArcForges.BuildId` and `ArcForges.PipelineRun` assembly metadata. The build reads
all four PE metadata tables and compares them with independently calculated Git
and pipeline inputs. Temporary package consumers have their own explicit local
build identity; they read the producer identity from the installed library.

Runtime access uses assembly attributes in C#, the exported
`@arcforges/proto/build-identity` and `@arcforges/api-client/build-identity` JSON
modules in Node, and module-specific JAR resources
`META-INF/arcforges/<artifactId>/build-identity.json` in Java/Kotlin. Unique JAR
paths prevent class-loader ambiguity when several Contracts modules are loaded.
The isolated consumers compare actual installed metadata with the retained
candidate's build identity before exercising real Hello success/error transport.
C# additionally runs as Native AOT. JVM probes are not Android device evidence.

Negative tests mutate all nine source kinds independently, reject unknown,
missing, duplicate and aliased axes, reject malformed build identity, and alter
packaged reports while recalculating the outer archive checksum. Repeated
generation with identical declared inputs must yield identical reports.

The reviewed package-graph inventory updates only the
`Directory.Build.targets` digest (previous SHA-256
`64eee4fee7291c9afb9049413a95a19acc174354e506dd1965237061d12bf4b1`).
The new target adds assembly support metadata; it introduces no project or
package references. Existing contract-access, licence, generation and
immutable Dokka resource profiles remain enforced.
