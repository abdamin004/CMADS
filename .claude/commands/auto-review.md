---
description: Run the auto-review loop (Claude Code <-> Codex CLI) on the thesis
---

Run the orchestrator with any user-supplied flags:

```bash
python scripts/auto_review.py $ARGUMENTS
```

When it finishes, report:
- Exit code meaning (0 APPROVE / 1 plan-cap / 2 fix-cap / 3 CLI failure)
- Path to the run directory under `.review-cycle/`
- Contents of `CHANGES.md` summary at the run root
- For non-zero exits: also print the last 40 lines of the latest verdict file so the user can decide whether to retry or adjust prompts
