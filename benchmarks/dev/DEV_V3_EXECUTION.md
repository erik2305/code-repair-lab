# DEV-v3 frozen execution protocol

This supplement implements, without changing, `DEV_V3_DESIGN.md`. Freeze and
commit this protocol and its runner before any DEV-v3 model request. Smoke runs
validate instrumentation only; they support no inferential claim.

| Task | Role | Applicable arms | S1 pristine evidence | S2 post-patch-#1 probe |
| --- | --- | --- | --- | --- |
| `dev-011` | context-acquisition positive | S0, S1, S2, A | `read_file("poll_hint.py")` | `read_file("poll_hint.py")` |
| `dev-012` | context-acquisition negative | S0, S1, S2, A | `read_file("cursor_codec.py")` | `read_file("cursor_codec.py")` |
| `dev-013` | runtime-diagnostic positive | S0, S1, S2, A | `run_reproduction` | `run_reproduction` |
| `dev-014` | runtime-diagnostic negative | S0, S1, S2, A | `run_reproduction` | `run_reproduction` |
| `dev-015` | progressive F1→F2 | S0, S2, A | not applicable | `run_full_tests` |
| `dev-016` | progressive F1→F2 | S0, S2, A | not applicable | `run_full_tests` |

The typed `TASK_PROTOCOLS` mapping in `coderepair.dev_v3_experiment` is executable
policy. In particular, `cursor_codec.py` is fixed irrelevant evidence, never
selected in response to model outcomes.

Arm names are S0 `initial_single_shot`, S1 `evidence_enriched_single_shot`,
S2 `scripted_feedback_two_shot`, and A `agentic`. Every attempt has a fresh
workspace. All arms share RunConfig, commit, snapshot, routing policy, and the
SHA-256 of the original shared context. Evidence is not included in that digest.
A uses exactly 8 model calls / 7 tool calls / 200,000 transcript bytes.

S0 reuses the existing baseline. S1 obtains exactly one pristine MCP observation
before one inference. S2's first prompt is byte-for-byte S0's prompt, with no
second-chance notice. After an accepted first batch, it acquires exactly one
fixed MCP observation, then makes one final inference containing original
context, its already-applied first batch, and the exact observation. The second
batch is cumulative and may be empty. Rejected first mutations stop before probe
and second inference; rejected second mutations stop before final evaluation.
There are no retries. Tool-boundary/provider failures abort operationally; normal
nonzero commands and timeouts are evidence. Accepted final mutations use the
independent evaluator, never supplied to a model.

Shadow replay of accepted A/S2 mutation prefixes happens after the live strategy,
in a fresh copy, outside prompts and strategy duration. S0/S1 need no shadow.
S1/S2 duration includes fixed acquisition; that acquisition time is also reported
separately. Tool counters are total/adaptive/fixed: S0 0/0/0, S1 1/0/1,
S2 1/0/1 (0/0/0 when first mutation is rejected), A n/n/0.

Schema-v3 (`experiment_protocol="dev-v3"`) JSONL retains provenance, original
context and exact prompt hashes, proposal path/content hashes, complete-data
usage/cost/latency aggregates, evidence/probe metadata and observation hashes,
stage mutation outcomes, final policy/command outcomes, and shadow prefix states.
Only A receives iterative-occurrence classification. S2 reports first/second
patch application, fixed probe execution, and first-patch shadow success.
Prompts, source contents and observations are not persisted.

Canonical task order is dev-011 through dev-016; canonical arm order is S0,S1,S2,A
(S0,S2,A for progressive tasks). Rotate left by `(task_index + repetition - 1)`
modulo the number of selected applicable arms. Repetitions and recorded execution
positions are one-based. Smoke subsets retain canonical ordering. An explicit
smoke arm selector must apply to every selected task. Comparison's complete arm
selector denotes all *applicable* arms, not a fabricated S1 for progressive tasks.

Preflight validates selectors/config, clean Git and commit, all manifests, fresh
contexts and fixed withheld reads, applicability, Docker image pinning, dependency
versions, and exclusive output creation before constructing a provider client.
The configured Docker reference is resolved once; its immutable ID is used for
all evidence, probes, agent tools, final evaluation and shadow replay. Every
completed record is written with `allow_nan=False` and flushed immediately;
later operational failures preserve prior records.

```sh
python scripts/run_dev_v3_experiment.py --purpose comparison \
  --model openai/gpt-6-luna --reasoning-effort medium --repetitions 5 \
  --output dev-v3-results-001.jsonl

python scripts/run_dev_v3_experiment.py --purpose smoke \
  --model openai/gpt-6-luna --reasoning-effort medium --repetitions 1 \
  --tasks dev-011 \
  --arms initial_single_shot,evidence_enriched_single_shot,scripted_feedback_two_shot,agentic \
  --output dev-v3-smoke-001.jsonl
```

Comparison requires all six tasks, all applicable arms, and at least five
repetitions; subsets are rejected. Defaults use all tasks/applicable arms.
Provider credentials use the existing OpenRouter client composition. No images
are built automatically, no model fallback or retry is added, and no live request
is part of automated verification. Historical runners, records and frozen
fixture/design artifacts remain unchanged.
