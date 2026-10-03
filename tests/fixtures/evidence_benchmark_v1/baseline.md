# Evidence benchmark v1 — baseline

Offline, selected report-reviewed targets; not a security accuracy score.

Real findings: 35; quarantined: 1.
Selected target recall: 93/105 (88.6%).
Forbidden matches: 20/36.

| Candidate kind | Matched | Targets |
|---|---:|---:|
| github_file | 19 | 20 |
| inline_snippet | 55 | 57 |
| github_diff | 19 | 19 |
| inline_diff | 0 | 7 |
| gist | 0 | 2 |

## Transport probes (recorded HTTP)

- `code-423n4/2023-04-caviar`: error — GitHubFetcher._headers() takes 1 positional argument but 2 were given
- `code-423n4/2023-01-astaria`: error — GitHubFetcher._headers() takes 1 positional argument but 2 were given

## Scope

Unlabelled candidates are unscored; do not interpret selected-target recall as global precision/recall. Roles are annotated for future checks, not predicted by the current scanner. Real duplicate pairs and entirely no-code findings remain corpus gaps; synthetic controls are reported separately.

See baseline.json for missing target indexes, forbidden matches, per-source counts, observations and implementation hashes.
