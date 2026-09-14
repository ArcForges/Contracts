# SPDX-License-Identifier: Apache-2.0
"""Prepare an independently restored Maven consumer, with no producer references."""

import os
from pathlib import Path
import shutil

from contracts import ROOT
from kotlin_tools import gradle
from maven_tools import zip_contents


def prepare(consumer: Path, directory: Path, manifest: dict, env: dict,
            evidence: Path, update_locks: bool = False) -> tuple[Path, dict]:
    project = consumer / "kotlin"
    shutil.copytree(ROOT / "tests/public/KotlinClient", project,
                    ignore=shutil.ignore_patterns("build", ".gradle", ".kotlin"))
    for name in ("gradlew", "gradlew.bat", "gradle.properties", "gradle/wrapper/gradle-wrapper.jar",
                 "gradle/wrapper/gradle-wrapper.properties", "gradle/libs.versions.toml"):
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, project / name)
    (project / "gradlew").chmod(0o755)
    feed = consumer / "maven-feed"
    bundle = next(entry for entry in manifest["files"] if entry["kind"] == "maven")
    for name, contents in zip_contents((directory / bundle["name"]).read_bytes()).items():
        path = feed / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    isolated_env = dict(env, GRADLE_USER_HOME=str(consumer / "gradle-cache"))
    args = [f"-PreleaseVersion={manifest['version']}", f"-PcandidateRepository={feed.as_uri()}"]
    if update_locks:
        verification = project / "gradle/verification-metadata.xml"
        verification.parent.mkdir(parents=True, exist_ok=True)
        if not verification.exists():
            verification.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">
  <configuration><verify-metadata>true</verify-metadata><verify-signatures>false</verify-signatures>
    <trusted-artifacts><trust group="io.github.arcforges" reason="Exact candidate manifest verified before isolated restore" /></trusted-artifacts>
  </configuration><components />
</verification-metadata>
''', encoding="utf-8")
        gradle("resolveLockedDependencies", "installDist", *args, "--write-locks",
               "--write-verification-metadata", "sha256", cwd=project, env=isolated_env)
        for name in ("gradle.lockfile", "settings-gradle.lockfile", "gradle/verification-metadata.xml"):
            (ROOT / "tests/public/KotlinClient" / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / name, ROOT / "tests/public/KotlinClient" / name)
    gradle("resolveLockedDependencies", "installDist", *args, cwd=project, env=isolated_env)
    for name in ("gradle.lockfile", "settings-gradle.lockfile", "gradle/verification-metadata.xml"):
        shutil.copyfile(project / name, evidence / ("kotlin-" + Path(name).name))
    executable = project / "build/install/kotlin-archive-consumer/bin" / ("kotlin-archive-consumer.bat" if os.name == "nt" else "kotlin-archive-consumer")
    return executable, isolated_env
