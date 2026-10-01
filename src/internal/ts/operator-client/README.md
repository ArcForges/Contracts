# @arcforges/operator-client

Internal operator protobuf contracts; Operations-only import boundary.

Apache-2.0. This package contains the generated `arcforges.operator.v1.OperatorService` (31 unary methods: the 29 `operator.*`
operations of Registry04 section 9.1 plus `catalog.review` and `catalog.revoke`), its typed proposal, mutation, result and
configuration records, shape checks and the explicit `contractServices` catalogue. Public customer, personal-access-token,
agent and service callers are refused by the separate operator origin; these generated shapes establish no case, incident,
role or approval authority, and no runtime handler, identity-provider session or owner service is provided here. Shared
foundation, public support, commerce and catalog records are imported from `@arcforges/proto` rather than duplicated. Registry
visibility does not change the import boundary.
