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

CI has read-only permissions by default. Only main NuGet/npm registry jobs request
OIDC identity, after generation, build and isolated package-consumer checks.
Maven Central uses its environment's Portal token and in-memory PGP signing key.
Rotate those credentials, keep the PGP public key available, and restrict the
environment to main. All publishers use checked archives; the signing-only build
cannot compile or replace them. Never commit credentials or signing material.

Dependency updates, dependency review, CodeQL and secret scanning complement
review; passing these checks does not prove the absence of vulnerabilities.
