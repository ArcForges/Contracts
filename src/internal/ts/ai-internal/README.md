# @arcforges/ai-internal

Internal Cloud and AI HTTP schema records and validators.

Apache-2.0. This package contains the WP03.00 selected record slices. Complete service and semantic acceptance remains in later WP03 steps.

This is the one internal thin-adapter package that Contracts still publishes to npm (CON.40): the npm generation, build, pack and publication pipeline is restricted to this package. It is published to the public npm registry (`publishConfig` access `public`), while its contract access is `internal`. Registry visibility does not change the import boundary: public clients must not import it. It carries schema records and validators for the Cloudflare adapters only; business logic and authoritative state stay in C#.
