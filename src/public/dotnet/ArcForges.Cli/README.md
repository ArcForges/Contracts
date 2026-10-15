# ArcForges.Cli

Offline validation of the declared ArcForges package inventory.

Apache-2.0. This WP03.00 candidate contains the selected complete record slices; full service and semantic coverage remains in later WP03 substeps. Public accessibility does not authorize importing internal protocols.

## Command

This .NET tool declares the command `arcforges-contracts`:

```sh
dotnet tool install --tool-path <folder> ArcForges.Cli --version <exact version>
arcforges-contracts validate-inventory <inventory.json>
```

## Release note: command renamed to `arcforges-contracts` (AF-CON-02)

Versions published from ArcForges/Contracts after AF-CON-02 declare the tool command
`arcforges-contracts`. Earlier published versions declared `arcforges`, which is the
command of the ArcForges product CLI; the rename removes that PATH collision (ArcForges-Design
conflict C-03).

Earlier published versions are immutable: they keep the `arcforges` command and stay
resolvable, and none is unpublished, deprecated or deleted. Scripts that pin an earlier
version keep working; scripts that move to a newer version call `arcforges-contracts`
instead of `arcforges`. The `validate-inventory` arguments, results and exit codes are
unchanged; only the usage message names the new command.
