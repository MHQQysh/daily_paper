# Read-Only Public Site Design

## Goal

Publish the current Daily Paper library as a public GitHub Pages site while keeping all search, translation, category editing, manual addition, and deletion operations on localhost only.

## Separation

- Localhost keeps the existing interactive application and Python API unchanged.
- The public GitHub Pages build uses the same visual paper browser and committed JSON snapshot.
- Public visitors cannot start searches or mutate papers or directions.
- No DeepSeek key, GitHub token, or writable backend is exposed by the public site.

## Public Interface

The public site retains:

- Direction navigation and expandable paper lists
- Text search and relevance filtering
- Paper details, Chinese TLDR and abstracts
- Source and PDF links

The public site hides:

- Date range and paper-count run controls
- API key controls and run status
- Add-paper action
- Direction editing
- Paper deletion

## Data Flow

Local operations continue to update `data/papers.json`, `docs/papers.json`, and `docs/run_status.json`. Publishing consists of committing the desired JSON snapshot and pushing `main`; a deploy-only GitHub Actions workflow serves `docs/` without running search or DeepSeek.

## Validation

Automated tests protect localhost behavior. Browser checks cover public-mode visibility, local-mode visibility, paper rendering, desktop/mobile overflow, and console errors.
