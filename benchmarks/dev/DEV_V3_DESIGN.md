# DEV-v3 preregistration: information and feedback

This design is fixed **before** any `dev-011`–`dev-016` fixture or DEV-v3 model
request exists. DEV-v3 is a controlled synthetic mechanism study, not a holdout
benchmark or an attempt to make bugs progressively harder until a particular
single-shot model fails.

> Agentic repair may justify its additional cost on tasks where information
> materially relevant to a correct repair is absent from the shared initial
> context but can become available through repository inspection or execution
> feedback after the first inference.

The intended experimental variable is **availability and timing of information**,
not a subjective difficulty label. The baseline may still solve every task from
visible context; that remains a valid outcome.

## Frozen future task roles

| Task | Class | Role fixed before implementation |
| --- | --- | --- |
| `dev-011` | Relevant implementation omitted | Context-acquisition positive task |
| `dev-012` | Relevant implementation omitted class | Context-acquisition negative control: plausible withheld/distractor files exist, but the correct repair must not require them |
| `dev-013` | Runtime diagnostic disambiguation | Diagnostic-positive task |
| `dev-014` | Runtime diagnostic disambiguation | Runtime-diagnostic negative control: the available diagnostic must not be needed for the correct repair |
| `dev-015` | Progressive failure / second invariant | Progressive feedback task |
| `dev-016` | Progressive failure / second invariant | Progressive feedback task |

The negative controls remain legitimate repair tasks, not trivial padding. There
is no blanket hide-all-tests rule. Each future manifest freezes exact
`context_withheld_paths` before its first model request. Paths remain visible in
inventory, and informative filenames may leak clues; this is a documented
limitation, not a reason to obfuscate filenames unnaturally.

`context_withheld_paths` is an optional sorted set of exact portable relative
file paths. Old manifests default to empty and render identically. Withheld
files remain listed in inventory and readable through the normal `read_file`
tool, but their contents are absent from the shared initial context. The
rendering lists them only under the same neutral `OMITTED FILE CONTENTS` heading
as other omissions; it does not identify intentional withholding to the model.
Internal `withheld_paths` metadata distinguishes explicit withholding from byte,
encoding, or unsafe-entry omission for audit. Configured exact paths must exist
as ordinary repository files or context construction fails before inference.
The shared context
digest is SHA-256 over the exact UTF-8 `render_initial_context` result, before
arm-specific evidence is appended.

## Four preregistered arms

| Arm | Information and action sequence |
| --- | --- |
| S0 `initial_single_shot` | Shared initial context → one inference → one repair batch → independent evaluation; no tool observations |
| S1 `evidence_enriched_single_shot` | Same context plus one preregistered mechanically generated evidence packet → one inference → one batch → independent evaluation |
| S2 `scripted_feedback_two_shot` | Same context → inference/patch #1 → exactly one fixed probe → inference/cumulative patch #2 → independent evaluation; at most two inferences |
| A `agentic` | Existing bounded agent with `read_file`, `apply_file_changes`, `run_reproduction`, `run_full_tests`, and `run_lint` only |

S1 evidence is the exact bounded/sanitized `read_file` result for the critical
dependency in context-omitted tasks, or the exact bounded/sanitized original
`run_reproduction` result for runtime-diagnostic tasks. It is generated from
the unmodified snapshot and contains no gold patch, trusted partial patch,
human-written repair hint, or canonical replacement. S1 is **not directly
applicable** to patch-dependent progressive F2 evidence; no oracle packet from
a trusted partial repair will be fabricated for it.

S2's probe is fixed by class, never chosen after seeing model behavior:

| Class | One fixed S2 probe |
| --- | --- |
| Context omitted | `read_file` on the preregistered critical dependency |
| Runtime diagnostic | `run_reproduction` |
| Progressive failure | `run_full_tests` |

S0 vs S1 primarily measures the value of additional information supplied up
front. S0/S1 vs S2 can reveal value from evidence arriving after a repair
attempt. S2 vs A can reveal value associated with adaptive tool choice and
further interaction. Six synthetic tasks cannot provide perfect causal
identification or establish agent superiority.

DEV-v3 agent limits are fixed prospectively at **8 model calls, 7 tool calls,
and 200,000 transcript bytes**. This calibrates room for read → patch →
diagnostic → patch → re-test → finish based on earlier observed interaction
shape, before any DEV-v3 model run. Historical 6/5/100,000 limits and records
are unchanged. A one-repetition run is only an instrumentation smoke test.
The first actual comparison requires **at least five repetitions per applicable
task × arm**, unless this preregistration is revised before any DEV-v3 model run.
Tasks must not be retained or tuned based on whether S0 fails.

