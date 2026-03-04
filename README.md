# BI Agent v2.0

An enterprise BI agent that converts natural language questions (text or voice) into SQL queries, charts, insights, and plain-language explanations — powered by Google ADK, Gemini, and MS SQL Server.

---

## System Architecture

```
User (text / voice)
        │
        ▼
FastAPI (main.py)
        │
        ▼
pipeline.py — run_pipeline()
  ├── [1] sql_agent           → generate SQL from question
  ├── [2] validator_agent     → validate and fix SQL before execution
  ├── [3] execute_query()     → run against SQL Server (auto-retry on error)
  ├── [4] profile_dataframe() → summarise result data for agents
  └── [5] concurrent
        ├── chart_agent       → select chart type and config
        ├── insight_agent     → detect anomalies and trends
        └── explainer_agent   → write plain-language summary
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | ≥ 3.11 | required |
| [uv](https://docs.astral.sh/uv/) | latest | package & venv manager |
| ODBC Driver 18 | — | required for MS SQL Server |

### Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install ODBC Driver 18

```bash
# macOS
brew install msodbcsql18

# Ubuntu / Debian
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
sudo apt-get install msodbcsql18

# Windows — download from Microsoft:
# https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
```

---

## Installation & First Run

### 1. Clone the repository

```bash
git clone <repo-url>
cd bi-agent
```

### 2. Create a virtual environment and install dependencies

```bash
uv sync
```

> `uv sync` reads `pyproject.toml`, creates `.venv`, and installs all dependencies in one step.

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
MSSQL_SERVER=your-server.database.windows.net
MSSQL_DATABASE=your_database
MSSQL_USERNAME=your_username
MSSQL_PASSWORD=your_password
MSSQL_DRIVER=ODBC Driver 18 for SQL Server   # change if using a different version

GOOGLE_API_KEY=your_google_api_key            # required for Gemini / ADK
```

### 4. Verify the database connection

```bash
uv run python -c "from db import validate_connection; ok, msg = validate_connection(); print(msg)"
```

### 5. Start the server

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at **http://localhost:8000**

---

## Project Structure

```
bi-agent/
├── main.py            # FastAPI app and API endpoints
├── pipeline.py        # 5-step BI pipeline orchestration
├── tools.py           # execute_query, schema cache, data profiling
├── db.py              # MS SQL Server connection (pyodbc + SQLAlchemy)
├── chart_builder.py   # Altair chart builder (10 chart types)
├── agents/
│   ├── __init__.py
│   ├── sql_agent.py         # generates SQL query from question
│   ├── validator_agent.py   # validates and repairs SQL
│   ├── chart_agent.py       # selects chart type and builds config
│   ├── insight_agent.py     # detects anomalies and trends
│   ├── explainer_agent.py   # writes plain-language summary
│   └── transcriber.py       # Gemini audio transcription
├── static/
│   ├── index.html
│   └── app.js
├── pyproject.toml
└── .env
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/query` | Submit a question; returns SQL, chart, insights, and explanation |
| `GET` | `/api/health` | Check database connectivity |
| `GET` | `/api/schema` | View slim schema (append `?full=true` for full schema) |
| `POST` | `/api/schema/refresh` | Bust schema cache and reload from database |
| `POST` | `/api/transcribe` | Transcribe audio to text via Gemini |

### Example Request

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Show monthly sales in 2024 broken down by product category"}'
```

### Response Format

```json
{
  "sql":         "SELECT ...",
  "chart_spec":  { /* Vega-Lite JSON */ },
  "insights":    [{ "type": "anomaly", "message": "..." }],
  "explanation": "Total sales in 2024 were...",
  "data":        [{ "month": "Jan", "sales": 120000 }],
  "columns":     ["month", "sales"],
  "row_count":   12,
  "error":       null
}
```

---

## Supported Chart Types

`bar` · `hbar` · `line` · `area` · `scatter` · `pie` · `heatmap` · `boxplot` · `histogram` · `bubble`

The `chart_agent` automatically selects the most appropriate type based on the data shape and the original question.

---

## Development

### Run dev server with auto-reload

```bash
uv run uvicorn main:app --reload
```

### Add a dependency

```bash
uv add <package-name>
```

### Run tests

```bash
uv run pytest
```

### Lint and format

```bash
uv run ruff check .
uv run ruff format .
```

---

## Troubleshooting

**DB connection failed**
Verify that ODBC Driver 18 is installed and that the driver name in `.env` matches exactly:
```bash
odbcinst -q -d   # Linux/macOS — lists installed drivers
```

**Schema not updating**
Call the refresh endpoint to bust the cache:
```bash
curl -X POST http://localhost:8000/api/schema/refresh
```

**Gemini API error**
Confirm that `GOOGLE_API_KEY` in `.env` is valid and that your quota has not been exceeded.