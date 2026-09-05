# Baseline schema

Use this only when the vault has no local schema. A local schema always wins.

Required fields: unique stable `id`, `type`, `status`, ISO `created`, ISO `updated`, and a list of `topics`.

Recommended types: `inbox`, `source`, `knowledge`, `map`, `system`.

Recommended status flow: `inbox -> triaged -> draft -> review -> verified -> archived`.

Source notes should record source kind, URL or stable locator, authors, publication date, capture date, and an explicit trust assessment. Knowledge notes should list source-note wikilinks, evidence types, confidence, and reviewer.

Knowledge content must distinguish facts, external viewpoints, AI inferences, personal judgments, and empirical results. Important conclusions must link to a source or experiment record. AI must not fabricate personal judgment.

Stable IDs must survive title changes. Filenames should be readable; IDs exist for identity and automation.
