# Daily Paper

Daily Paper is a lightweight academic paper tracker. It retrieves all papers submitted on one UTC date from the broad arXiv categories `cs.AI`, `cs.CV`, `cs.LG`, and `cs.CL`. DeepSeek then ranks every candidate independently for every configured direction, selects the top N papers per direction, and translates the selected abstracts into Chinese.

## What It Tracks

Default directions and keywords live in `config/topics.json`. The current defaults are:

- Vision Token Pruning
- GRPO
- 可解释性
- 流形

The site does not download PDFs. It stores only paper metadata, abstracts, and links.

## Customize Directions

On the website, click `Edit directions`. Each line uses:

```text
Direction Name | keyword one, keyword two, keyword three
```

Saving there changes the grouping in your browser immediately and stores it in local storage.

To change the default directions used by the daily GitHub Actions fetcher, edit `config/topics.json` in the repository.

## Run From The Website

The website can trigger the GitHub Actions workflow directly. This avoids any extra backend service.

1. Create a GitHub fine-grained token that can access this repository and trigger Actions.
2. Open the site.
3. Paste the token into `GitHub token for triggering Actions`.
4. Click `Save token`. It is saved only in your browser local storage.
5. Choose one date and the number of papers wanted for each direction.
6. Click `Run search`.

The workflow will search papers, use the repository secret `DEEPSEEK_API_KEY` for DeepSeek translation, update `docs/papers.json`, update `docs/run_status.json`, and redeploy the site.

The run panel reports how many papers were found, kept, added, updated, and stored in total.

## Local Run

Double-click `start_daily_paper.cmd`. It starts the loopback-only local server and opens:

`http://127.0.0.1:8766/`

Install the local PDF reader dependency once when setting up the project:

```powershell
python -m pip install -r requirements.txt
```

On localhost, the run panel asks for a DeepSeek API key instead of a GitHub token. The key is stored in this browser's local storage. Choose one date and a paper count per direction, then click `Run local search`; the page starts the fetch, shows progress, and reloads the updated paper list automatically.

Use `Edit directions` to add, rename, or remove research directions and edit their keyword lists. Chinese direction names receive stable unique IDs, so categories such as `可解释性` and `流形` remain separate. In local mode, Save creates a backup and persists the catalog to `config/topics.json`; on the hosted static page, custom directions remain in that browser and are included when it triggers a workflow.

Automatic browser searches are append-only: newly found papers are merged into the library and older papers are not removed by a search. The same paper may be selected for multiple directions but is stored only once with all matching directions. The completed run report shows the retrieved count, per-direction selected counts, unique selected count, and counts for added, updated, and duplicate papers.

To add one paper manually, paste an arXiv URL, arXiv ID, or title into the sidebar search field and click `+`. Title searches return up to five candidates. After choosing one, review DeepSeek's suggested directions, edit the checkboxes if needed, and confirm the addition.

The same field accepts a public direct PDF URL from sites such as OpenReview or CVF Open Access. The local server temporarily downloads up to 30 MB, extracts at most 120,000 characters, and asks DeepSeek to recover the title, authors, abstract, Chinese translation, and recommended directions. PDF bytes and extracted full text are discarded; the saved record keeps the original PDF link. A DeepSeek key is required, and scanned PDFs without selectable text are not currently supported. OpenReview links protected by a login or browser challenge cannot be fetched anonymously and return a clear access error.

To remove an unwanted paper, select it and click the trash icon in the detail view. Local deletion asks for confirmation, creates a timestamped backup, and removes only the current record. It does not create an ignore rule, so a future search may add the paper again.

Only one local search can run at a time. Closing the browser does not cancel a running search because the local Python server owns the process.

For command-line use, the original fetcher remains available:

```powershell
python scripts/fetch_papers.py --date 2026-07-14 --papers-per-topic 5
```

## DeepSeek

Set `DEEPSEEK_API_KEY` to enable DeepSeek scoring and Chinese summaries.

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python scripts/fetch_papers.py --date 2026-07-14 --papers-per-topic 5
```

In GitHub, add the same key under:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Secret name:

`DEEPSEEK_API_KEY`

## Deployment

The included GitHub Actions workflow runs every day for the previous UTC date and updates `data/papers.json` plus `docs/papers.json`. Enable GitHub Pages with:

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

The public URL will be:

`https://<your-github-username>.github.io/daily_paper/`
