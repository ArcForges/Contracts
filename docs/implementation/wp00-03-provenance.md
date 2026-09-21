# Reuse and provenance (WP00.03)

> Historical plan/evidence. Current execution follows [AGENTS.md](../../AGENTS.md) and Design P2-017;
> hosted runtime/consumer gates and repeated public-byte checks below are superseded, not instructions to repeat them.

The accepted [Design profile](https://github.com/ArcForges/ArcForges-Design/blob/1d2a2aa800bc93b26d12337e669bdcf3fd85150f/docs/assurance/reference-coverage-and-provenance.md#31-current-repository-implementation-profile)
governs this process. Contracts remains Apache-2.0. Source provenance and the
existing dependency closure checks are separate requirements.

Use `eng/provenance/template.json` to prepare
`eng/provenance/records/<material-name>-r<number>.json` before reusing material.
Complete the exact repository, commit, paths, file-level licence evidence,
attribution, targets, disposition, oracle, NOTICE requirement and lifetime.
Generated material separately names all generator and input licence positions.
Temporary material needs an accountable owner and removal trigger. The template
contains placeholders and is never itself an approved record.

The Licensing and Provenance Owner reviews the actual source evidence and all
fields, then records reviewer, date and rationale. The PR review supplies the
review evidence; an `approved` value alone is not an approval. This role may be
exercised by the maintainer's authorized implementation reviewer. Boundary
questions go to the Architecture Owner, and product decisions to the Product
Owner. A conflict is registered in `eng/provenance/conflicts/<id>.json` with
`id`, `material`, `evidence`, `boundary`, `owner`, `requiredDecision`, `status`
and `resolution`. An unresolved conflict fails the audit and blocks the affected
material. Resolution cites a formal decision and a new admissible record, or
removes the material; it never silently changes the closed licence policy.

`eng/provenance/files.json` explicitly classifies every tracked file and every
non-ignored new file as authored metadata/source or an active record target.
Review additions and changes for newly reused material, including insertions in
existing authored files. The checker cannot infer authorship from source text.
Reused targets have exact hashes (`lf` for UTF-8 text, `raw` for binaries).
Legal documents are retained under their own copying terms; they do not grant
permission to import the implementation they describe. The decision table and
supported expressions in `eng/policy/reuse-policy.json` cannot be edited to grant
an exception without also changing the reviewed implementation and Design.

Used records cannot be modified, renamed or deleted. Retain retired records;
create a new revision with `supersedes` and move the complete target group to it.
The checker compares Git history with the PR/merge-group base, the previous main
commit on a push, or the fetched `origin/main` during local branch work. On the
primary main checkout it compares with committed HEAD. A missing comparison
commit fails; fetch history before checking. CI retains full history in the
candidate job. No sibling checkout or network source download is used by the
checker.

The initial four records reconcile the existing Gradle 9.7.1 wrapper, all 15
Hello binding outputs and five legal-text copies, and retain the protobuf
generator licence. They identify the inspected baseline and do not claim that
these records preceded historical copies. Wrapper regeneration was verified
against the official immutable Gradle source/distribution. The canonical Apache
text was compared with a pinned licence template; no historical download origin
is invented. Generator commits come from package metadata and immutable upstream
release/source evidence, including Grpc.Tools' exact protobuf submodule.

Packaging can add material absent from Git. Active artifact records are listed
in the inventory's `artifacts` array and bind the exact owning project, package,
artifact kind and immutable profile hash. Their generator/input licence
positions and notice obligations are required before packaging. The current
Dokka record covers all four Maven documentation archives, 42 fixed resources,
the complete generated API page inventory and the 81 actual Apache/MIT npm
components. Every one of the 515 emitted npm source files was checked against
its integrity-verified archive; subordinate licence paths and code headers were
reviewed. The two webpack runtime helpers use their actual nested versions,
style-loader 3.3.4 and css-loader 6.11.0. Prism's separately copied MIT resource
is bound to its exact Dokka source bytes.

The fixture module now uses the same Dokka 2.2.0 producer as the other modules.
This resolves the observed GPL-family JDK Javadoc script conflict without a
licence exception. Dokka's ten embedded OFL font files and exactly four
`@font-face` blocks are excluded; existing system font fallbacks keep the
documentation readable offline. Complete API pages, navigation and search are
retained. One owned CSS rule corrects the upstream theme's unreadable dark-mode
content links; its exact transformed bytes are also bound in the profile.
Fixed scripts, styles and icons must match reviewed upstream or
reproduced bytes. Generated pages must match their reviewed complete content
after replacing only the displayed candidate version and normalizing LF. An
API or generator/configuration change therefore requires a newly reviewed
profile and superseding record, never an automatic baseline refresh.

The 82 documentation legal-text records retain full original licences and
Dokka's NOTICE. Documentation-specific notices enter each documentation JAR;
runtime packages retain their own relevant source and dependency notices.
`eng/documentation_tools.py` checks raw generator output before staging, then
checks the actual archive again. Unknown/missing members, modified resources,
extra fonts, changed API content and missing full notices fail. The source-bound
`artifacts/evidence/documentation-provenance.json` receipt contains the bundle
and archive hashes, every member hash, matched record IDs and notice hashes.
CI retains this evidence. Prior published versions are not modified.

These HTML resources belong only to the developer API reference archives for
`contracts-proto`, `contracts-client`, `contracts-connect-client` and
`contract-fixtures`. Each module publishes a separate Maven `javadoc` companion;
its documentation pages and browser resources stay out of the runtime JAR.
The 12 Chromium, Firefox and WebKit scenarios inspect those four developer
reference archives: navigation, search, theme contrast and resource loading.
They provide no evidence about the Cloudflare-hosted Web product, Avalonia
desktop applications or the native Kotlin/Compose Android application. Desktop
and mobile UI follow their native implementation boundaries; this documentation
producer supplies no embedded browser, HTML UI or JavaScript UI to them.

Run these checks after updating reviewed records and the file inventory:

```text
python eng/check_provenance.py --owner Contracts --write-notice
python eng/check_provenance.py --owner Contracts
python -m unittest discover -s tests/tooling -p test_provenance.py -v
python eng/contracts.py generate --check
```

Only the first command regenerates `eng/provenance/NOTICE.txt`; ordinary checks
reject drift. Existing root and dependency notices stay intact. Packing first
validates provenance and appends package-relevant generator attribution and the
full protobuf BSD licence to each package NOTICE. Archive verification requires
these exact notices in NuGet, npm and every Maven main/source/documentation JAR.
CI retains `artifacts/evidence/provenance.json` with source and comparison commits,
dirty state, inventory counts and the notice digest. Tooling tests exercise
missing/invalid records, boundary violations, paths, generated inputs, temporary
lifetimes, history mutation and removal of package notices. Full formatting,
generation, candidate consumers, security and publication gates remain required.

This inventory covers current source provenance. It does not implement future
business contracts or establish product, device, provider or commercial readiness.
