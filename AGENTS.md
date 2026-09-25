# Project rules

- Implement one increment at a time and keep the app runnable at each increment.
- Keep this project suitable for eventual public GitHub publication: never commit credentials, personal data, local databases, or generated local files.
- Keep automatic X monitoring, schedulers, notifications, paid APIs, and mandatory X API access out of scope unless a later requirement explicitly changes this.
- Do not write collected or parsed information directly into `Event`. Store it as an `ImportCandidate` and require review before applying it.
- Keep business and data access logic separate from presentation so a future JSON API or Sites UI can reuse it.
- Prioritize a usable mobile experience when UI work begins.
- Stay within the currently requested increment; do not prebuild later screens or flows.
- Keep seed content fictional and relative to the current date.
