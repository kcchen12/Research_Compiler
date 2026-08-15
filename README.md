# Research Paper Digest

A Streamlit app to monitor newly published academic papers and generate weekly/biweekly digest reports.

## Current scope

- Journal of Fluid Mechanics retrieval via OpenAlex + Crossref
- User-added journals via OpenAlex journal search
- SQLite tracking of already-digested papers
- Keyword relevance scoring
- Optional AI summaries (OpenAI or Gemini)
- Markdown + HTML digest export

## Project structure

- `/home/runner/work/Research_Compiler/Research_Compiler/app.py`
- `/home/runner/work/Research_Compiler/Research_Compiler/paper_fetcher.py`
- `/home/runner/work/Research_Compiler/Research_Compiler/database.py`
- `/home/runner/work/Research_Compiler/Research_Compiler/relevance.py`
- `/home/runner/work/Research_Compiler/Research_Compiler/summarizer.py`
- `/home/runner/work/Research_Compiler/Research_Compiler/digest.py`
- `/home/runner/work/Research_Compiler/Research_Compiler/config.py`
- `/home/runner/work/Research_Compiler/Research_Compiler/data/papers.db` (created at runtime)

## Install

```bash
pip install -r requirements.txt
```

## Environment variables

Copy `.env.example` to `.env` and set:

- `AI_PROVIDER` (`openai` or `gemini`)
- `AI_MODEL` (for example `gemini-3.5-flash-lite`)
- `OPENAI_API_KEY` (if using OpenAI)
- `GEMINI_API_KEY` (if using Gemini)

Gemini model choices and manually maintained free-tier quota limits are centralized
in `config.py`. The recommended default is `gemini-3.5-flash-lite`.

## Run

```bash
python app.py
```

The standard Streamlit command also works:

```bash
python -m streamlit run app.py
```

## Data flow

1. `app.py` collects journal/date/interests from UI.
2. Users can add journals from the sidebar by searching OpenAlex sources and saving a selected match.
3. `paper_fetcher.py` fetches papers from OpenAlex and Crossref, normalizes and deduplicates them.
4. `database.py` compares fetched papers against digest history (DOI-first, safe fallback for missing DOI).
5. `relevance.py` ranks papers from title+abstract against user interests.
6. `summarizer.py` generates/caches AI summaries per paper.
7. `digest.py` builds downloadable Markdown/HTML digest output.

## What currently works

- Real API retrieval for Journal of Fluid Mechanics in configurable date ranges
- Custom journal search/add/remove controls backed by SQLite
- New vs seen paper detection with SQLite persistence and reset/view controls
- Paper relevance scoring and ranked display
- Digest creation from unseen papers only
- AI summary fallback when abstract is insufficient or provider setup fails

On Streamlit Cloud, SQLite-backed custom journals persist with the app's local
storage while the deployment is alive, but may reset if the app is rebuilt or
its ephemeral filesystem is cleared.
