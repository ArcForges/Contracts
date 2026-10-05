# Authorization declaration assertions

GOV.16 consumes the CON.18 operation metadata gate. The matrix is produced from
the current authored operation exports, not from a second catalogue. Pending
catalogue entries remain pending, and migration examples do not become production
bindings.

The independent hostile-input fixtures assert the owner/deployment chain and
resource, context and connector egress requirements as offline policy decisions.
Fixture credentials and readiness statements are symbolic inputs. They are not
proof of authentication, runtime enforcement, a live provider or an implemented
Cloud/DesktopPlatform binding.

## Identity, workspace, device and session bindings

`binding-classification.json` classifies every registered `identity.*`,
`workspace.*` and `device.*` operation against closed binding kinds (user,
authenticationIdentity, session, device, workspace, apiToken, flow). An operation
without a classification, a stale classification, an unknown binding, a tool actor
on an identity-bearing binding, an automation-token operation that mutates, or a
plan whose access contradicts the operation's idempotency fails the report.

The classification is checked against facts the producers declared, not against
producer source. `producer-declarations.json` is a reviewed snapshot of those
facts with an exact repository, commit and file digest per source:

- Cloud (CLOUD.11, Cloud `d9947f68`): the physical identity, device and workspace
  tables with their owner relations and uniqueness, the four distinct identifier
  types, the eight identity plans and the `account-enrollment` family.
- DesktopPlatform (PLT.38, `2ffeba33`): the fourteen decision steps, the four
  enforcement points and the steps each point runs.

CI validates the snapshot offline (exact commits, sanctioned source set, facts
bound to their digest). No producer checkout, network or build is needed. To move
or re-verify a pin, run explicitly against local checkouts (read through
`git show <commit>:<path>`, never the working tree):

    python tests/AuthorizationPolicyTests/producer_declarations.py verify --cloud <Cloud> --platform <DesktopPlatform>
    python tests/AuthorizationPolicyTests/producer_declarations.py write --cloud <Cloud> --cloud-commit <sha> --platform <DesktopPlatform> --platform-commit <sha>

A moved source or an edited fact is refused as a stale pin. Every owner/deployment
chain obligation is `bound` to producer facts, `declared-port` (the enforcement
point is declared but its fact source is a host port with no production
implementation) or `pending-producer` with a named reason. The report states these
limits; no obligation is promoted without a verified fact.

Run `python -m unittest discover -s tests/AuthorizationPolicyTests -v`.
The report command is `python tests/AuthorizationPolicyTests/assertions.py
--report artifacts/evidence/authorization-boundaries.json`.

Classified operations report `behavior: not-bound`: this is declared metadata
only, with no operation handler, store, runtime enforcement or live provider.