## Future fixture acceptance requirements

- `dev-011`: critical helper visible by path but not content initially;
  retrievable with `read_file`; non-writable; untouched by canonical repair;
  canonical evaluation succeeds. At least one plausible withheld distractor is
  required. No oversized-file padding trick.
- `dev-012`: plausible withheld implementation context, but canonical repair
  derivable without reading it; measures unnecessary acquisition overhead.
- `dev-013`: discriminating runtime fact absent initially and present in the
  original reproduction observation; at least two static hypotheses remain
  compatible with initially visible source. No artificial answer-revealing
  diagnostic line.
- `dev-014`: diagnostic available, but diagnostic-specific information not
  required to infer the repair; measures unnecessary execution overhead.
- `dev-015` and `dev-016`: original F1 and failed evaluator; trusted first-stage
  partial removes F1 but exposes F2 and still fails; canonical removes both
  and succeeds. F2's discriminating fact is absent from both initial context
  and original F1 observation. If a hidden test/fixture causes this, document
  it explicitly: progressive F2 then also contains an information-availability
  component and is not causally pure.

## Measurements and interpretation

Primary per-attempt outcome: independent final evaluator success, reported by
task and arm. Secondary fields: model/tool calls, input/output/total tokens,
cached input and reasoning output tokens when reported, provider-reported cost,
model-request and end-to-end duration, termination reason, routed provider,
first-patch shadow success, and iterative occurrence category. No composite
score or code-level winner is defined. Task is an analysis unit; do not pool
all attempts into one undifferentiated solve rate or claim statistical
significance from this pilot.

Execution feedback is a normal MCP result even when `exit_code != 0` and
`is_error=False`; `is_error` denotes a tool/boundary error, not test failure.
Future records keep execution exit/timeout and SHA-256 of exact model-visible
bounded/sanitized observation text, without full stdout/stderr. Proposed patch
identity uses sorted path plus SHA-256 of UTF-8 content. Full generated source is
not stored. The initial-context and per-request prompt digests are SHA-256 of
their exact UTF-8 renderings. Records include resolved `openai`, `mcp`, and
`pydantic` versions. Provider usage maps `input_tokens_details.cached_tokens`
and `output_tokens_details.reasoning_tokens` when supplied; missing remains
null, not zero.

Shadow evaluation is measurement-only **after** an agent run: replay successful
cumulative mutation prefixes in a fresh workspace, independently evaluate each,
hash each resulting workspace with the evaluator's safe non-following tree
inventory, record policy/command outcomes, then destroy the shadow copy. The
live agent loop performs no full-workspace measurement hashing. Shadow results
do not enter the model transcript or measured live strategy duration.

An agent that succeeds after exactly one successful patch is a
**tool-assisted one-patch repair**, even if it later reads or tests. A
**context-refinement iteration** requires a successful first patch, a new
successful `read_file` observation, a materially different second successful
patch, and final evaluator success, without a failing execution diagnostic
between those patches. A **feedback-responsive iterative-repair occurrence**
requires a successful first patch, then `run_reproduction`, `run_full_tests`,
or `run_lint` with nonzero exit or timeout, then a materially different
successful second patch, and final independent success. These are trace
occurrences only. **Iterative value** requires cross-arm comparison: an agent
occurrence does not establish necessity if S0, S1, or S2 also succeeds.

Do not normalize away real agent token usage; cost is part of the strategy.
Later analysis should distinguish static instruction/context resend,
accumulated transcript, tool observations, cached input tokens, and
output/reasoning tokens where possible. Historical token ratios are not purely
intrinsic to iterative reasoning; earlier prompt layout and context resend
contributed. Stable prompt prefixing is a prospective layout change, not a
claim that caching actually occurs.

For DEV-v3 execution, resolve the configured Docker tag once **before provider
calls**, record the configured reference and immutable image ID separately,
and pass the immutable image ID to every container. Never rebuild it implicitly.
A future sample-and-verify S3 arm is explicitly deferred.

## Freeze rule

Before the first DEV-v3 model request, commit this design, context-withholding
and renderer semantics, task IDs/classes and negative controls, four arm and
fixed-probe definitions, new limits, event/metric definitions, repetition
policy, raw-record and prompt-hash semantics, dependency provenance, immutable
Docker-ID rule, and shadow-evaluation semantics. Implement fixtures only in the
next task against that committed preregistration.

After a model is evaluated on a DEV-v3 task, do not change its bug, issue text,
tests, withheld paths, initial-context policy, evidence source, fixed S2 probe,
arm semantics, or limits. Document any genuine defect, retire/exclude the
affected task from the corresponding comparison, and create a new version if
needed. Never strengthen after a solve or weaken after a failure.
