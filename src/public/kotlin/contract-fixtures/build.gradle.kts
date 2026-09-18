// SPDX-License-Identifier: Apache-2.0
plugins { `java-library` }
tasks.processResources {
    from(rootProject.file("fixtures/public")) {
        include("*.json")
        into("arcforges/fixtures")
    }
}

// Project licence metadata is verified independently of the root LICENSE.
extra["spdxLicense"] = "Apache-2.0"
extra["licenceBoundary"] = "Apache"
