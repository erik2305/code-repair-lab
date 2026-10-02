# DEV-v3 operational safeguards

`dev-v3-results-001.jsonl` is an immutable aborted infrastructure artifact, not
benchmark evidence. Its 25 completed rows report Docker exit 125 for all checks;
the later HTTP 429 also aborted the run. Do not resume, rewrite, merge or analyze
these rows as repair failures. Start the clean comparison from the beginning in
a new exclusive output file.

The runner now pins the Docker image and executes a harmless Python sentinel in
a fresh disposable workspace using the same temporary-directory mechanism,
read-only bind mount and restricted Docker runner as real attempts. This must
pass before provider construction. Exit 125 raises an operational exception with
bounded, redacted operator diagnostics; it is not model feedback or normal JSONL.
Other ordinary command failures and timeout semantics remain unchanged.

For the currently observed account limit of 20 requests/minute, use conservative
inter-attempt pacing:

```sh
python scripts/run_dev_v3_experiment.py --purpose comparison \
  --model openai/gpt-6-luna --reasoning-effort medium --repetitions 5 \
  --inter-attempt-delay-seconds 20 --output dev-v3-results-002.jsonl
```

This account-specific guidance is not a universal rate limit or guarantee. Pacing
defaults to zero, occurs only between completed attempts after record flushing,
and is recorded as operational provenance. It is outside live strategy timings
and leaves deterministic order, prompts, model settings and arm semantics intact.
HTTP 429 and other provider failures still abort without retry or fallback;
earlier completed records remain flushed. No resume behavior is implemented.
