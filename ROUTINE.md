# Weekly auto-refresh routine

The site is rebuilt weekly by a **Claude Code cloud agent** (a "routine"), not a
local cron job. It runs in Anthropic's cloud, checks out this repo, rebuilds from
the live PDF, and republishes the Artifact.

- **Schedule:** `0 5 * * 3` (cron, UTC) = **Wednesday 05:00 UTC**
  = 12:00 AM EST / 1:00 AM EDT. Chosen to land after Masa U'Matan's
  "late Tuesday night" PDF update in both halves of the year.
- **Model:** `claude-sonnet-5`
- **Environment:** `Default` (`env_01FcpMNRFRziToQU1Rdh3wMo`)
- **Tools:** `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Artifact`
- **Manage / disable:** <https://claude.ai/code/routines>

## Agent prompt

The authoritative copy is the routine's saved prompt (claude.ai/code/routines);
this is a summary of what it does, in order:

1. `python3 -m pip install -r requirements.txt`
2. **Tests first** (`python3 -m unittest discover -s tests`, plus
   `node --test tests/search.test.js` if Node exists). Any failure stops the run.
3. `python3 build.py` - downloads the PDF, parses it, runs the data-quality gate
   in `checks.py`.
   - `ABORT:` lines (hard failure): stop, write nothing, report them. The public
     site keeps last week's data.
   - `WARN:` lines (soft): continue, and include them in the report so the
     right rules get added to `parse.py`.
4. `git add -A && git commit && git push` - this updates the public site
   (GitHub Pages serves `docs/`).
5. Republish the private Artifact copy.
6. Report: list date, listing count, tests, every WARN, push result, site URL.

## Re-create the routine (if deleted)

With the `schedule` skill / `RemoteTrigger` tool:

```json
{
  "action": "create",
  "body": {
    "name": "Lakewood NJ Area Rentals — weekly refresh",
    "cron_expression": "0 5 * * 3",
    "enabled": true,
    "job_config": {
      "ccr": {
        "environment_id": "env_01FcpMNRFRziToQU1Rdh3wMo",
        "session_context": {
          "model": "claude-sonnet-5",
          "sources": [{"git_repository": {"url": "https://github.com/OWNER/lakewood-rentals"}}],
          "allowed_tools": ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Artifact"]
        },
        "events": [{"data": {
          "uuid": "GENERATE-A-FRESH-UUID",
          "session_id": "",
          "type": "user",
          "parent_tool_use_id": null,
          "message": {"role": "user", "content": "<the agent prompt above>"}
        }}]
      }
    }
  }
}
```
