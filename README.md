# CodeRepair Lab

CodeRepair Lab is a controlled research framework comparing single-shot LLM code repair with feedback-driven, agentic repair on reproducible Python tasks. It measures repair success alongside tokens, provider-reported cost, model calls, and latency. This is a completed synthetic mechanism-study pet project, not a production autonomous coding agent or a real-world bug benchmark.

## Research question

Does an iterative agentic repair loop materially outperform a single-shot LLM repair baseline, and if so, under what information conditions and at what additional cost?

## Key findings

In these synthetic controlled tasks:

- When the first patch was sufficient, Agent interaction added overhead without improving success.
- Withholding essential information made the initial single-shot fail; providing or acquiring that evidence improved success.
- On dev-015/016, post-first-patch full-test feedback supplied F2 information withheld initially. S2 and Agent then succeeded 5/5; this mixes feedback timing with information availability, as anticipated in the preregistration, rather than isolating feedback alone.
- On those progressive tasks, Agent did not improve final success over S2 with preregistered designer-selected task-specific probes. This does not establish that autonomous evidence selection is unnecessary generally.
- Agent interaction used substantially more tokens, model calls, and provider-reported cost. These observations do not establish universal agent superiority or inferiority.

## Experimental design

Strategies start with the same deterministic `InitialRepairContext`, including the task description, policy, file inventory, and bounded whole UTF-8 files. Frozen ablations deliberately vary subsequent information access:

| Arm | Information and repair protocol |
| --- | --- |
| S0 | Initial single-shot: one generation, no additional inspection or feedback. |
| S1 | Evidence-enriched single-shot: one generation after a fixed evidence acquisition. Applicable to dev-011–014 only. |
| S2 | Fixed scripted two-shot feedback: first repair, preregistered designer-selected task-specific probe, second repair; no adaptive tool selection. |
| Agent | Bounded adaptive loop with workspace-scoped MCP tools. |

DEV-v3 uses six tasks and five repetitions per applicable task/arm: 110 attempts. Common controls include logical model `openai/gpt-6-luna`, reasoning effort `medium`, 4,096 output tokens per call, 60-second request timeout, 30-second evaluator-command timeout, and 100,000/200,000-byte initial-context limits. Agent limits are eight model calls, seven tool calls, and 200,000 transcript bytes. Inter-attempt pacing is 20 seconds, outside measured strategy duration.

The frozen [design](benchmarks/dev/DEV_V3_DESIGN.md), [execution protocol](benchmarks/dev/DEV_V3_EXECUTION.md), and [operational safeguards](benchmarks/dev/DEV_V3_OPERATIONS.md) define the comparison. Shadow evaluations replay accepted mutation prefixes in fresh workspaces after the measured run, without feeding their outcomes back to the strategy.

## DEV-v3 results

Primary success comes from the independent evaluator: authorized final repository delta, unchanged protected state, and passing reproduction, full tests, and configured lint without timeout.

| Task | S0 | S1 | S2 | Agent |
| --- | --- | --- | --- | --- |
| dev-011 | 0/5 | 5/5 | 5/5 | 5/5 |
| dev-012 | 5/5 | 5/5 | 5/5 | 5/5 |
| dev-013 | 0/5 | 5/5 | 1/5 | 5/5 |
| dev-014 | 5/5 | 5/5 | 5/5 | 5/5 |
| dev-015 | 0/5 | — | 5/5 | 5/5 |
| dev-016 | 0/5 | — | 5/5 | 5/5 |

S2 passed dev-013's functional reproduction/full tests **5/5**, but four runs failed lint and remain primary evaluator failures. Agent occurrences were 20 tool-assisted one-patch repairs and 10 feedback-responsive iterations; there were no context-refinement iterations or unclassified occurrences.

dev-013's frozen role is runtime-diagnostic positive, but all five Agent runs first read the withheld fixture; four patched before any execution feedback, and all first patches passed shadow evaluation. Agent success is not clean evidence of requiring runtime diagnostics. The exact causes of the four S2 lint failures are not recoverable from source-free canonical records. Occurrence classification uses distinct recorded patch-batch hashes, not semantic materiality; aggregate overhead is agentic interaction overhead, not pure iteration cost.

## Cost / overhead

| Arm | Mean tokens | Mean cost | Mean duration | Mean model calls |
| --- | ---: | ---: | ---: | ---: |
| S0 | 989.03 | $0.00023118 | 6.83 s | 1.00 |
| S1 | 1465.25 | $0.00028859 | 7.35 s | 1.00 |
| S2 | 2552.30 | $0.00052768 | 12.08 s | 2.00 |
| Agent | 11505.40 | $0.00137482 | 19.38 s | 6.37 |

Aggregate means span different applicability sets; use the [deterministic full report](results/analysis/dev-v3/report.md) for per-task matched comparisons rather than pooling solve rates. Strategy duration excludes inter-attempt pacing and later shadow replay. The complete DEV-v3 comparison recorded 301 model calls, 211 tool calls, 480,707 tokens, and $0.069782145 provider-reported cost; this is not a total infrastructure-cost estimate.

