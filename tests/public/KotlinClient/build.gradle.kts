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
