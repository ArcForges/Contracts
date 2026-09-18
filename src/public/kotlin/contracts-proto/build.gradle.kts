// SPDX-License-Identifier: Apache-2.0
plugins { `java-library`; alias(libs.plugins.kotlin.jvm) }
dependencies { api(libs.protobuf.kotlin.lite) }
tasks.processResources {
    from(rootProject.file("public/proto")) { into("proto") }
    from(rootProject.file("artifacts/contracts.binpb"))
}

// Project licence metadata is verified independently of the root LICENSE.
extra["spdxLicense"] = "Apache-2.0"
extra["licenceBoundary"] = "Apache"
