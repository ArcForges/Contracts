# WP00.00 product and naming freeze

The authoritative design is [P2-015 and the naming policy](https://github.com/ArcForges/ArcForges-Design/blob/4382eec97e45f8abcc81fdcb28221e907f44ddde/docs/architecture/28-product-naming-policy.md), merged in [Design PR13](https://github.com/ArcForges/ArcForges-Design/pull/13) and refined by [Design PR14](https://github.com/ArcForges/ArcForges-Design/pull/14).

The bounded plan maps the current product/feature identities, historical dispositions,
provider roles and association reservations into one Apache-2.0 policy file. Contracts
owns its validator and Git inventory scanner. Other roots are read-only scan targets;
no runtime package, generated contract or adjacent-source consumer is introduced.

The scan includes tracked files (even tracked ignored/generated files), non-ignored
new files and file paths. Raw UTF-8/UTF-16 checks include binary resource payloads.
Missing tracked files, symbolic entries, invalid policy and stale/unused exceptions
fail. The only eligible exception is an exact, reviewed, hash-bound provenance record.
One exact exception preserves DesktopPlatform's existing tracked traceability seed: all 50 matches are fixed-commit source-baseline entries,
reviewed individually and bound to its committed SHA-256. No other artifact path is exempted. Retired wire IDs are policy data; this step does
not claim whole-schema enforcement before WP03/WP05.

Local verification uses real temporary Git repositories and the production command:
clean scan/report success, forbidden content failure, mixed-case identifier and path
matching, generated and UTF-16 resources, missing files, symbolic Git entries,
spoofed remote owners, malformed policy and provenance exception abuse. These are
source-policy tests, not product or provider runtime evidence.

CI runs the naming scan and retains its JSON receipt, then the existing tooling test
suite, package/consumer and security gates. Applicable CI and main publication remain
pending until the corresponding actual run completes. WP02/WP05 own continuing
family-wide build enforcement. WP30 owns the already selected Android prerelease
identity migration; WP33/WP36/WP53 own real native association/installer behavior.

## Collected obligations and observed local evidence

| Obligation                                        | Change / owner                                  | Evidence                                                                                        |
| ------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Current product, companion and feature identities | Single naming JSON / Contracts                  | Closed-schema and identity checks; preserved bootstrap package names                            |
| Historical name dispositions and provider roles   | Policy data / Contracts                         | Excluded products have no alias; provider roles checked independently                           |
| Native file identifiers without new format scope  | Reserved Scope/Slate entries / product owners   | No association for Notes or companions; implementation stays at format/distribution owners      |
| Scan real source, paths and resources             | Portable scanner / Contracts                    | Actual nine-root Git inventories, UTF-16 and generated/ignored tracked-file tests               |
| Minimal provenance exceptions                     | One exact historical artifact / DesktopPlatform | 50 source-baseline values reviewed; committed/working SHA-256 identical; no directory exception |
| Continuing check and traceable results            | Existing CI / Contracts                         | Scan plus tooling suite; JSON evidence retained. Family integration stays WP02/WP05             |

Local scan on 2026-09-18, before commit (the Contracts row includes this candidate's
working changes); other roots were clean and fetched from origin/main. All nine
returned pass. Source-policy evidence only; no published package is required by WP00.

| Repository      | Observed input HEAD                        | Files | Exceptions used | Result |
| --------------- | ------------------------------------------ | ----- | --------------- | ------ |
| DesktopPlatform | `97fe0afb01d7de7083ca43332d1f33092a0521fe` | 208   | 1               | pass   |
| Contracts       | `d77aefabe0676dbe32845cbcf50aee361eb3fe7e` | 134   | 0               | pass   |
| ArcNotes        | `d0d555e64e5f19e8f2d8139ab49f6bceb04548ea` | 54    | 0               | pass   |
| ArcScope        | `27d6708ae3204e98c5c9aa5c380805b703ef1584` | 54    | 0               | pass   |
| ArcSlate        | `075558c548a71369568064b65007ca03517913b7` | 54    | 0               | pass   |
| Cloud           | `6554400c04817491fe68d5e6319434034c5dc356` | 70    | 0               | pass   |
| AI              | `d6a0b55c4ac0324a3103a1de553121f3bc82406a` | 57    | 0               | pass   |
| Web             | `86d6fded796d060eb064125baca7db690bc65419` | 72    | 0               | pass   |
| Mobile          | `15145a4b4139525aae4185f0d2d20c87ec91686a` | 58    | 0               | pass   |

Policy SHA-256: `4c7f4771ffc9c11234a4a098aef5a3008e2109b6fee6e4b0a5855243561d41b2`. The executable JSON receipt additionally records each actual inventory digest and dirty state. CI produces a new receipt for its checked-out candidate; this table records the local collection, not a claim about a future commit.
