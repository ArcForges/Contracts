// SPDX-License-Identifier: Apache-2.0
plugins { `java-library` }
tasks.processResources {
    from(rootProject.file("fixtures/public")) {
        include("*.json")
        into("arcforges/fixtures")
    }
}
