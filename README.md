# Daily Paper

Daily Paper is a lightweight, pure-online tracker for token-pruning research. It searches new papers, classifies them into research directions, asks DeepSeek for a concise Chinese relevance note when an API key is available, and publishes a static GitHub Pages site.

## What It Tracks

Default directions and keywords live in `config/topics.json`. The current defaults are:

- Visual Token Pruning
- VLM / MLLM Acceleration
- LLM Context / KV Pruning
- Token Merging / Compression
- Efficient ViT
- Dynamic Token Selection
- Survey / Benchmark

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
5. Choose the range, such as `30 days`.
6. Click `Run search`.

The workflow will search papers, use the repository secret `DEEPSEEK_API_KEY` for DeepSeek translation, update `docs/papers.json`, update `docs/run_status.json`, and redeploy the site.

The run panel reports how many papers were found, kept, added, updated, and stored in total.

## Local Run

```powershell
python scripts/fetch_papers.py --days 14 --max-results 80
python -m http.server 8000 --directory docs
```

Then open `http://127.0.0.1:8000`.

## DeepSeek

Set `DEEPSEEK_API_KEY` to enable DeepSeek scoring and Chinese summaries.

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python scripts/fetch_papers.py --days 14 --max-results 80
```

In GitHub, add the same key under:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Secret name:

`DEEPSEEK_API_KEY`

## Deployment

The included GitHub Actions workflow runs every day and updates `data/papers.json` plus `docs/papers.json`. Enable GitHub Pages with:

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

The public URL will be:

`https://<your-github-username>.github.io/daily_paper/`
