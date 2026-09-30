# CodeRepair Lab

CodeRepair Lab is an experimental Python project comparing **single-shot LLM code repair** with **iterative agentic repair**. The research question is: does iteration materially improve repair success, and when is that improvement worth the additional model calls, tokens, cost, latency, and complexity? Intended comparisons include solve rate, first-pass success, token usage, estimated/API cost, latency, model calls, iterations, and failure modes. The project is under development; both strategy primitives exist, and paired development experiments are underway.

## Current architecture

```text
TaskSpec / YAML
      ↓
Disposable snapshot workspace
      ↓
Shared InitialRepairContext
      ↓
Repair strategy: single-shot baseline or bounded agent loop
      ↓
Controlled mutation / workspace-scoped MCP tools
      ↓
Independent evaluator → read-only Docker checks
```

Implemented today:

- Strict YAML loading into `TaskSpec`, with `SnapshotSource` and `GitSource` schemas. Snapshot tasks can be copied into disposable workspaces; Git materialization is not implemented.
- Logical writable/protected path policy and controlled `FileChange` mutation. The filesystem boundary rejects symlinks, junctions, hard links, and case aliases that could bypass policy.
- Docker execution with network disabled, capabilities dropped, resource limits, and read-only workspace mounts for trusted checks. The independent evaluator checks protected files and the complete final-tree delta against `writable_paths` before running reproduction, full tests, and optional lint.
- A workspace-scoped MCP server exposing exactly `read_file`, `apply_file_changes`, `run_reproduction`, `run_full_tests`, and `run_lint`. It exposes no arbitrary model-facing shell command.
- Deterministic `InitialRepairContext`; provider-neutral generation usage, latency, and model identity; `RunConfig` and agent-only `AgentLimits` contracts; and a single-shot baseline that makes one generator call before independent evaluation.
- OpenRouter Responses adapters for repair proposals and typed agent actions. OpenRouter is the only supported model gateway for benchmark execution. The project uses the `openai` Python SDK as an OpenAI-compatible client configured for OpenRouter; benchmark requests are not sent directly to OpenAI. A bounded cumulative plain-Python agent loop uses the existing MCP tools, explicit model/tool/transcript limits, and one independent final evaluation. Both strategy paths have been live-validated once on `dev-001`.

The benchmark routing policy fixes one logical model and its reasoning/generation settings. Cross-model fallback is disabled; same-model provider failover is allowed with `require_parameters` enabled. Results retain the returned model, selected routed provider when metadata is available, and gateway-reported cost when available.

Both strategy paths now expose comparable raw telemetry: evaluator success, model/tool calls, available token counts, aggregate model-request latency, end-to-end strategy duration, and provider-reported USD cost when supplied. Cost estimation, aggregate solve rates, comparative first-pass metrics, iteration counts, and automated failure analysis are not implemented.

## Development benchmark and live validation

The development set contains four small fixtures:

| Task | Bug class | Main purpose |
| --- | --- | --- |
| `dev-001` | Whitespace normalization | Local text repair |
| `dev-002` | Collection boundary | Incomplete final chunk |
| `dev-003` | Cross-module contract | Canonical identifier lookup |
| `dev-004` | Shared mutable state | Cross-call options contamination |

These are development/evaluation fixtures for debugging the experiment, **not** a holdout benchmark or evidence of comparative performance.

The preregistered DEV-v2 group adds six synthetic development fixtures:

| Task | Fixed bug class |
| --- | --- |
| `dev-005` | Cache invalidation / stale state |
| `dev-006` | Exception-boundary specificity |
| `dev-007` | Serialization compatibility |
| `dev-008` | Transactional multi-state invariant |
| `dev-009` | Recursive base-context propagation |
| `dev-010` | Parsing/escaping pipeline |

