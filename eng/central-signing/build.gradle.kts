// SPDX-License-Identifier: Apache-2.0
plugins { signing }
val candidate = file(providers.gradleProperty("candidateDirectory").get()).canonicalFile
require(candidate.isDirectory) { "A verified Maven repository directory is required" }
val payload = candidate.walkTopDown().filter {
    it.isFile && (it.extension in setOf("jar", "pom", "module"))
}.toList()
require(payload.size == 15) { "Expected three complete unsigned Maven publications" }
signing {
    useInMemoryPgpKeys(
        providers.environmentVariable("MAVEN_SIGNING_KEY").get(),
        providers.environmentVariable("MAVEN_SIGNING_PASSWORD").getOrElse("")
    )
}
tasks.register<Sign>("signCandidate") {
    // This build has no source sets, repositories or package-generation tasks.
    // Only detached signatures are added; the tested bytes remain untouched.
    sign(*payload.toTypedArray())
}
