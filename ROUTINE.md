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

```
You maintain the "Lakewood Rental List" website. This repo is your working directory.

1. Install deps:  pip install -r requirements.txt
2. Rebuild:       python3 build.py
   build.py downloads the current Masa U'Matan rental PDF, parses it, and
   regenerates listings.json and site/index.html. If it exits non-zero (fewer
   than 60 listings parsed, or the download failed), STOP — do not publish or
   commit anything, and report the failure.
3. If step 2 succeeded, republish the page with the Artifact tool:
     file_path: site/index.html
     url:       https://claude.ai/code/artifact/b8837b56-6782-4202-b3d7-c8db84ff1014
   Keep the title "Lakewood Rental List" and favicon 🏘️ unchanged.
4. Commit the regenerated files:
     git add -A && git commit -m "Weekly refresh" && git push
   If push fails on auth, skip it — the Artifact update is the important part.
5. Report the list date, the listing count, and the Artifact URL.
```

## Re-create the routine (if deleted)

With the `schedule` skill / `RemoteTrigger` tool:

```json
{
  "action": "create",
  "body": {
    "name": "Lakewood Rental List — weekly refresh",
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
