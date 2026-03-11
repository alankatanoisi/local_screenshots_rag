# Decisions

This file records important project decisions and the reasoning behind them.

Keep entries short and practical.

## 2026-03-10 / 2026-03-11

### Git + GitHub

- The project uses a local git repository plus a public GitHub remote.
- Reason:
  - local work needs version history and safe checkpoints
  - GitHub provides backup, sharing, and a public project surface

### Public README Safety

- The public `README.md` should remain safe to publish.
- Reason:
  - maintaining separate public and local READMEs creates unnecessary drift
  - sensitive or machine-specific notes should live elsewhere

### README Version Archive

- The repo keeps one main `README.md` plus archived README editions in `readme-history/`.
- Filename pattern:
  - `README-vX-YYYY-MM-DD.md`
- Reason:
  - preserve the evolution of the public project story
  - keep an unconventional but intentional documentation history
  - still preserve a conventional root landing page

### Naming

- The current project name is provisional.
- The current repo/folder name is allowed to remain a placeholder until a stronger name clearly wins.
- Reason:
  - forcing a premature rename creates churn
  - the project can evolve while the naming stays unsettled

### Public-By-Default Working Assumption

- Unless explicitly stated otherwise, treat repo-tracked documentation as public-facing.
- Reason:
  - the GitHub repository is public
  - this reduces the chance of accidentally publishing sensitive notes
