# Security Policy

## Supported versions

Security reports are accepted for the current 0.1.x release line.

## Reporting a vulnerability

Please report suspected vulnerabilities through GitHub's private vulnerability reporting or Security Advisory feature when it is enabled for this repository. If that option is unavailable, contact the maintainers privately through their GitHub profile.

Do not publish exploit details, personal information, credentials, cookies, tokens, or private event data in a public issue or pull request. Include a concise impact description and safe reproduction steps in the private report.

## Important deployment limitation

The 0.1.x application has no authentication on its administration routes. Those routes can read and change Artists, Events, Sources, and ImportCandidates. The FastAPI backend must not be exposed to the public internet in its current form. Run it bound to 127.0.0.1 for personal local use. Authentication, authorization, CSRF protections, and production deployment controls are not implemented.

The local SQLite database is not encrypted. Source and Candidate records may contain pasted post text or personal schedule details. Protect the computer, backups, and any files containing real user data.
