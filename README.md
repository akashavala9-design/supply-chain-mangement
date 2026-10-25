# Supply Chain Intelligence Mini-Platform

A small supply-chain data platform with a curated shipment dataset, a FastAPI
serving layer, a saved delay-classification model, data-quality reporting,
and an assistant that can call data tools.

## Project status

This is a take-home project, not a claim of production deployment. The local
API and assistant tool smoke tests have passed in the development notebook.
The existing API test suite has 8 passing tests. Real provider-backed LLM
tool selection has not been verified because no provider API key is configured.

## Architecture

```text
Raw CSV datasets
      |
      v
Curation and data-quality checks
      |                    |
      v                    v
Curated shipment data   Quarantined conflicts / DQ report
      |
      +------------------------------+
      |                              |
      v                              v
FastAPI serving endpoints       Assistant tools
      |                              |
      v                              +--> Query shipments
Saved delay model                    +--> Route statistics
                                     +--> Delay prediction API
                                     +--> Quarterly route ranking
                                            |
                                            v
                                  Optional LLM provider
                                  (API key required)
```

## Repository layout

- `data/raw/`: source CSV datasets.
- `data/curated/`: curated shipment data used by the serving layer.
- `data/quarantine/`: records separated due to identified conflicts.
- `app/main.py`: FastAPI endpoints.
- `app/dq.py`: reusable data-quality checks and report generation.
- `app/assistant.py`: assistant tools, local test mode, optional OpenAI tool calling,
  and JSONL observability logs.
- `models/delay_model.joblib`: saved model artifact.
- `reports/`: data-quality and model evaluation reports.
- `tests/`: API regression tests.
- `.github/workflows/`: CI workflow configuration.

## Requirements

- Python 3.12 recommended for the Docker image.
- Python and pip for local development.
- Docker with the Compose plugin for containerized execution.
- An OpenAI API key is optional and is required only for real OpenAI calls.

## Run locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app/dq.py
python -m pytest -v tests
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/docs` to inspect the interactive API documentation.
Use `http://127.0.0.1:8000/health` for the health check.

Run the assistant in local, no-key mode:

```bash
python -m app.assistant
```

The local mode is a deterministic demonstration, not an LLM. It is useful for
checking tool behavior without credentials.

## Run with Docker Compose

```bash
docker compose up --build
```

Then check `http://127.0.0.1:8000/health`.

The container includes the project data and saved model. This is a single-service
deployment for demonstration, not a production orchestration design.

## API capabilities

The implemented API includes routes for:

- Health checks.
- Shipment lookup and filtered, paginated shipment listing.
- Route delay and on-time statistics.
- Delay-risk prediction.
- Data-quality report retrieval.

Inspect `app/main.py` and `/docs` for the authoritative request schemas and
response formats.

## Assistant tools

The assistant exposes these tools:

- `query_shipments(filters)`: read curated shipment records.
- `get_route_stats(origin, destination)`: aggregate route delay and on-time metrics.
- `predict_delay(shipment_id)`: call the prediction endpoint.
- `top_delayed_routes(start_date, end_date)`: rank routes by average observed delay
  in the requested arrival-date window.

The OpenAI mode uses function/tool calling and allows the model to choose tools.
It requires `OPENAI_API_KEY`. The implementation limits tool calls per request
and refuses questions outside the supply-chain domain.

Set credentials in your shell rather than committing them:

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-4o-mini"
```

Do not commit `.env` files or secrets. Provider usage and cost have not been
measured in this project because no live provider calls have been run. Cost per
query depends on current provider pricing, input/output token counts, and the
number of tool-calling rounds. Check the provider's current published pricing
before estimating a deployment budget.

## Data quality and quarantine

The standalone data-quality module checks input data and writes a machine-readable
report. Review `reports/data_quality_report.json` for the current run's findings.
Conflicting records are separated into quarantine for investigation instead of
being silently treated as trusted curated data.

A data-quality finding is not automatically proof that a row is invalid.
For example, an arrival timestamp earlier than the planned arrival requires
business-context investigation before deciding whether to reject the record.

## Model and evaluation

The API loads a saved model artifact to predict whether a shipment will exceed
the project's 24-hour delay threshold. Prediction is a risk estimate, not a
guarantee.

The current saved evaluation report has shown weak, near-random discrimination
(ROC-AUC approximately 0.497 in the recorded holdout evaluation). This is a
material limitation. Do not describe the model as production-ready. Further work
should examine label quality, feature usefulness, class balance, temporal
validation, and operational baselines.

Features should be available at prediction time. Actual arrival, actual delay,
and other post-outcome fields must not be used as model inputs because they
would leak the answer into the prediction.

## Tests

Run:

```bash
python -m pytest -v tests
```

The existing eight API tests cover health, shipment lookup, not-found behavior,
pagination, data-quality reporting, prediction, unknown prediction IDs, and
request validation. Assistant-specific tests, broader integration tests, and
container smoke tests should be added before claiming comprehensive coverage.

## Observability

Assistant events are written to `reports/assistant_logs.jsonl`. API requests
also emit structured request logs. Before production use, add request correlation
IDs, log rotation/retention, access controls, secret redaction, and a durable
central logging destination. Avoid logging sensitive shipment or customer data
unnecessarily.

## CI/CD plan

1. Install dependencies in a clean environment.
2. Run unit and API integration tests.
3. Run the data-quality checks and validate the report schema.
4. Build the Docker image.
5. Run a container health smoke test.
6. Publish an image only after checks pass.
7. Deploy to a test environment, verify health and key endpoints, then promote
   through an approved release process with rollback capability.

The workflow under `.github/workflows/` must be inspected to confirm which of
these steps it currently implements; this plan is not a claim that all steps
are already automated.

## Scaling and production gaps

For a larger workload, consider a database-backed serving layer, indexed route
and shipment lookups, cached aggregations, model loading once at application
startup, bounded external calls, retries only where safe, and a durable queue
for asynchronous work. Add authentication, rate limiting, metrics, alerting,
schema/version management, and deployment secrets management before exposing
the service publicly.

For the take-home, the focus is reproducibility, data correctness, explainable
trade-offs, and testable behavior—not claiming production readiness without
evidence.



## Getting Started

### Option A: Docker Compose

Prerequisites: Docker Engine/Desktop with the Compose plugin.

From the project root:

```bash
docker compose up --build
```

When the application starts, check:

```bash
curl -i http://localhost:8000/health
```

Open the interactive API documentation at:
`http://localhost:8000/docs`

