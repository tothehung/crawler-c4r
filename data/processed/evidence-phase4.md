# Evidence benchmark v1 — baseline

Offline, selected report-reviewed targets; not a security accuracy score.

Real findings: 35; quarantined: 1.
Selected target recall: 105/105 (100.0%).
Forbidden matches: 0/36.

| Candidate kind | Matched | Targets |
|---|---:|---:|
| github_file | 20 | 20 |
| inline_snippet | 57 | 57 |
| github_diff | 19 | 19 |
| inline_diff | 7 | 7 |
| gist | 2 | 2 |

## Transport probes (recorded HTTP)

- `code-423n4/2023-04-caviar`: resolved — 5c87f7d69c6fac29eb253b5c7b2fb4a9f23f8750
- `code-423n4/2023-01-astaria`: resolved — 1bfc58b42109b839528ab1c21dc9803d663df898

## Scope

Unlabelled candidates are unscored; do not interpret selected-target recall as global precision/recall. Roles are annotated for future checks, not predicted by the current scanner. Real duplicate pairs and entirely no-code findings remain corpus gaps; synthetic controls are reported separately.

See baseline.json for missing target indexes, forbidden matches, per-source counts, observations and implementation hashes.
