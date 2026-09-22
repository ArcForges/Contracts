# Reviewed dependency admission

The owner policy at `eng/policy/dependency-policy.json` binds the complete locked
NuGet/npm/Maven closure and exact normalized hashes of manifests, locks, toolchain
inputs and source provenance records. Reviewed cached nuspec/POM metadata and npm
lock declarations supply package-specific licences and source hashes. Maven parent
POM inheritance is recorded explicitly. Stax2's cached licence states BSD-2-Clause;
the existing `javax.annotation-api` CDDL-1.1 option remains reference-only. No
registry download or blanket group-name licence inference is needed by the checker.

`python eng/dependency_admission.py` checks the real source/lock closure offline.
`python -m unittest discover -s tests/tooling -p test_dependency_admission.py -v`
checks rejection behavior without package archives or network access. The existing
source provenance, generated public/internal access, locked restores and runtime
package SBOM/legal checks remain independently required. This policy does not
implement later internal schemas or grant public clients access to internal SDKs.

Every dependency or framework change requires a reviewed replacement input receipt:
owner, maintenance assessment, changed closure and every named upgrade check must
be addressed. Hash refresh alone is insufficient. Major framework changes require
Native AOT/trim and affected Android Kotlin/JVM/ART/R8/transport assessments under
VG-08. Relevant runtime/performance/migration diagnostics run locally when affected
and supported by existing tools; absent evidence stays explicit. No new provisioning
or hosted consumer/device execution is implied.

Publication retains exact main NuGet/npm CI versions, the accepted npm `latest`
candidate convention and Maven main SNAPSHOT receipts. Consumers cannot select
mutable tags or SNAPSHOT through this dependency policy. Stable package construction
checks the full dependency closure for prereleases before building; the existing
canonical tag/main ancestry checks, OIDC environments, immutable collision guards
and source-free Central signing remain authoritative. No stable tag was created.

Review receipts under `eng/policy/dependency-reviews/` are append-only. The checker
compares the accepted Git tree and preserves every historical coordinate/integrity
binding: even a newly reviewed snapshot cannot change bytes under an existing
NuGet/npm version or Maven artifact coordinate. Add a successor receipt for an
actual reviewed upgrade; never edit or delete an earlier receipt.
