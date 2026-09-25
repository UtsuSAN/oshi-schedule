# Local Codex instructions

- Work only under `sites/oshi-schedule/` for the Sites viewer. Do not change the FastAPI application unless the user explicitly requests it.
- Keep this a read-only static view of Public Snapshot data.
- Preserve the version 1.0 snapshot contract and Asia/Tokyo time handling.
- Keep data refresh manual. Do not add automatic X monitoring, polling, schedulers, or notifications.
- Do not add `source_text`, Candidate/raw post data, local databases, credentials, private plans, or unapproved event data.
- Keep the viewer usable on mobile and desktop; check JavaScript syntax and JSON parsing after edits.
- This folder is a GitHub source mirror. A GitHub commit does not modify or publish the ChatGPT Site. After pushing changes, provide the branch and commit to the Site-connected ChatGPT Codex for synchronization.
- Keep Site changes unpublished unless the user explicitly requests deployment.
