# Security policy

## Supported versions

This repository is a prerelease packaging foundation. Security fixes target the
latest main build; there is no production support or response-time commitment.
Pin exact package versions and move to a verified fixed version when advised.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/ArcForges/Contracts/security/advisories/new).
Include the affected package/version, a minimal reproduction, impact and any
proposed mitigation. Redact credentials and personal data. Avoid public issues
for unpatched vulnerabilities.

If the private reporting form is unavailable, open a public issue requesting a
private contact channel without disclosing the vulnerability itself.

## Release security

CI has read-only permissions by default. Only the main and release-tag NuGet and
npm (`@arcforges/ai-internal` only) registry jobs request OIDC identity, after the
generation, build and offline candidate checks. Both publishers use the checked
candidate archives and cannot rebuild them. The Maven Central channel, its Portal
token and its PGP signing key are retired (CON.40): no workflow reads them, and
removing the unused `maven-central` environment secrets is a repository-settings
task for the owner. Already published packages stay immutable; nothing is
unpublished, deprecated or deleted. Never commit credentials or signing material.

Dependency updates, dependency review, CodeQL and secret scanning complement
review; passing these checks does not prove the absence of vulnerabilities.
