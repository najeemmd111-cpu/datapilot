# DataPilot

Predicts when Vélib' stations in Paris will run out of bikes, and answers questions about the network in plain English. The front end, Paris Pulse, replays a day across the city as a living map.

## Run it

You need Python 3.10 or newer. You don't need Node, accounts or API keys.

```bash
python run.py
```

The first run takes a few minutes. It creates `.venv`, installs packages, generates sample data, trains the model and opens <http://localhost:8000>.

The first run uses **generated sample data**, not real Vélib' readings, and the app shows a banner saying so. To download real history and retrain:

```bash
python run.py --real
```

## What it does

- **The city:** about 1,500 stations drawn from their coordinates alone. Press play to watch a day. Red dots have no bikes, and the line along the bottom shows the share of empty stations.
- **Station details:** click a dot or search for a name to see its day and the chance of having no bikes in 30 minutes.
- **Ask the city:** answers appear as street plaques. Flip one to see the SQL, or show its stations on the map.

## Architecture

| Layer | Tools |
| --- | --- |
| Data | pandas, BigQuery (DuckDB locally), Terraform |
| Model | scikit-learn, MLflow |
| API | FastAPI on Cloud Run: `/api/stations`, `/api/replay`, `/api/predict`, `/api/ask`, `/api/health` |
| Agent | LangGraph, sqlglot read-only guard, Langfuse |
| Front end | Angular 22, canvas, Chart.js |
| CI | GitHub Actions |

Folders: `data` ingest and sample data, `ml` notebook and training, `api` FastAPI and agent, `web` Angular source, `infra` Terraform and deployment. `api/static` holds the built web app.

## Turn on a real LLM

Without an LLM, Ask the city uses a few fixed queries, so it only understands a handful of question types. To use a real model, copy `.env.example` to `.env`, then set `LLM_MODEL` and your provider's key:

```text
LLM_MODEL=anthropic:your-model-name
ANTHROPIC_API_KEY=your-key
```

Then run `python run.py`. Set the `LANGFUSE_*` values too if you want traces.

## Train and inspect runs

```bash
.venv/bin/pip install -r ml/requirements.txt    # Windows: .venv\Scripts\pip
.venv/bin/python ml/train.py
.venv/bin/mlflow ui --backend-store-uri sqlite:///ml/mlflow.db
```

## Deploy to Google Cloud

1. Start the Google Cloud free trial and add a budget alert. Cloud Run needs billing.
2. Run `gcloud auth login`, `gcloud auth application-default login` and `gcloud config set project YOUR_PROJECT_ID`.
3. Enable the APIs:

   ```bash
   gcloud services enable bigquery.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
   ```

4. In `infra`, run `terraform init`, then `terraform apply -var project_id=YOUR_PROJECT_ID`.
5. Install the cloud packages with `.venv/bin/pip install -r api/requirements-cloud.txt`.
6. Load data with `.venv/bin/python data/ingest.py --bigquery`.
7. Train on it with `DATA_BACKEND=bigquery .venv/bin/python ml/train.py`.
8. Create the Secret Manager secrets `llm-api-key`, `langfuse-public` and `langfuse-secret`. Give `datapilot-api` the Secret Accessor role on each one.
9. Deploy with `LLM_MODEL=provider:model LLM_KEY_NAME=YOUR_PROVIDERS_KEY_NAME ./infra/deploy.sh`.
10. Set a monthly spending limit with your LLM provider.

## Design choices

- **Target:** a yes/no question, "no bikes in 30 minutes?", is what a rider actually needs.
- **Baseline:** "an empty station stays empty" is hard to beat, so the model has to prove it adds something.
- **Metrics:** accuracy misleads because most stations aren't empty. Recall counts the shortages we catch, precision limits false alarms, and PR-AUC compares models across thresholds.
- **Time split:** the test set is the last two days, with a gap, so the model can't learn from the future.
- **Exact time matching:** labels and lag features match exact timestamps, because missing snapshots would otherwise shift them.
- **Two locks on SQL:** the guard allows one SELECT on two tables, and the service account can't write even if the guard fails.
- **One SQL layer:** the same queries run on DuckDB and BigQuery, so local tests cover the API's own queries.
- **One Cloud Run service:** it serves both Angular and the API, so there's no CORS setup.
- **Spending limits:** `/api/ask` is limited per address and per day, Cloud Run stops at one instance, and BigQuery rejects queries over 100 MB.

## Results

Tested on the last two days of real data. Only 5.2% of the 286,957 readings were followed by an empty station 30 minutes later.

| Model | Precision | Recall | PR-AUC |
| --- | --- | --- | --- |
| Baseline: an empty station stays empty | 0.609 | 0.610 | 0.392 |
| HistGradientBoosting, threshold 0.5 | 0.686 | 0.483 | 0.640 |

- Accuracy would mislead: always predicting "not empty" scores about 94.8%.
- Recall matters because a rider who walks to an empty station loses time.
- Precision matters because too many false alarms make riders ignore the warning.
- PR-AUC compares how well each method ranks risk, without fixing one threshold.
- At 0.5, the model cut false alarms by 44% but caught 21% fewer empty stations than the baseline, so the threshold needs tuning.

To compare LLMs on the 15 test questions, run this from `api`:

```bash
LLM_MODELS=provider:model-a,provider:model-b ../.venv/bin/python eval_llm.py
```

## Limits

- The public history only starts on 2026-10-27, so it can't show other seasons.
- Replay data is historical, not live.
- Deployment is manual and CI only tests the code.

## What broke and how I fixed it

- **Gaps in snapshots:** a simple `diff()` gave wrong lags, so lags now match exact timestamps.
- **Wrong answer in the demo agent:** "At what hour do stations run out?" matched "run out" first and listed stations, so the hour pattern now runs first.
- **Time zones in generated SQL:** portable SQL was awkward, so tables now store Paris date and hour columns.
- **Add your own:** interviewers will ask about what broke for you.

## Data credit

Real data: *Vélib' Métropole station status, every minute (unofficial)*, Angelo Saadeh, <https://huggingface.co/datasets/angelosaadeh/velib>, from Vélib' Métropole (GBFS) and the Base Adresse Nationale, Licence Ouverte 2.0.
