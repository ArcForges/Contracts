# ArcForges contract-fixtures

`io.github.arcforges:contract-fixtures` provides the exact release's shared
`arcforges/fixtures/hello.json` resource and a Java 17 accessor:
`io.github.arcforges.contracts.fixtures.ContractFixtures.openHello()`.
The caller closes the UTF-8 resource stream. Apache-2.0.

Use this artifact in the consumer's test dependencies, at the same version as
the messages/client. It has no runtime dependencies and does not include a
server. Cases cover ASCII, Unicode and the empty-name INVALID_ARGUMENT result.
The producer verifies them against a real C# gRPC host using the published JARs.