## Architecture and isolation

Strict YAML task manifests define immutable snapshots, trusted argv checks, and writable/protected policies. Disposable copies feed the shared initial context, single-shot baseline, or bounded plain-Python agent loop. MCP exposes exactly `read_file`, `apply_file_changes`, `run_reproduction`, `run_full_tests`, and `run_lint`; the model cannot supply arbitrary shell commands, Docker options, images, or timeouts. LangGraph is not used.

Controlled host-side mutation validates the entire change batch before writing, applies protected-path precedence, and rejects filesystem aliases including symlinks, junctions, hard links, and case mismatches. The independent evaluator compares the complete final tree with the snapshot and rejects unauthorized or unsafe changes before executing any candidate code.

Evaluator and MCP feedback commands mount `/workspace` read-only; `/tmp` remains writable. Docker disables runtime networking, drops all capabilities, enables no-new-privileges, and limits CPU (1), RAM (512 MiB), and PIDs (128), with a read-only container root. Only the workspace is bind-mounted, not the Docker socket, project root, or home directory. This is a restricted development sandbox, not a formally hardened hostile multi-tenant boundary.

OpenRouter transport uses strict structured proposals, explicit reasoning effort, and disabled SDK retries. Cross-model fallback is disabled; same-model provider failover is allowed with required parameter support. Source-free raw JSONL records telemetry and provenance; offline deterministic analysis is separate from strategy execution and final/shadow evaluation.

## DEV-v1 → DEV-v3 progression

- **DEV-v1:** infrastructure and four basic paired tasks; baseline and Agent both solved 4/4.
- **DEV-v2:** six richer tasks; both solved 6/6, with Agent still making one accepted patch per task. Interaction overhead alone did not demonstrate iterative value.
- **DEV-v3:** frozen S0/S1/S2/Agent ablations, withheld information, runtime diagnostics, progressive F1 → F2 bugs, and shadow prefix evaluation distinguish tool-assisted one-patch repair from feedback-responsive iteration.

Historical DEV-v1/v2 records do not contain the later shadow measurements. Versions are not pooled into one solve-rate claim.

## Reproducibility

[Canonical evidence](results/README.md) includes frozen raw JSONLs, SHA-256 hashes, the DEV-v3 report, and machine-readable summary. The same DEV-v3 input regenerates byte-identical report/summary. Raw records do not persist full prompts, generated source contents, or tool-observation contents. They record Git commit provenance, immutable Docker image ID, dependency/environment metadata, and requested/returned model information.

Use Python 3.12+ (the recorded DEV-v3 environment used Python 3.13) and install development tooling:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

On POSIX systems activate with `source .venv/bin/activate`. Docker-backed checks require a running Docker daemon/Desktop and the development image:

```text
docker build -f Dockerfile.sandbox -t coderepair-lab-sandbox:dev .
```

The image contains Python 3.13, pytest, and Ruff for synthetic dev tasks, not arbitrary external repository dependencies. Rebuilding its mutable tag need not reproduce the original image ID; the recorded ID identifies what actually ran.

## Running tests and analysis

Automated tests use fake providers and make no external LLM requests. Docker integration tests skip when the daemon or image is unavailable. On Windows use a fresh repository-local basetemp per verification run:

```text
python -m pytest --basetemp=.pytest-tmp-release
ruff check .
git diff --check
```

Offline analysis needs no API credentials or Docker:

```text
python scripts/analyze_experiments.py --dev-v3 results/raw/dev-v3.jsonl --output-dir analysis-output
```

The output directory must not already exist. Add `--dev-v1 results/raw/dev-v1.jsonl --dev-v2 results/raw/dev-v2.jsonl` for a combined, separately reported historical analysis. Outputs include `report.md`, `summary.json`, and reproducible `attempts.csv`; only report/summary are published here. Live smoke/experiment scripts are manual, credential-requiring tools, not part of offline reproduction.

## Repository structure

```text
benchmarks/dev/      frozen designs, protocols, and synthetic tasks
src/coderepair/      repair, execution, evaluation, and analysis code
scripts/            manual experiment and offline analysis entry points
tests/              automated verification
results/raw/        canonical frozen research evidence
results/analysis/   deterministic derived reports
```

## Limitations

This is a synthetic pilot: six DEV-v3 tasks, five repetitions per applicable task/arm, and one logical model. There is no external real-world bug benchmark or claim of statistical significance. Informative filenames can leak clues. Same-model provider infrastructure is not physically controlled, and provider-reported costs/latency are environment-dependent. The findings do not prove universal agent superiority or inferiority.

## Status

CodeRepair Lab is complete for its intended pet-project scope. The repository preserves frozen experimental evidence and deterministic analysis needed to reproduce the reported findings; further benchmark expansion and agent-framework work are out of scope.
