# SPDX-License-Identifier: Apache-2.0
"""Canonical versions and trusted push identities, shared by packing and publishing."""

import os
import re
from contracts import run

NUMBER = r"(0|[1-9][0-9]*)"
STABLE = rf"{NUMBER}\.{NUMBER}\.{NUMBER}"
CI = rf"1\.0\.0-ci\.{NUMBER}\.{NUMBER}"


def stable(value: str) -> bool:
    return re.fullmatch(STABLE, value) is not None


def maven_version(build: str) -> str:
    if stable(build):
        return build
    if re.fullmatch(CI, build):
        return "1.0.0-SNAPSHOT"
    raise ValueError("Unsupported build version")


def selected_version() -> str:
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/"):
        value = ref.removeprefix("refs/tags/v")
        if not ref.startswith("refs/tags/v") or not stable(value):
            raise ValueError("Release tag must be canonical vX.Y.Z")
        # Checkout fetch-depth: 0 provides the remote main history. No credentials
        # are needed here. A tag on an unmerged branch is not a release input.
        run("git", "merge-base", "--is-ancestor", os.environ["GITHUB_SHA"], "origin/main")
        return value
    return f"1.0.0-ci.{os.environ['GITHUB_RUN_NUMBER']}.{os.environ['GITHUB_RUN_ATTEMPT']}"


def authorize(build: str) -> None:
    ref = os.environ.get("GITHUB_REF", "")
    if ref == "refs/heads/main":
        if not re.fullmatch(CI, build):
            raise ValueError("Main publication requires a CI build version")
    elif ref == "refs/tags/v" + build and stable(build):
        if selected_version() != build:
            raise ValueError("Tag and candidate versions differ")
    else:
        raise ValueError("Publishing is restricted to main or matching canonical release tags")


if __name__ == "__main__":
    value = selected_version()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"version={value}\n")
