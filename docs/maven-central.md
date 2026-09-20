# Maven development snapshots and formal releases

The group remains `io.github.arcforges`, with `contracts-proto`, `contracts-client`, `contracts-connect-client` and `contract-fixtures`.

Main builds publish `1.0.0-SNAPSHOT` to `https://central.sonatype.com/repository/maven-snapshots/`. Canonical `vX.Y.Z` tags publish immutable `X.Y.Z` releases to Maven Central. The tag commit must be reachable from main and passes the same candidate/consumer gates. No production tag is created by a validation test.

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

Gradle may [cache changing modules](https://docs.gradle.org/current/userguide/dependency_caching.html); use `--refresh-dependencies` when explicitly requesting a fresh snapshot. A snapshot coordinate can resolve differently later. The JAR's `source.json` carries the immutable cross-language CI build version, Git SHA and descriptor hash. Candidate manifests additionally record `mavenVersion`; publication receipts record all resolved timestamped URLs and hashes. Formal releases share one version across NuGet/npm/Maven.

## Tested-byte publication and recovery

Packing uses an isolated Maven-local directory below repository `artifacts`, never the developer's global Maven repository. Both consumer platforms restore the candidate before publication. A separate source-free Gradle build transports the exact tested JAR, sources, documentation, POM and module files. Gradle generates snapshot timestamps and repository checksums. The publisher verifies all 20 remote files byte for byte. A newer snapshot cannot be replaced by a delayed older CI run; a same-build byte conflict fails.

Each publication step has a ten-minute timeout. `maven-deployment-<run-id>-<attempt>` retains a non-secret receipt even after failure. Re-run failed jobs with the original candidate; do not re-run all jobs merely to retry publication. Matching snapshot bytes succeed without another upload. Missing snapshot files can be republished from the same candidate and are verified together before success.

Formal releases retain the Central Portal `AUTOMATIC` upload and detached-signature path. Retries recover the accepted deployment ID from the same run's receipt. An ambiguous upload without an ID is not uploaded again: inspect Central and set environment variable `MAVEN_CENTRAL_DEPLOYMENT_ID` only to the confirmed deployment ID, then remove the override after recovery. Publication and public-byte propagation share the bounded attempt; a later retry resumes the same deployment. Search indexing is not an acceptance gate.

Candidates are retained for 30 days and receipts for 90 days. If an immutable release candidate expires, do not reconstruct or overwrite that version; allocate a new release version through review. CI/npm/NuGet success does not establish Maven availability. Namespace enablement is proven only by a real successful snapshot publication.

Post-merge verification can run `python eng/contracts.py consume --aot --snapshot-registry` against the downloaded matching candidate. It verifies remote bytes before and after actual Kotlin/Connect restoration and RPC execution, using fresh caches.
