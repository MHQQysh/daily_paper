# Daily Paper

Daily Paper is a lightweight academic paper tracker. It retrieves papers for every UTC day in an inclusive date range from the broad arXiv categories `cs.AI`, `cs.CV`, `cs.LG`, and `cs.CL`. A local title-and-abstract pass directly selects the top N papers for every configured direction across the whole range. DeepSeek is used only to write the Chinese TLDR and translate the abstract for those final selections.

## What It Tracks

Default directions and keywords live in `config/topics.json`. The current defaults are:

- Vision Token Pruning
- GRPO
- 可解释性
- 流形

The site does not download PDFs. It stores only paper metadata, abstracts, and links.

## Public Website

The GitHub Pages site is a read-only public showcase of the latest committed `docs/papers.json` snapshot. Visitors can browse directions, search the library, filter by relevance, read Chinese summaries and abstracts, and open source or PDF links.

Search runs, API keys, direction editing, manual paper addition, and deletion are available only on localhost. The public site contains no writable backend and no GitHub or DeepSeek token input.

## Publish Local Results

Run and review paper operations locally. When the snapshot is ready to publish, commit `data/papers.json`, `docs/papers.json`, and `docs/run_status.json`, then push `main`. The deploy-only Pages workflow publishes `docs/` without running a paper search.

Default directions and keyword lists are edited locally and persisted to `config/topics.json`.

## Local Run

Double-click `start_daily_paper.cmd`. It starts the loopback-only local server and opens:

`http://127.0.0.1:8766/`

Install the local PDF reader dependency once when setting up the project:

```powershell
python -m pip install -r requirements.txt
```

On localhost, the run panel asks for a DeepSeek API key. The key is stored in this browser's local storage. Choose an inclusive date range of up to 31 days and a paper count per direction, then click `Run local search`; the page starts the fetch, shows progress, and reloads the updated paper list automatically.

Use `Edit directions` to add, rename, or remove research directions and edit their keyword lists. Chinese direction names receive stable unique IDs, so categories such as `可解释性` and `流形` remain separate. Save creates a backup and persists the catalog to `config/topics.json`.

Automatic browser searches are append-only: newly found papers are merged into the library and older papers are not removed by a search. The same paper may be selected for multiple directions but is stored only once with all matching directions. The completed run report shows the retrieved count, per-direction selected counts, unique selected count, and counts for added, updated, and duplicate papers.

To add one paper manually, paste an arXiv URL, arXiv ID, or title into the sidebar search field and click `+`. Title searches return up to five candidates. After choosing one, review DeepSeek's suggested directions, edit the checkboxes if needed, and confirm the addition.

The same field accepts a public direct PDF URL from sites such as OpenReview or CVF Open Access. The local server temporarily downloads up to 30 MB, extracts at most 120,000 characters, and asks DeepSeek to recover the title, authors, abstract, Chinese translation, and recommended directions. PDF bytes and extracted full text are discarded; the saved record keeps the original PDF link. A DeepSeek key is required, and scanned PDFs without selectable text are not currently supported. OpenReview links protected by a login or browser challenge cannot be fetched anonymously and return a clear access error.

To remove an unwanted paper, select it and click the trash icon in the detail view. Local deletion asks for confirmation, creates a timestamped backup, and removes only the current record. It does not create an ignore rule, so a future search may add the paper again.

Only one local search can run at a time. Closing the browser does not cancel a running search because the local Python server owns the process.

For command-line use, the original fetcher remains available:

```powershell
python scripts/fetch_papers.py --start-date 2026-07-01 --end-date 2026-07-14 --papers-per-topic 5
```

## DeepSeek

Set `DEEPSEEK_API_KEY` to enable Chinese TLDRs and abstract translations for the papers selected by the local filter. DeepSeek does not classify, score, or rank papers.

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python scripts/fetch_papers.py --start-date 2026-07-01 --end-date 2026-07-14 --papers-per-topic 5
```

## Deployment

The included GitHub Actions workflow deploys the committed `docs/` snapshot whenever `main` receives a relevant push. It does not search papers or call DeepSeek. Configure GitHub Pages to use GitHub Actions as its source.

- Source: `GitHub Actions`

The public URL will be:

`https://<your-github-username>.github.io/daily_paper/`
