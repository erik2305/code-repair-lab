# Frozen experimental evidence

These artifacts support CodeRepair Lab's reported synthetic research results. Canonical selection was verified from record content, experiment purpose, task coverage, and provenance, not numeric filename suffixes. Raw files are byte-identical copies of the validated sources; no JSONL formatting or field normalization was performed. Scoped `.gitattributes` rules disable Git newline conversion for canonical raw and derived artifacts so Windows checkout preserves their bytes.

## Canonical artifacts

| File | Validated source | Experiment ID | Role and coverage |
| --- | --- | --- | --- |
| [raw/dev-v1.jsonl](raw/dev-v1.jsonl) | `dev-results-001.jsonl` | `20260930T050406700936Z` | DEV-v1 paired baseline/Agent: four tasks, eight attempts. |
| [raw/dev-v2.jsonl](raw/dev-v2.jsonl) | `dev-results-002.jsonl` | `20260930T115546274984Z` | DEV-v2 paired baseline/Agent: six tasks, twelve attempts. |
| [raw/dev-v3.jsonl](raw/dev-v3.jsonl) | `dev-v3-results-002.jsonl` | `20261002T114122881026Z` | Validated DEV-v3 comparison: six tasks, 110 attempts across applicable S0/S1/S2/Agent arms. |

SHA-256 of the exact raw bytes:

```text
dev-v1.jsonl  e7f172552bc9abace0be35286be6255a404ff658172d9de89a6632ddca439fbc
dev-v2.jsonl  452e236b1724a53f5759ef00180df3ce7a8c6b4980f340f45f8e4b63ad88a04e
dev-v3.jsonl  d4eab9f09dd3630e2047897ba8715b20e1489dd6bee45a6c65110353fe3f19bc
```

Historical DEV-v1/v2 results remain separate from DEV-v3 and have no retroactively invented shadow metrics. JSONL retains filenames, hashes, usage, execution outcomes, and environment/model provenance, not full prompt, generated source, or observation payloads.

## DEV-v3 analysis

The [report](analysis/dev-v3/report.md) and [summary](analysis/dev-v3/summary.json) were regenerated from the canonical raw copy and verified byte-identical to the validated Task 35 outputs from `dev-v3-analysis-002/`.

Verified anchors: 110 attempts, 301 model calls, 211 tool calls, 480,707 total tokens, and $0.069782145 provider-reported cost. Primary outcomes include lint: dev-013 S2 has 5/5 functional passes but only 1/5 evaluator successes because of four lint failures.

## Offline reproduction

After installing the project with `python -m pip install -e ".[dev]"`, run:

```sh
python scripts/analyze_experiments.py \
  --dev-v3 results/raw/dev-v3.jsonl \
  --output-dir analysis-output
```

Windows/PowerShell equivalent:

```powershell
python scripts/analyze_experiments.py --dev-v3 results/raw/dev-v3.jsonl --output-dir analysis-output
```

The output directory must be new. The analyzer validates inputs and emits deterministic `summary.json`, `report.md`, and `attempts.csv`; the CSV is mechanically reproducible and not published. Optional explicit `--dev-v1` and `--dev-v2` inputs produce separately reported historical sections. No provider request or Docker execution is needed.

## Exclusions

Smoke runs, aborted infrastructure runs, and development diagnostics are not included in the canonical results. The earlier `dev-v3-results-001.jsonl` comparison was invalid due to Docker infrastructure exit 125 and a subsequent HTTP 429; it is not analyzed as repair failure evidence. `dev-v3-smoke-001.jsonl` is a smoke run, not comparison evidence.

Local archival copies, analysis scratch outputs, `attempts.csv`, and pytest caches remain outside this public result directory under ignored storage. Raw evidence is frozen; derived reports must be regenerated, not hand-edited.