Stop the services with `Ctrl+C`; use `docker compose down` to remove
the running containers.

### Option B: Local Python

Use Python 3.11 or another version supported by the project dependencies.

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies and run tests:

```bash
python -m pip install -r requirements.txt
python -m pytest -q tests
```

Start the API using the command appropriate to the application's module
layout, for example:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If the container or local startup fails, check the installed dependencies,
working directory, required data/model files, and application logs.

## Production Support Runbook

1. **Check service health:** call `/health` and inspect application logs.
2. **Identify the failing operation:** record the endpoint, timestamp,
   HTTP status, and relevant request or shipment identifier. Avoid logging
   secrets or unnecessary customer data.
3. **Check data quality:** inspect `/data-quality/report` and the generated
   report for affected datasets, severity, and recommended actions.
4. **Reconcile counts:** compare raw, curated, quarantined, and serving
   record counts. Investigate duplicate keys, missing IDs, and unexpected
   count changes before replaying data.
5. **Investigate predictions:** confirm the model artifact loads and that
   all expected booking-time features are present. Do not use actual
   arrival, actual delay, or other post-outcome fields as prediction inputs.
6. **Recover safely:** correct the underlying cause, rerun the relevant
   validation/tests, and rerun processing only after confirming that
   retries are safe and idempotent.
7. **Verify recovery:** check health, affected records, data-quality output,
   and tests. Document the cause, impact, fix, and follow-up action.

For a production deployment, add alerting, correlation IDs, access controls,
centralized log retention, and an audited recovery procedure.

## Model Evaluation and Retraining

The saved Logistic Regression model predicts whether a shipment's actual
delay exceeds 24 hours using the documented booking-time features.

The current evaluation reports:

- ROC-AUC: 0.497
- Precision: 0.3908
- Recall: 0.4934
- F1: 0.4361
- Test rows: 930

The ROC-AUC is approximately random-ranking performance. This model is a
demonstration, not a validated production decision system. Do not use its
predictions for consequential operational decisions without further
evaluation.

Before retraining:

1. Validate source data and label quality.
2. Split data using a time-aware strategy where appropriate to avoid
   training on future information.
3. Fit preprocessing and the model using training data only.
4. Exclude actual arrival, actual delay, actual departure, final status,
   and other information unavailable at booking time.
5. Evaluate precision, recall, F1, ROC-AUC, calibration, and performance
   across relevant routes and shipment groups.
6. Compare against a simple baseline and the currently saved artifact.
7. Save the new model and feature schema together; run regression tests
   before promoting it.
8. Monitor data drift, prediction quality once labels arrive, and model
   performance over time. Retrain only when justified by evidence.

A retraining schedule and automated model promotion are future production
work unless implemented elsewhere in this repository.

## GenAI Tool Use, Guardrails, and Disclosure

The assistant includes local functions for shipment queries, route statistics,
and delay prediction. Its provider-backed answer path depends on the
configured LLM provider and credentials.

The existence of local functions does not by itself prove that live
provider-backed tool selection works. Verify tool calls using the configured
provider before claiming that end-to-end LLM tool calling has passed.

Guardrails should restrict requests to the supply-chain domain, validate
tool arguments, limit tool execution, handle errors safely, and avoid
exposing credentials or sensitive data in logs. Record tool invocations and
results with appropriate redaction and retention controls.

**AI-use disclosure:** Complete this section before submission with the
actual tools used, what they assisted with, and which outputs or code were
independently tested and reviewed. Do not claim that AI-generated code is
fully verified solely because it was generated.

## Known Limitations

- The current model has weak discrimination (ROC-AUC 0.497) and requires
  further feature, label, and time-aware validation work.
- A local test pass does not establish that Docker, GitHub Actions, or a
  live external LLM provider has been successfully exercised.
