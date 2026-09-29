# CodeRepair Lab

CodeRepair Lab is an experimental Python project comparing **single-shot LLM code repair** with **iterative agentic repair**. The research question is: does iteration materially improve repair success, and when is that improvement worth the additional model calls, tokens, cost, latency, and complexity? Intended comparisons include solve rate, first-pass success, token usage, estimated/API cost, latency, model calls, iterations, and failure modes. The project is under development; both strategy primitives exist, but no comparative experiment has been run.

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
- OpenRouter Responses adapters for repair proposals and typed agent actions, tested offline. OpenRouter is the only supported model gateway for benchmark execution. The project uses the `openai` Python SDK as an OpenAI-compatible client configured for OpenRouter; benchmark requests are not sent directly to OpenAI. A bounded cumulative plain-Python agent loop uses the existing MCP tools, explicit model/tool/transcript limits, and one independent final evaluation. No live agent-action run has been made.

The benchmark routing policy fixes one logical model and its reasoning/generation settings. Cross-model fallback is disabled; same-model provider failover is allowed with `require_parameters` enabled. Results retain the returned model, selected routed provider when metadata is available, and gateway-reported cost when available. The OpenRouter single-shot baseline has been live-validated on `dev-001`; the typed agent-step adapter is offline-tested, and the full iterative agent path has not yet been live-validated.

Both strategy paths now expose comparable raw telemetry: evaluator success, model/tool calls, available token counts, aggregate model-request latency, end-to-end strategy duration, and provider-reported USD cost when supplied. Cost estimation, aggregate solve rates, comparative first-pass metrics, iteration counts, and automated failure analysis are not implemented.

## Development benchmark and live validation

`benchmarks/dev/dev-001` is a small synthetic task whose name normalizer misses surrounding non-space whitespace. It is the known development fixture for infrastructure validation, not a meaningful benchmark suite or holdout set.

One OpenRouter single-shot baseline smoke run on `dev-001` used `openai/gpt-6-luna` with `medium` reasoning. The response reported the same returned model, routed provider OpenAI, 356 input / 92 output / 448 total tokens, $0.0000816 cost, and about 3.25 seconds of request latency. It proposed one `text_utils.py` change; mutation was accepted, and independent reproduction, full-suite, and lint checks all exited 0. This is **one infrastructure-validation run**, not evidence about model quality, solve rate, strategy superiority, expected latency, or average cost. Same-model provider failover was allowed by policy but was not demonstrated by this call.

A historical direct-Gemini manual smoke run also validated the provider-neutral baseline path. Its script is retained only as historical infrastructure-validation context; direct Gemini is not a supported benchmark transport. The OpenRouter agent-action adapter remains offline-tested, and no live iterative-agent run has been claimed.

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

The scripts under `scripts/` are **manual** and may consume provider quota or balance. They are not run by pytest. `live_openrouter_dev001.py` is the completed baseline smoke path; `live_openrouter_agent_dev001.py` is the unrun iterative-agent smoke path. `live_gemini_smoke.py` is historical only. Supply credentials through environment variables; never commit API keys.

## Local verification

As of 2026-09-29, the full pytest suite passed 432 tests with no skips using a repository-local `--basetemp`. `ruff check .` and `git diff --check` passed locally. This is a point-in-time result, not a CI guarantee.

## Planned, not implemented

LangGraph, human approval (HITL), holdout benchmarks, experiment runner, aggregate cost analysis, automated failure taxonomy, environment provenance, `GitSource` materialization, and tracing remain future work. There is no CI guarantee in this repository.
