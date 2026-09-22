// SPDX-License-Identifier: Apache-2.0
import groovy.json.JsonOutput
import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.component.ProjectComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult
import org.jetbrains.kotlin.gradle.dsl.KotlinJvmProjectExtension
import org.jetbrains.dokka.gradle.DokkaExtension

plugins {
    base
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.dokka) apply false
}

val release = providers.gradleProperty("releaseVersion").getOrElse("1.0.0-ci.0.0")
require(Regex("(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(-ci\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)|-SNAPSHOT)?").matches(release))
val codegen = configurations.create("codegen") { isCanBeConsumed = false }
dependencies {
    // Upstream publishes an executable fat JAR; compiler dependencies are not runtime APIs.
    codegen("com.connectrpc:protoc-gen-connect-kotlin:${libs.versions.connect.get()}@jar")
}

allprojects {
    group = "io.github.arcforges"
    version = release
    dependencyLocking { lockAllConfigurations(); lockMode.set(LockMode.STRICT) }
    tasks.withType<AbstractArchiveTask>().configureEach {
        isPreserveFileTimestamps = false
        isReproducibleFileOrder = true
    }
    tasks.register("resolveLockedDependencies") {
        doLast { configurations.filter { it.isCanBeResolved }.forEach { it.resolve() } }
    }
}

tasks.register<Sync>("resolveCodegenTools") {
    from(codegen)
    into(layout.projectDirectory.dir("artifacts/kotlin-codegen"))
}

subprojects {
    apply(plugin = "java-library")
    apply(plugin = "maven-publish")
    apply(plugin = "org.jetbrains.dokka")
    if (name != "contract-fixtures") {
        apply(plugin = "org.jetbrains.kotlin.jvm")
        extensions.configure<KotlinJvmProjectExtension> {
            jvmToolchain(17)
            compilerOptions { allWarningsAsErrors.set(true) }
            sourceSets.named("main") { kotlin.srcDir("generated/kotlin") }
        }
    }
    extensions.configure<DokkaExtension> {
        if (project.name == "contracts-proto") {
            dokkaPublications.configureEach {
                // Dokka aliases inherited protobuf methods across sibling messages.
                // Document declared APIs without those misleading cross-type links.
                suppressInheritedMembers.set(true)
            }
        }
        dokkaSourceSets.configureEach {
            jdkVersion.set(17)
            // Offline documentation: no mutable external package-list downloads.
            enableJdkDocumentationLink.set(false)
            enableKotlinStdLibDocumentationLink.set(false)
            enableAndroidDocumentationLink.set(false)
        }
    }
    extensions.configure<JavaPluginExtension> {
        toolchain.languageVersion.set(JavaLanguageVersion.of(17))
        withSourcesJar()
    }
    extensions.configure<SourceSetContainer> {
        named("main") {
            java.srcDir("generated/java")
            resources.srcDir(rootProject.layout.projectDirectory.dir("artifacts/maven-metadata/${project.name}"))
        }
    }
    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
        options.release.set(17)
        options.compilerArgs.add("-Werror")
    }
    tasks.withType<Jar>().configureEach {
        from(rootProject.file("LICENSE")) { into("META-INF") }
    }
    // Only reviewed resources enter the companion archive. The owning Python
    // packager stages this directory after checking raw pinned Dokka output.
    val documentationDirectory = rootProject.layout.projectDirectory.dir("artifacts/documentation/${project.name}")
    val documentation = tasks.register<Jar>("javadocJar") {
        archiveClassifier.set("javadoc")
        from(documentationDirectory)
        doFirst {
            require(documentationDirectory.file("NOTICE").asFile.isFile) {
                "Run python eng/contracts.py pack to prepare reviewed documentation resources"
            }
        }
    }
    extensions.configure<PublishingExtension> {
        publications {
            create<MavenPublication>("maven") {
                from(components["java"])
                artifact(documentation)
                pom {
                    name.set("ArcForges ${project.name}")
                    description.set("Public Hello World protobuf contracts: ${project.name}. Android/JVM, Apache-2.0.")
                    url.set("https://github.com/ArcForges/Contracts")
                    licenses { license { name.set("Apache-2.0"); url.set("https://www.apache.org/licenses/LICENSE-2.0.txt") } }
                    developers { developer { id.set("arcforges"); name.set("ArcForges contributors"); url.set("https://github.com/ArcForges") } }
                    scm {
                        url.set("https://github.com/ArcForges/Contracts")
                        connection.set("scm:git:https://github.com/ArcForges/Contracts.git")
                        developerConnection.set("scm:git:ssh://git@github.com/ArcForges/Contracts.git")
                        tag.set(providers.gradleProperty("sourceCommit").getOrElse("HEAD"))
                    }
                }
            }
        }
        repositories { maven { name = "Candidate"; url = rootProject.layout.projectDirectory.dir("artifacts/maven-repository").asFile.toURI() } }
    }
    tasks.register("runtimeInventory") {
        inputs.property("releaseVersion", release)
        val output = rootProject.layout.projectDirectory.file("artifacts/maven-graphs/${project.name}.json")
        outputs.file(output)
        doLast {
            val resolution = configurations.getByName("runtimeClasspath").incoming.resolutionResult
            fun identity(id: org.gradle.api.artifacts.component.ComponentIdentifier): String = when (id) {
                is ModuleComponentIdentifier -> "${id.group}:${id.module}:${id.version}"
                is ProjectComponentIdentifier -> "io.github.arcforges:${id.projectName}:$release"
                else -> error("Unexpected component: $id")
            }
            val graph = resolution.allComponents.associate { component ->
                identity(component.id) to component.dependencies.filterNot { it.isConstraint }.map {
                    require(it is ResolvedDependencyResult) { "Unresolved runtime dependency: $it" }
                    identity(it.selected.id)
                }.distinct().sorted()
            }
            output.asFile.parentFile.mkdirs()
            output.asFile.writeText(JsonOutput.prettyPrint(JsonOutput.toJson(graph)) + "\n")
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
