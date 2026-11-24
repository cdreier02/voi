# pilot-01 run notes

- Run on 2026-11-24.
- Each reply came from a separate Claude Code subagent that was given only `AGENT_INSTRUCTION` (see `pilot/convention.py`) and one prompt file. A fresh subagent was used for every delegate in every round; continuity came from the "Your own record" section of the prompt.
- Subagents carry a coding-assistant system prompt, so these are not clean model calls.
- Rounds 2 and 3 were run only for `known`. `lottery` and `withheld` were unanimous in round 1, so their remaining rounds were skipped.
- 60 replies in total. None were invalid and none were re-run.
