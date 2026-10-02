# DEV-v3 operational safeguards

`dev-v3-results-001.jsonl` is an immutable aborted infrastructure artifact, not
benchmark evidence. Its 25 completed rows report Docker exit 125 for all checks;
the later HTTP 429 also aborted the run. Do not resume, rewrite, merge or analyze
these rows as repair failures. Start the clean comparison from the beginning in
a new exclusive output file.

The aborted comparison's Docker exit 125 was reproduced as a Windows bind-mount
access failure (`CreateFile <workspace>: Access is denied`) for a workspace
created through the default system temporary-directory path. Independent
diagnostics also found protected owner-specific ACLs with disabled inheritance
under changing Windows execution identities (`ysati` and `CodexSandboxOffline`).
This establishes an access problem, not that `%TEMP%` alone explains its cause.

DEV-v3 uses a project-local temporary workspace root, `.coderepair-tmp/`, for
context validation, mounted preflight, every live attempt, and S2/Agent shadows.
A shared helper creates unique UUID children using ordinary `mkdir()` so they
inherit normal project permissions rather than tempfile's private `0o700` ACLs.
It removes each child on exit (including failures); the Git-ignored parent may
persist. No ACL changes or Administrator privileges are part of the runner.
Historical shadow callers without this explicit scratch root retain their prior
temporary-directory behavior. Scratch paths are not persisted in JSONL.

The runner pins the Docker image and executes a harmless Python sentinel in
a fresh disposable workspace using that same scratch mechanism,
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
