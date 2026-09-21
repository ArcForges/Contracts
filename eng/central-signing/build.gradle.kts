// SPDX-License-Identifier: Apache-2.0
plugins { signing; `maven-publish` }
val snapshot = providers.gradleProperty("snapshotVersion").orNull
val candidate = file(providers.gradleProperty("candidateDirectory").get()).canonicalFile
require(candidate.isDirectory) { "A verified Maven repository directory is required" }
val payload = candidate.walkTopDown().filter {
    it.isFile && (it.extension in setOf("jar", "pom", "module"))
}.toList()
val expectedFileCount = providers.gradleProperty("expectedFileCount").get().toInt()
require(expectedFileCount > 0 && payload.size == expectedFileCount) { "Expected the complete verified Maven payload" }
if (snapshot == null) signing {
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

// Publish only prebuilt archives. Gradle owns timestamp/checksum/metadata transport.
if (snapshot != null) {
    require(snapshot == "1.0.0-SNAPSHOT")
    val repositoryUrl = providers.gradleProperty("snapshotRepository").getOrElse(
        "https://central.sonatype.com/repository/maven-snapshots/")
    val target = java.net.URI(repositoryUrl)
    val loopback = target.scheme == "http" && target.host == "127.0.0.1" &&
        target.userInfo == null && target.port > 0
    require(repositoryUrl == "https://central.sonatype.com/repository/maven-snapshots/" ||
        target.scheme == "file" || loopback) { "Only Sonatype or a local test repository is allowed" }
    publishing {
        publications {
            for (module in listOf("contracts-proto", "contracts-client", "contracts-connect-client", "contract-fixtures")) {
                create<MavenPublication>(module) {
                    groupId = "io.github.arcforges"
                    artifactId = module
                    version = snapshot
                    val prefix = "io/github/arcforges/$module/$snapshot/$module-$snapshot"
                    artifact(candidate.resolve("$prefix.jar"))
                    artifact(candidate.resolve("$prefix-sources.jar")) { classifier = "sources" }
                    artifact(candidate.resolve("$prefix-javadoc.jar")) { classifier = "javadoc" }
                    artifact(candidate.resolve("$prefix.module")) { extension = "module" }
                }
            }
        }
        repositories {
            maven {
                name = "Snapshots"
                url = target
                isAllowInsecureProtocol = loopback
                if (target.scheme == "https") credentials {
                    username = providers.environmentVariable("MAVEN_CENTRAL_USERNAME").get()
                    password = providers.environmentVariable("MAVEN_CENTRAL_TOKEN").get()
                }
            }
        }
    }
    tasks.withType<org.gradle.api.publish.maven.tasks.GenerateMavenPom>().configureEach {
        val generatedPom = destination
        doLast {
            val module = name.removePrefix("generatePomFileFor").removeSuffix("Publication")
                .replaceFirstChar { it.lowercase() }
            candidate.resolve("io/github/arcforges/$module/$snapshot/$module-$snapshot.pom")
                .copyTo(generatedPom, overwrite = true)
        }
    }
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
