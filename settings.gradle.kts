// SPDX-License-Identifier: Apache-2.0
pluginManagement { repositories { gradlePluginPortal(); mavenCentral() } }
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { mavenCentral() }
}
rootProject.name = "arcforges-contracts"
include("contracts-proto", "contracts-client", "contracts-connect-client", "contract-fixtures")
rootProject.children.forEach { it.projectDir = file("src/public/kotlin/${it.name}") }
