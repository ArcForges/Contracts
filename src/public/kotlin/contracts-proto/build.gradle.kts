// SPDX-License-Identifier: Apache-2.0
plugins { `java-library`; alias(libs.plugins.kotlin.jvm) }
dependencies { api(libs.protobuf.kotlin.lite) }

// The owner vector is an ordinary offline source-component check.
kotlin.sourceSets.named("test") {
    kotlin.srcDir(rootProject.file("tests/kotlin"))
}
val installationPossessionVectors = tasks.register<JavaExec>("installationPossessionVectors") {
    dependsOn(tasks.named("testClasses"))
    classpath = sourceSets["test"].runtimeClasspath
    mainClass.set("io.github.arcforges.contracts.tests.CON34InstallationPossessionTest")
    args(rootProject.file("fixtures/public/con-34-installation-possession.json").absolutePath)
}
tasks.named("check") { dependsOn(installationPossessionVectors) }
val installationPossessionAdjuncts = tasks.register<JavaExec>("installationPossessionAdjuncts") {
    dependsOn(tasks.named("testClasses"))
    classpath = sourceSets["test"].runtimeClasspath
    mainClass.set("io.github.arcforges.contracts.tests.CON34InstallationAdjunctTest")
}
tasks.named("check") { dependsOn(installationPossessionAdjuncts) }
tasks.processResources {
    from(rootProject.file("public/proto")) { into("proto"); exclude("arcforges/extensions/**") }
    from(rootProject.file("artifacts/contracts.binpb"))
}

// Project licence metadata is verified independently of the root LICENSE.
extra["spdxLicense"] = "Apache-2.0"
extra["licenceBoundary"] = "Apache"
