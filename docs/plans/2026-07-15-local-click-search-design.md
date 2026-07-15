# Local Click-to-Search Design

## Goal

Allow the local Daily Paper website to start an arXiv search and DeepSeek translation from the browser without requiring a GitHub token or a terminal command.

## Architecture

Add a small Python HTTP server that serves the existing `docs/` site and exposes local-only API endpoints. The browser sends run parameters and the DeepSeek API key to this server. The server launches `scripts/fetch_papers.py` in a background process and keeps an in-memory job status.

The GitHub Pages deployment remains static and continues to use GitHub Actions. Localhost automatically switches the controls to local mode.

## User Flow

1. Start Daily Paper by double-clicking the local launcher.
2. Enter the DeepSeek API key once. The browser stores it in `localStorage`.
3. Choose a date, result limit, score threshold, and optional rebuild mode.
4. Click `Run search`.
5. The page polls local job status, displays progress, and reloads papers when the run finishes.

## Components

- `scripts/local_server.py`: serves static files and implements `POST /api/run` plus `GET /api/status`.
- Local launcher: starts the API server without a visible terminal window and opens the browser.
- `docs/app.js`: selects local or GitHub mode from the page origin, stores the appropriate token, starts jobs, and polls status.
- `docs/index.html`: uses mode-neutral token labels and status text that JavaScript updates.

## Safety And Errors

- Only one local search may run at a time.
- The DeepSeek key is passed to the child process through its environment and is never written to repository files or server logs.
- Invalid inputs return clear HTTP errors.
- Failed jobs expose the final error and recent output without exposing the API key.
- API endpoints bind to loopback only, so other devices cannot trigger local commands.

## Verification

- Validate Python and JavaScript syntax.
- Start the local server and verify static JSON loading.
- Trigger a small no-DeepSeek or mocked run through the API.
- Verify duplicate-run rejection, status polling, and final paper refresh.
