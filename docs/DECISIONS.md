# Design choices and their consequences

This is a reading guide to choices documented in the repository. It is not a set of approved Commonplace decision records.

## Bind each server to an explicit scope

One manifest selects a server's sources. Requests cannot switch its environment or repository set. Team and personal manifests use separate stores and MCP processes, keeping derived evidence within the selected scope.

This local separation does not provide multi-user authorization. A company integration still supplies identity, source authorization and storage controls. Revisit the service boundary before exposing a shared remote endpoint. See [Configuration and integration](CONFIGURATION.md).

## Keep retrieval separate from reviewed guidance

Code indexing provides current source evidence. Commonplace provides human-reviewed practices, conventions, decisions and procedures. Indexing a Markdown document does not approve it; stale, proposed and retired guidance is withheld from agent lookup.

This makes curation an explicit activity. Teams must propose and review useful lessons instead of expecting a code scan to create policy. See [Knowledge layers](KNOWLEDGE-LAYERS.md) and [Commonplace](COMMONPLACE.md).

## Give people a reading guide

The human architecture view starts with repository documentation. Extracted dependency relationships remain supporting evidence: they cannot explain undocumented design intent or prove runtime behavior.

Authors must supply the narrative and keep it current. Revisit guide coverage when a new component changes the end-to-end flow. See [How Context Engine fits together](ARCHITECTURE-OVERVIEW.md).

## Keep integrations outside the core

The core accepts explicit local sources and defined provider boundaries. Company systems supply credentials, repository provisioning, remote authorization and process supervision. The VS Code extension has no runtime npm dependencies.

The tradeoff is that deployment needs integration work; the local reference is not a managed company service. See [Development and verification](DEVELOPMENT.md) and [Configuration and integration](CONFIGURATION.md).
