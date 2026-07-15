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
