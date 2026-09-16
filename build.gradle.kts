// SPDX-License-Identifier: Apache-2.0
import groovy.json.JsonOutput
import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.component.ProjectComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult
import org.jetbrains.kotlin.gradle.dsl.KotlinJvmProjectExtension
import org.jetbrains.dokka.gradle.DokkaExtension
import org.jetbrains.dokka.gradle.tasks.DokkaGeneratePublicationTask

plugins {
    base
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.dokka) apply false
}

val release = providers.gradleProperty("releaseVersion").getOrElse("1.0.0-ci.0.0")
require(Regex("1\\.0\\.0-ci\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)").matches(release))
val codegen by configurations.creating { isCanBeConsumed = false }
dependencies {
    for (platform in listOf("windows-x86_64", "linux-x86_64", "osx-x86_64")) {
        codegen("io.grpc:protoc-gen-grpc-java:${libs.versions.grpc.asProvider().get()}:$platform@exe")
    }
    codegen("io.grpc:protoc-gen-grpc-kotlin:${libs.versions.grpc.kotlin.get()}:jdk8@jar")
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
    if (name != "contract-fixtures") {
        apply(plugin = "org.jetbrains.kotlin.jvm")
        apply(plugin = "org.jetbrains.dokka")
        extensions.configure<KotlinJvmProjectExtension> {
            jvmToolchain(17)
            sourceSets.named("main") { kotlin.srcDir("generated/kotlin") }
        }
        extensions.configure<DokkaExtension> {
            dokkaSourceSets.configureEach {
                jdkVersion.set(17)
                // Offline documentation: no mutable external package-list downloads.
                enableJdkDocumentationLink.set(false)
                enableKotlinStdLibDocumentationLink.set(false)
                enableAndroidDocumentationLink.set(false)
            }
        }
    }
    extensions.configure<JavaPluginExtension> {
        toolchain.languageVersion.set(JavaLanguageVersion.of(17))
        withSourcesJar()
        if (project.name == "contract-fixtures") withJavadocJar()
    }
    extensions.configure<SourceSetContainer> {
        named("main") {
            java.srcDir("generated/java")
            resources.srcDir(rootProject.layout.projectDirectory.dir("artifacts/maven-metadata/${project.name}"))
        }
    }
    tasks.withType<JavaCompile>().configureEach { options.encoding = "UTF-8"; options.release.set(17) }
    tasks.withType<Javadoc>().configureEach { options.encoding = "UTF-8" }
    tasks.withType<Jar>().configureEach {
        from(rootProject.file("LICENSE")) { into("META-INF") }
    }
    val documentation = if (name != "contract-fixtures") {
        tasks.register<Jar>("javadocJar") {
            archiveClassifier.set("javadoc")
            from(tasks.named<DokkaGeneratePublicationTask>("dokkaGeneratePublicationHtml").flatMap { it.outputDirectory })
        }
    } else tasks.named<Jar>("javadocJar")
    extensions.configure<PublishingExtension> {
        publications {
            create<MavenPublication>("maven") {
                from(components["java"])
                if (project.name != "contract-fixtures") artifact(documentation)
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
