// SPDX-License-Identifier: Apache-2.0
plugins { application; alias(libs.plugins.kotlin.jvm) }
kotlin { jvmToolchain(17) }
application { mainClass.set("io.github.arcforges.tests.MainKt") }
val release = providers.gradleProperty("releaseVersion").get()
dependencies {
    implementation("io.github.arcforges:contracts-client:$release")
    implementation("io.github.arcforges:contract-fixtures:$release")
    implementation(libs.grpc.okhttp)
    implementation(libs.gson)
}
dependencyLocking {
    lockAllConfigurations()
    lockMode.set(LockMode.STRICT)
    // Candidates are exact and hash-verified before this build. Third parties
    // remain locked; the candidate version changes on every producer CI run.
    ignoredDependencies.add("io.github.arcforges:*")
}
tasks.register("resolveLockedDependencies") {
    doLast { configurations.filter { it.isCanBeResolved }.forEach { it.resolve() } }
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
