# WP00.01: derived policy declaration verification

> Historical plan/evidence. Current execution follows [AGENTS.md](../../AGENTS.md) and Design P2-017;
> hosted runtime/consumer gates and repeated public-byte checks below are superseded, not instructions to repeat them.

Design [P2-016](https://github.com/ArcForges/ArcForges-Design/blob/1607374e81955f0a47f319cd6cc8ba1c6e254157/docs/decisions/phase-2-specification-decisions.md#rule-p2-016)
assigns the AGPL glossary/invariant exporter to DesktopPlatform. Contracts remains
the Apache naming-policy owner. No Design program, AGPL exporter or AGPL data is
copied into this repository; test records are independently authored examples.

Policy schema 2 registers exactly `DesktopPlatform/eng/policy/glossary-terms.json`,
the reviewed Design commit, glossary source digest and canonical declaration digest.
The scanner rejects duplicate keys, unknown envelope or row fields, incorrect
ownership/source metadata and changed declaration bytes. After validation it removes
only `forbiddenAliases` values from scanning and scans every other decoded JSON
field, including escaped strings. Another path or repository receives no allowance.
The existing hash-bound provenance treatment is unchanged. Registration can precede
the producer PR; WP00.01 acceptance must observe the actual export in the nine-root scan.

The canonical array digest is SHA-256 of UTF-8 JSON with recursively sorted object
keys, no ASCII escaping and compact separators, retaining array order and all string
values. This digest does not establish copyright or package capability.

Validation includes 28 naming tests with real temporary Git repositories: source and
declaration mutations, unknown nested fields, escaped forbidden values, copies,
invalid owner/path/digest registrations and duplicate JSON keys. The complete
tooling suite, locked producer build, packaged consumers and security checks remain
required. `artifacts/evidence/wp00-01-family.json` records the actual local nine-root
scan and the consumed declaration. This record predates its PR CI and post-merge registry
publication; WP00 is accepted in the Design [WP00 stage acceptance](https://github.com/ArcForges/ArcForges-Design/blob/7e56614ced01a12c84eb2047071d14399249ee90/docs/assurance/wp00-stage-acceptance.md); no product-readiness gate
closes from this policy change.
