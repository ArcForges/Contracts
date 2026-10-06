# Public operation authorization catalog

CON.26 publishes `PublicOperationCatalog` in `ArcForges.Contracts.PublicApi.Operations`
and `EventOperationCatalog` in `ArcForges.Contracts.Events.Operations`. `All` contains
immutable public business metadata; `TryGet` uses exact ordinal operation IDs.
Unknown, cross-owner, operator, local/helper and HTTP-exception operations are not
admitted by these catalogs. Hosts can project both catalogs through their own
abstractions without making business modules depend on Contracts assemblies.

The existing `eng/operations` shards own every authorization field. Generation
validates the shards with the operation-scope gate and checks complete owned
business method coverage against compiled descriptor sets. The retained Hello
migration example is excluded. Service/method bindings, ownership scope,
idempotency, profile, source rule and every authorization field are preserved.
No wire schema, service, package identity or dependency is added.

`PatEligible` is explicitly false for denied operations. Their `PatScopes` is
empty; eligible operations have exactly their operation ID as a scope. The tenancy
`Scope` property is not a token scope. The existing closed Design allowlist has
twelve operations, including `support.listCases`; CON.26 corrects that row's
previously false metadata and rejects future silent omissions.

Proposal-derived `approval.decide` risk, step-up and local-presence requirements
remain null literals with exact verified-source expressions in `RiskSource`,
`StepUpSource` and `LocalPresenceSource`. Consumers must resolve those expressions
against the verified approval proposal, rather than treating null as false.

This is production authorization metadata, not a grant or runtime authorization
decision. Hosts must still authenticate, bind ownership/workspace and current
epochs, enforce applicable requirements and reject unmounted operations.
Constructing a `PublicOperationPolicy` does not add it to the catalogs. All exposed
collections copy or wrap immutable storage; no registration or reflection
discovery API exists.

`python eng/contracts.py generate --check` checks reproducibility.
`StructureTests --con-26` checks every authored field, compiled descriptor coverage,
an independent twelve-operation PAT oracle, unknown/private boundaries, proposal
sources, immutable collections and concurrent lookup. The existing serialization
probe executes these APIs in its actual Native AOT artifact. These component
results do not establish live Cloud authorization or full commercial acceptance.

The architecture host consumes the actual published `ArcForges.Build.Policy` `1.0.0-ci.111.1` from DesktopPlatform source `5f2c09010c61094e9285d6e6f71a9ca62c4c8689`. Its three exact non-wire approvals bind the qualified symbol, owning project, source path, normalized source SHA-256 and metadata kind. The shared policy checks real compiled and disk inputs, immutable closed shapes and forbidden serializer/transport reachability; no generated-wire schema is invented. Approval mismatch, missing approval, ambiguity, foreign ownership or simultaneous wire classification fails closed. The AGPL build source remains private to the non-packable architecture test executable and never enters a redistributed Contracts package.
