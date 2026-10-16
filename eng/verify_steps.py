# SPDX-License-Identifier: Apache-2.0
"""Local verification steps of Contracts, loaded by eng/verify.py (which injects `Step`).

Hosted CI ran on Ubuntu only, so every check runs in WSL Debian, in the Linux-native verification clone checked out at
the pushed commit. The `wsl` lane is the `Build candidate` job of .github/workflows/ci.yml followed by the build,
naming and architecture steps of the `secrets` job of .github/workflows/security.yml (they share one checkout, so they
run in order and the security build is incremental on the candidate's Release build). The secret scan of the pushed
range and actionlint (only when a workflow changed) run in their own lanes, concurrently.

Differences from the hosted jobs, all because the hosted values come from GitHub:
- `CI` is not set: Directory.Build.targets and eng/build_identity.py require a complete GitHub run identity when it
  is, so local builds carry the `local` build identity instead of `ci`.
- The PR base the scripts read from the GitHub event (provenance, dependency admission, contract-access history) is
  the merge base with main: the first step points the clone's `origin/main` at it, which is where the scripts look
  when no event exists, and the explicit provenance step passes it as `--base`.
- The candidate is packed at the local version `1.0.0-ci.0.0` (the `pack` default); the run-number selection of
  eng/release_channels.py and the artifact uploads are GitHub-bound (the selection logic is covered by the tooling
  tests).
- The hosted architecture gate reads the hosted job identity; the step gives it the pushed commit as GITHUB_SHA and
  the job id `secrets` for that one process, and the gate still checks that the checkout is exactly that commit.
- The secret scan covers the pushed range ({range}), not the full history: history before it was scanned when it was
  pushed.
Every change runs the full profile: the naming, provenance, formatting, packaging and foundation checks read the
documentation too, so there is no Markdown that no check reads.
"""

REPOSITORY = "Contracts"

# Tool versions that key a reusable pass (the python running eng/verify.py is added by the core).
FINGERPRINT = {
    "wsl": {
        "dotnet-sdks": "dotnet --list-sdks | tr '\\n' ' '",
        "node": "node --version",
        "npm": "npm --version",
        "python": "python --version",
        "git": "git --version",
    },
}

# The environment of ci.yml and security.yml, without CI=true (see above).
ENV = {"DOTNET_NOLOGO": "true", "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "PYTHONUTF8": "1"}

LOCAL_VERSION = "1.0.0-ci.0.0"
ARCHITECTURE = "tests/ArchitectureTests/bin/Release/net10.0/ArcForges.Contracts.ArchitectureTests.dll"

# The hosted Security/secrets scan (same pinned image digest and gitleaks config), over the pushed range, with no
# network and a read-only mount of the verification clone.
SECRET_SCAN = (
    "docker run --rm --network none -v \"$PWD:/repo:ro\" "
    "-e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo "
    "ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f "
    "git /repo --redact --no-banner --verbose --config /repo/.gitleaks.toml "
    "--log-opts=\"--full-history --diff-filter=tuxdb {range}\""
)

# actionlint as pinned in the product repositories' CI, cached once in WSL; the archive is checked on every run.
ACTIONLINT = (
    "set -euo pipefail; v=1.7.12; "
    "sum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8; "
    "d=\"$HOME/.cache/arcforges-verify/tools\"; t=\"$d/actionlint_${v}_linux_amd64.tar.gz\"; mkdir -p \"$d\"; "
    "if [ ! -f \"$t\" ]; then "
    "curl --fail --silent --show-error --location --output \"$t.part\" "
    "\"https://github.com/rhysd/actionlint/releases/download/v${v}/actionlint_${v}_linux_amd64.tar.gz\"; "
    "echo \"$sum  $t.part\" | sha256sum --check --quiet; mv \"$t.part\" \"$t\"; fi; "
    "echo \"$sum  $t\" | sha256sum --check --quiet; "
    "mkdir -p \"$d/actionlint-$v\"; tar -xzf \"$t\" -C \"$d/actionlint-$v\" actionlint; "
    "\"$d/actionlint-$v/actionlint\""
)


def workflows_changed(changed: list[str]) -> bool:
    return any(path.startswith(".github/workflows/") for path in changed)


def select_profile(changed: list[str]) -> str:
    return "full"


def wsl(step_id: str, command: str, timeout: int, **options) -> Step:
    return Step(step_id, "wsl", command, timeout=timeout, env=ENV, **options)


STEPS = [
    # ci.yml, Build candidate
    wsl("restore", "set -e; git update-ref refs/remotes/origin/main {base}; python eng/contracts.py restore", 600),
    wsl("dependency-admission", "python eng/dependency_admission.py", 300),
    wsl("naming", "python eng/check_naming.py --report artifacts/evidence/naming.json", 300),
    wsl("provenance", "python eng/check_provenance.py --owner Contracts --base {base}", 300),
    wsl("contract-access-test", "node --test tests/tooling/contract_access.test.mjs", 300),
    wsl("format-audit", "set -e; npm run format:check; npm audit --audit-level=high; git diff --check", 300),
    wsl("pack", f"python eng/contracts.py pack --version {LOCAL_VERSION}", 2400),
    wsl("tooling-tests", "python -m unittest discover -s tests/tooling -v", 900),
    wsl("clean-tree", "git diff --exit-code", 60),
    # security.yml, Secret scan job after the scan (the locked restore already ran in `restore`)
    wsl("security-build", "dotnet build ArcForges.Contracts.slnx --configuration Release --no-restore "
        "--verbosity minimal", 1200),
    wsl("security-naming", "python eng/check_naming.py --report artifacts/evidence/naming.json", 300),
    wsl("architecture-hosted", f"GITHUB_ACTIONS=true GITHUB_JOB=secrets GITHUB_SHA={{sha}} dotnet {ARCHITECTURE} "
        "--hosted", 1200),
    # security.yml, the secret scan itself, over the pushed range
    wsl("secret-scan", SECRET_SCAN, 900, lane="scan"),
    wsl("actionlint", ACTIONLINT, 300, lane="actionlint", when=workflows_changed),
]