- Provider-backed GenAI behavior requires valid provider configuration and
  a real integration test.
- Production readiness still requires deployment-specific security,
  monitoring, access controls, secrets management, and recovery validation.
- CI is configured in `.github/workflows/ci.yml`; its remote status must be
  verified after pushing the workflow to GitHub.


## Tech choices

- **API:** FastAPI provides typed HTTP endpoints, request validation, and structured JSON responses.
- **Data processing:** pandas handles CSV ingestion, validation, and transformations for this take-home dataset.
- **Storage:** CSV files separate raw, curated, and serving data for a lightweight, reproducible local demonstration.
- **ML:** A saved scikit-learn model is loaded by the API at startup. Requests do not retrain the model.
- **GenAI assistant:** The project provides a deterministic local assistant and an optional OpenAI tool-calling path.
- **Testing:** pytest and FastAPI TestClient support automated unit and HTTP integration tests.
- **Packaging and CI:** Docker Compose provides a single-command deployment option; GitHub Actions runs automated checks.

**Idempotency:** Curated output should be rebuilt deterministically from raw inputs, with stable shipment identifiers and explicit duplicate/conflict handling. Re-running the pipeline should not create additional copies of the same shipment.

**Data relationships:** `shipment_id` identifies a shipment; `origin_port` and `destination_port` reference port codes. Port events relate to shipments through their documented shipment/event keys. Confirm exact join keys in the source files before production use.

**Scaling by 100x:** Move raw and curated files to object storage, process incrementally with Spark, partition by useful query dimensions, use a transactional table format, and add orchestration, schema enforcement, monitoring, and workload-aware storage.

**Intentionally out of scope:** A production cloud deployment, Kubernetes, Terraform, a user interface, and high-availability infrastructure are not implemented in this take-home.


## Data quality summary

The standalone data-quality module checks raw shipment, port, and port-event datasets. It emits a JSON report containing the check name, affected row count, percentage, severity, and recommended action. The API exposes the report through `GET /data-quality/report`.

| Dataset | Check | Affected rows | Severity |
|---|---|---:|---|
| Shipments | Duplicate shipment IDs | 56 | Warning |
| Shipments | Missing actual arrival | 349 | Warning |
| Shipments | Missing weight | 73 | Critical |
| Shipments | Missing status | 54 | Warning |
| Shipments | Non-positive weight | 36 | Critical |
| Shipments | Non-positive container count | 23 | Critical |
| Shipments | Non-standard status | 30 | Warning |
| Shipments | Unknown origin port | 42 | Critical |
| Shipments | Unknown destination port | 55 | Critical |
| Shipments | Arrival earlier than planned | 950 | Info |
| Ports | Missing country | 1 | Warning |
| Port events | Missing event type | 140 | Warning |
| Port events | Missing notes | 1,913 | Warning |
| Port events | Duplicate event ID | 206 | Warning |

The full generated report contains **21 checks** across the three raw datasets. The counts above are per check; they may overlap and must not be added together as a unique number of bad rows.

The curated shipment dataset contains 4,995 rows with 4,995 distinct non-null shipment IDs. Five conflicting shipment IDs were excluded into a quarantine/conflict file. Missing-value checks returning zero and other checks not shown in this summary remain available in the full JSON report.

Critical findings require investigation or quarantine according to the check's recommended action. Informational findings, such as early arrivals, should be investigated rather than automatically rejected.


## If I had more time

1. Improve the delay model through time-aware validation, feature analysis, baseline comparison, and threshold tuning. Current ROC-AUC is approximately **0.497**, so this model is not demonstrated to be predictive enough for production use.
2. Add tests for every data-quality rule, malformed filters, date-range boundaries, and assistant tool-selection behavior.
3. Add correlation IDs, structured error categories, safe log redaction, and explicit logging for every assistant tool invocation and result.
4. Add freshness, row-count reconciliation, and schema-drift alerts.
5. Validate the container build and full startup flow in a Docker-capable environment.


## Scaling to production

- **Ingestion:** Use scheduled or event-driven incremental ingestion with checkpoints and replay support.
- **Storage:** Store immutable raw data in object storage and use a transactional lakehouse format for curated data.
- **Processing:** Use distributed Spark processing when data volume and workload justify it; avoid introducing distributed infrastructure without measured need.
- **Reliability:** Use idempotent writes, stable business keys, deduplication, quarantine, retries with limits, and source-to-target reconciliation.
- **Serving:** Put API workloads behind authenticated, rate-limited deployment infrastructure and use a database or analytical serving store appropriate to query patterns.
- **Observability:** Track latency, throughput, freshness, failures, data-quality results, model performance, and cost.
- **ML lifecycle:** Version artifacts and features, monitor drift and prediction quality, and retrain only through a tested deployment process.
- **Security:** Store credentials in a secrets manager, apply least-privilege access, and redact sensitive information from logs.
- **Deployment:** Run tests and linting in CI, build and scan the container, deploy through staged environments, verify health checks, and retain a tested rollback path.

These are proposed production improvements, not claims that cloud deployment, security controls, or scaling tests have already been implemented.
