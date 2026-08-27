# Live Agent Replay Evaluation

The original `core_tasks.json` is a useful 25-case task definition, but the
legacy default runner is explicitly a `synthetic_profile_check`: it evaluates
declared capability dependencies, not model behavior. Its 100% baseline must
not be used as a product metric.

`backend.evals.live_agent_replay` replays the same tasks through the product
SSE chat pipeline. It records actual `tool_call`, `tool_result`, and `final`
events produced by the configured model and tools.

```bash
.venv/bin/python -m backend.evals.live_agent_replay \
  --model YOUR_MODEL \
  --output backend/evals/reports/live_agent_replay.json
```

The runner creates an isolated `eval-*` user and `live-eval-*` sessions. Its
report is gitignored and includes per-task event-derived tool coverage, output
completion, latency, and error categories.

## What The Metrics Mean

- `task_contract_pass_rate`: the run emitted non-empty final output, did not
  return an `agent_error`, and observed every tool required by the case.
- `required_tool_coverage_rate`: required-tool observations divided by all
  declared required tools.
- `tool_result_observation_rate`: tool results observed divided by tool calls.
- `response_completion_rate`: non-error runs with non-empty final output.

These are real runtime reliability metrics, but they are not semantic answer
accuracy. Do not write “task success rate” in a resume until a separate answer
grader or human review is added. A resume-safe claim after an actual run is:

> Replayed 25 agent workflows through the production chat and tool pipeline;
> measured tool-contract pass rate, required-tool coverage, result observation,
> latency, and categorized runtime failures from structured traces.
