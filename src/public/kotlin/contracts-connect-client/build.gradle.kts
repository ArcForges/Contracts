// SPDX-License-Identifier: Apache-2.0
plugins { `java-library`; alias(libs.plugins.kotlin.jvm) }
dependencies {
    api(project(":contracts-proto"))
    api(libs.connect.core)
}
