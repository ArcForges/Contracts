// SPDX-License-Identifier: Apache-2.0
plugins { `java-library`; alias(libs.plugins.kotlin.jvm) }
dependencies {
    api(project(":contracts-proto"))
    api(libs.grpc.protobuf.lite)
    api(libs.grpc.stub)
    api(libs.grpc.kotlin.stub)
    api(libs.coroutines.core)
}

// Project licence metadata is verified independently of the root LICENSE.
extra["spdxLicense"] = "Apache-2.0"
extra["licenceBoundary"] = "Apache"
