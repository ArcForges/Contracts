# WP00.02: project licence boundaries

The accepted [declaration profile](https://github.com/ArcForges/ArcForges-Design/blob/6ba885ad38dd71de532c74d7b69f439d01d19a0a/docs/architecture/01-solution-and-project-layout.md#41-project-declaration-and-verification-profile)
assigns all Contracts source, tools, fixtures and public/internal contracts to
Apache-2.0 / Apache. `eng/policy/licence-boundary.json` enumerates 15 current
project/build manifests, including the signing-only and isolated consumer builds.
New tracked or nonignored project manifests must be registered and declared.

The bounded change adds explicit MSBuild, npm and Gradle properties and checks the
actual Git inventory and locked first-party package closure before building.
MSBuild checks evaluated properties and project-reference containment, including
command-line overrides. Gradle checks the evaluated root and every subproject;
the same checks travel with independent consumer builds. No adjacent repository
is imported or built. The Apache checker is authored here, independently of the
AGPL family verifier owned by DesktopPlatform.

```text
python eng/contracts.py restore
python eng/check_licences.py
python eng/contracts.py pack --version 1.0.0-ci.0.0
python -m unittest discover -s tests/tooling -v
python eng/contracts.py consume --aot
npm run format:check
```

Negative tests cover missing/inconsistent declarations, a changed repository
assignment, new/unregistered projects, imported and command-line overrides,
escaped references, transitive AGPL/unknown package families and an npm alias.
Real MSBuild target execution rejects an AGPL reference and an escape. An actual
Gradle invocation rejects an evaluated subproject override.

CI retains `artifacts/evidence/licence-boundary.json` with commit/dirty identity,
the naming report and Gradle's `build/reports/licence-boundary.json`.
The naming declaration is repinned to the accepted Design commit above; glossary
declaration bytes and digests are unchanged. The immutable candidate and isolated
C#/TypeScript/Kotlin/JVM/AOT transport gates remain required, followed by registry
publication and public-byte verification for the merged commit. Those run-specific
results must be checked separately; source policy tests do not prove publication,
Android device acceptance, product functionality or commercial readiness.
