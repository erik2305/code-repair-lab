# DEV-v2 preregistration

This controlled synthetic development group consists exactly of `dev-005` through
`dev-010`. Its bug classes and acceptance criteria were fixed before any model was
run on these fixtures. They are inspired by recurring maintenance patterns, not
copied benchmark instances. Real-world evaluation (for example, BugsInPy or
SWE-bench Verified) is a separate future activity.

| Task | Fixed bug class | Observable contract |
| --- | --- | --- |
| `dev-005` | Cache invalidation / stale derived state | Mutation refreshes an affected cached view; unchanged repeated reads reuse it. |
| `dev-006` | Exception-boundary specificity | Malformed external data becomes a public input error; unexpected internal failures propagate. |
| `dev-007` | Backward-compatible serialization | Current writes round-trip, and documented legacy data remains readable. |
| `dev-008` | Transactional multi-state invariant | A rejected operation changes neither primary nor secondary externally visible state. |
| `dev-009` | Recursive base-context propagation | Each relative reference uses the manifest that declares it, including nested references. |
| `dev-010` | Multi-stage parsing / escaping | Ordinary, escaped, and quoted separators parse under one small deterministic grammar. |

Each fixture has at least two semantically relevant application modules, one
focused reproduction test, and a separate contract regression. Its original
snapshot must fail reproduction and the full suite while passing lint. A trusted
plausible partial repair must pass reproduction but fail a distinct full-suite
regression while passing lint. A trusted canonical repair must pass reproduction,
full suite, lint, and independent evaluation, including writable-path and
protected-path integrity checks. Reference repairs live only in project tests,
outside the benchmark snapshots. Tests are protected; writable application paths
are narrow. The fixtures use only the standard library, no network or services,
and fit the normal 100,000-byte per-file and 200,000-byte total initial-context
budgets without omissions.

These states demonstrate an incomplete repair path where execution feedback could
be informative; they do not predict any model's actions or difficulty. Because
all relevant files are initially visible, these tasks do not measure discovery
of omitted context through `read_file`. That is a separate future task class.

Once any model has been evaluated on a DEV-v2 fixture, its behavioral contract,
tests, bug implementation, and issue text are frozen. A genuine defect should be
documented and the affected fixture excluded or retired from the relevant
comparison; a new task/version should be created if necessary. Do not silently
strengthen or weaken a task after observing a model outcome.
