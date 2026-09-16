// SPDX-License-Identifier: Apache-2.0
plugins { application; alias(libs.plugins.kotlin.jvm) }
kotlin { jvmToolchain(17) }
application { mainClass.set("io.github.arcforges.tests.MainKt") }
val release = providers.gradleProperty("releaseVersion").get()
dependencies {
    implementation("io.github.arcforges:contracts-connect-client:$release")
    implementation("io.github.arcforges:contract-fixtures:$release")
    implementation(libs.connect.okhttp)
    implementation(libs.connect.google.javalite)
    implementation(libs.gson)
}
dependencyLocking {
    lockAllConfigurations()
    lockMode.set(LockMode.STRICT)
    // Exact first-party candidate files are hash-verified before this isolated restore.
    ignoredDependencies.add("io.github.arcforges:*")
}
tasks.register("resolveLockedDependencies") {
    doLast { configurations.filter { it.isCanBeResolved }.forEach { it.resolve() } }
}
