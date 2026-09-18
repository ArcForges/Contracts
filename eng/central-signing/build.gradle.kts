// SPDX-License-Identifier: Apache-2.0
plugins { signing }
val candidate = file(providers.gradleProperty("candidateDirectory").get()).canonicalFile
require(candidate.isDirectory) { "A verified Maven repository directory is required" }
val payload = candidate.walkTopDown().filter {
    it.isFile && (it.extension in setOf("jar", "pom", "module"))
}.toList()
val expectedFileCount = providers.gradleProperty("expectedFileCount").get().toInt()
require(expectedFileCount > 0 && payload.size == expectedFileCount) { "Expected the complete verified Maven payload" }
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

// Project licence metadata is verified independently of the root LICENSE.
extra["spdxLicense"] = "Apache-2.0"
extra["licenceBoundary"] = "Apache"

// Verify effective values after every project script has been evaluated, including
// tools and isolated consumer builds. Third-party licences remain independently owned.
gradle.projectsEvaluated {
    val declarations = rootProject.allprojects.sortedBy { it.path }.map { owned ->
        require(owned.projectDir.canonicalFile.toPath().startsWith(rootDir.canonicalFile.toPath())) {
            "AFL002: Project escapes this build: ${owned.path}"
        }
        require(owned.extra.has("spdxLicense") && owned.extra["spdxLicense"] == "Apache-2.0" &&
                owned.extra.has("licenceBoundary") && owned.extra["licenceBoundary"] == "Apache") {
            "AFL001: Missing or incorrect Apache licence declaration: ${owned.path}"
        }
        owned.configurations.forEach { configuration ->
            configuration.dependencies.withType<org.gradle.api.artifacts.ProjectDependency>().forEach { dependency ->
                val target = rootProject.project(dependency.path)
                require(target.extra.has("licenceBoundary") && target.extra["licenceBoundary"] == "Apache") {
                    "AFL003: Apache project references a non-Apache project: ${owned.path} -> ${target.path}"
                }
            }
        }
        mapOf("project" to owned.path, "spdxLicense" to owned.extra["spdxLicense"],
              "licenceBoundary" to owned.extra["licenceBoundary"],
              "projectReferences" to owned.configurations.flatMap { configuration ->
                  configuration.dependencies.withType<org.gradle.api.artifacts.ProjectDependency>().map { it.path }
              }.distinct().sorted())
    }
    val report = rootProject.layout.buildDirectory.file("reports/licence-boundary.json").get().asFile
    report.parentFile.mkdirs()
    report.writeText(groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(declarations)) + "\n")
}
