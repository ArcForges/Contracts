// SPDX-License-Identifier: Apache-2.0
pluginManagement { repositories { gradlePluginPortal(); mavenCentral() } }
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        exclusiveContent {
            forRepository { maven { name = "candidate"; url = uri(providers.gradleProperty("candidateRepository").get()) } }
            filter { includeGroup("io.github.arcforges") }
        }
        mavenCentral()
    }
}
rootProject.name = "kotlin-connect-archive-consumer"
