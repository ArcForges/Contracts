# Maven development snapshots and formal releases

The group remains `io.github.arcforges`, with `contracts-proto`, `contracts-connect-client` and `contract-fixtures`.

Main builds publish `1.0.0-SNAPSHOT` to `https://central.sonatype.com/repository/maven-snapshots/`. Canonical `vX.Y.Z` tags publish immutable `X.Y.Z` releases to Maven Central. The tag commit must be reachable from main and passes the same build/offline candidate gates. No production tag is created by a validation test.

## Account setup

Verify ownership of `io.github.arcforges` in the [Central Portal](https://central.sonatype.com/). In [namespace settings](https://central.sonatype.com/publishing/namespaces), enable SNAPSHOTs for this namespace. Sonatype currently removes old snapshots after approximately 90 days; these are development artifacts, not long-term deployment inputs. See [official snapshot documentation](https://central.sonatype.org/publish/publish-portal-snapshots/).

Generate the Portal publishing user-token pair. Store `MAVEN_CENTRAL_USERNAME` and `MAVEN_CENTRAL_TOKEN` as secrets in GitHub environment `maven-central`. Formal releases additionally use `MAVEN_SIGNING_KEY` and `MAVEN_SIGNING_PASSWORD`; publish the public signing key as required by [Central](https://central.sonatype.org/publish/requirements/gpg/). Snapshot jobs receive no signing key. Keep secrets out of repository files and logs.

Restrict the environment to branch `main` and tags `v*`, without required reviewers or timers. The workflow rejects noncanonical tags and unmerged tag commits. Enable repository variable `MAVEN_PUBLISH_ENABLED=true` after setup. A skipped job means no publication; a missing credential or disabled namespace fails visibly.

## Development consumption

Existing immutable consumer pins are unchanged. Development users explicitly opt in:

```kotlin
repositories {
    maven {
        url = uri("https://central.sonatype.com/repository/maven-snapshots/")
        content { includeGroup("io.github.arcforges") }
    }
    mavenCentral()
}
dependencies {
    implementation("io.github.arcforges:contracts-connect-client:1.0.0-SNAPSHOT")
}
```

Gradle may [cache changing modules](https://docs.gradle.org/current/userguide/dependency_caching.html); use `--refresh-dependencies` when explicitly requesting a fresh snapshot. A snapshot coordinate can resolve differently later. The JAR's `source.json` carries the immutable cross-language CI build version, Git SHA and descriptor hash. Candidate manifests additionally record `mavenVersion`; publication receipts record candidate identity and upload/deployment status. Formal releases share one version across NuGet/npm/Maven.

## Candidate publication and recovery

Packing uses an isolated Maven-local directory below repository `artifacts`, never the developer's
global Maven repository. The producer validates archive contents once. A separate source-free
Gradle build transports the retained JAR, sources, documentation, POM and module files, without
rebuilding. Gradle generates snapshot timestamps and required repository checksums.

The serialized SNAPSHOT job reads [GitHub main-ref metadata](https://docs.github.com/en/rest/git/refs#get-a-reference).
If its candidate commit is no longer main, it records `superseded` and performs no upload.
Otherwise a successful transport records `upload-completed`; there is no public JAR download or
byte polling. This latest-main policy prevents an older queued/retried commit from rewinding the channel.
A diagnosed retry may re-upload the same mutable snapshot candidate; never retry merely to verify it.

Each publication step has a ten-minute timeout. `maven-deployment-<run-id>-<attempt>` retains a
non-secret receipt even after failure. Inspect the failure before retrying the same candidate.
Do not re-run all jobs or allocate a replacement version merely to check publication.

Formal releases retain the Central Portal `AUTOMATIC` upload and required detached signatures.
Retries recover the accepted deployment ID from the same run's receipt. An ambiguous upload without
an ID is not uploaded again: inspect Central and set `MAVEN_CENTRAL_DEPLOYMENT_ID` only to the
confirmed ID, then remove the override. The [Portal status response](https://central.sonatype.org/publish/publish-portal-api/)
must identify the expected deployment ID/name and all three package coordinates at `PUBLISHED`.
That provider result completes publication; public propagation and search indexing are not polled.

Candidates remain retained for 30 days and receipts for 90 days. An expired immutable candidate
must not be reconstructed or overwritten. NuGet/npm success does not establish Maven publication.
Post-merge work confirms commit and required job/provider status only. The consumer and snapshot
inspection helpers remain explicit local diagnostics for a concrete defect or user request; they
are never CI or routine post-merge gates. See [AGENTS.md](../AGENTS.md).