[DEV_V2_DESIGN.md](benchmarks/dev/DEV_V2_DESIGN.md) records the fixed classes and acceptance criteria before any model execution on these fixtures. For each, trusted validation establishes a partial repair that passes reproduction but fails an independent full-suite regression, as well as a complete repair that passes independent evaluation. These are still development fixtures, not holdout tasks or model-performance results. The live experiment runner remains scoped to `dev-001` through `dev-004` pending fixture review.

One OpenRouter single-shot baseline smoke run on `dev-001` used `openai/gpt-6-luna` with `medium` reasoning. The response reported the same returned model, routed provider OpenAI, 356 input / 92 output / 448 total tokens, $0.0000816 cost, and about 3.25 seconds of request latency. It proposed one `text_utils.py` change; mutation was accepted, and independent reproduction, full-suite, and lint checks all exited 0. This is **one infrastructure-validation run**, not evidence about model quality, solve rate, strategy superiority, expected latency, or average cost. Same-model provider failover was allowed by policy but was not demonstrated by this call.

One OpenRouter iterative-agent smoke run on `dev-001` also passed independent evaluation. It made three model calls and two MCP tool calls, proposing `apply_file_changes` for `text_utils.py`, then `run_reproduction`, then `finish`. It reported 3,058 input / 311 output / 3,369 total tokens, $0.00049165 cost, about 16.85 seconds of aggregate model latency, and about 24.69 seconds end-to-end. Final reproduction, full-suite, and lint checks exited 0. This is likewise **one infrastructure-validation run**, not comparative performance evidence.

A historical direct-Gemini manual smoke run also validated the provider-neutral baseline path. Its script is retained only as historical infrastructure-validation context; direct Gemini is not a supported benchmark transport.

## Safety boundary

Benchmark sources remain separate from disposable workspaces. Model-originated file changes pass through controlled host-side mutation, and trusted benchmark commands run with a read-only workspace in Docker. The evaluator independently rejects protected-file tampering and unauthorized final repository changes before executing candidate code. Docker here is a restricted development execution environment, **not** a formally hardened hostile multi-tenant sandbox or VM.

## Development setup

Python 3.12 or newer is required. Create and activate a virtual environment, then install the package and development tools:

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Build the development sandbox image before Docker-backed checks:

```bash
docker build -f Dockerfile.sandbox -t coderepair-lab-sandbox:dev .
```

The image contains Python 3.13, pytest, and Ruff and is intended for the synthetic development task. Run local checks with:

```bash
python -m pytest
ruff check .
git diff --check
```

The scripts under `scripts/` are **manual** and may consume provider quota or balance. They are not run by pytest. `live_openrouter_dev001.py` and `live_openrouter_agent_dev001.py` are the single-task smoke paths; `live_gemini_smoke.py` is historical only. Supply credentials through environment variables; never commit API keys.

## Paired DEV experiment runner

After building the sandbox image, commit or stash all tracked and untracked changes, set `OPENROUTER_API_KEY`, and invoke the manual runner with an explicit model and a new output filename:

```bash
python scripts/run_dev_experiment.py --model openai/gpt-6-luna --reasoning-effort medium --repetitions 1 --output dev-results.jsonl
```

The runner pairs baseline and agent attempts on `dev-001` through `dev-004`. Each attempt gets a fresh disposable workspace and the same model, reasoning level, initial-context budgets, evaluator, and Docker image. Strategy order alternates deterministically by task and repetition. It refuses a dirty Git worktree or an existing output file, records the Git commit and immutable Docker image ID, and flushes one raw JSONL record per completed attempt. Repetitions are independent; an operational failure leaves completed records in place without a retry. **Running the script consumes provider balance.** These four tasks remain development fixtures, not a holdout evaluation; no comparative result is claimed here.

## Local verification

Docker-backed tests run when the daemon and sandbox image are available; otherwise they skip. Local results are point-in-time checks, not a CI guarantee.

## Planned, not implemented

LangGraph, human approval (HITL), holdout benchmarks, aggregate cost analysis, automated failure taxonomy, full environment provenance, `GitSource` materialization, and tracing remain future work. There is no CI guarantee in this repository.
