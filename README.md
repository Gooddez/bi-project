# BI Agent v2.0

Enterprise BI Agent — แปลงคำถามภาษาไทย/อังกฤษ (text หรือ voice) เป็น SQL, chart, insight และ explanation อัตโนมัติ ด้วย Google ADK + Gemini + MS SQL Server

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
  ├── [1] sql_agent          → สร้าง SQL
  ├── [2] validator_agent    → ตรวจ/แก้ SQL
  ├── [3] execute_query()    → รัน SQL Server (retry on error)
  ├── [4] profile_dataframe()→ สรุป data
  └── [5] concurrent
        ├── chart_agent      → เลือก chart type
        ├── insight_agent    → วิเคราะห์ anomaly/trend
        └── explainer_agent  → เขียน summary
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | ≥ 3.11 | required |
| [uv](https://docs.astral.sh/uv/) | latest | package + venv manager |
| ODBC Driver 18 | — | สำหรับเชื่อม MS SQL Server |

### ติดตั้ง uv (ถ้ายังไม่มี)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### ติดตั้ง ODBC Driver 18

```bash
# macOS
brew install msodbcsql18

# Ubuntu / Debian
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
sudo apt-get install msodbcsql18

# Windows — ดาวน์โหลดจาก Microsoft:
# https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
```

---

## Installation & First Run

### 1. Clone repository

```bash
git clone <repo-url>
cd bi-agent
```

### 2. สร้าง virtual environment และติดตั้ง dependencies

```bash
uv sync
```

> `uv sync` จะอ่าน `pyproject.toml` สร้าง `.venv` และติดตั้ง dependencies ทั้งหมดในครั้งเดียว

### 3. ตั้งค่า environment variables

```bash
cp .env.example .env
```

แก้ไขไฟล์ `.env`:

```env
MSSQL_SERVER=your-server.database.windows.net
MSSQL_DATABASE=your_database
MSSQL_USERNAME=your_username
MSSQL_PASSWORD=your_password
MSSQL_DRIVER=ODBC Driver 18 for SQL Server   # default, แก้ถ้าใช้ version อื่น

GOOGLE_API_KEY=your_google_api_key            # สำหรับ Gemini / ADK
```

### 4. ทดสอบ DB connection

```bash
uv run python -c "from db import validate_connection; ok, msg = validate_connection(); print(msg)"
```

### 5. รัน server

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

เปิด browser ที่ **http://localhost:8000**

---

## Project Structure

```
bi-agent/
├── main.py            # FastAPI app + endpoints
├── pipeline.py        # 5-step BI pipeline orchestration
├── tools.py           # execute_query, schema cache, data profiling
├── db.py              # MS SQL Server connection (pyodbc + SQLAlchemy)
├── chart_builder.py   # Altair chart builder (10 chart types)
├── agents/
│   ├── __init__.py
│   ├── sql_agent.py         # สร้าง SQL query
│   ├── validator_agent.py   # ตรวจ/แก้ SQL
│   ├── chart_agent.py       # เลือก chart type + config
│   ├── insight_agent.py     # วิเคราะห์ anomaly/trend
│   ├── explainer_agent.py   # เขียน plain-language summary
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
| `POST` | `/api/query` | ส่งคำถาม → รับ SQL, chart, insights, explanation |
| `GET` | `/api/health` | ตรวจสอบ DB connection |
| `GET` | `/api/schema` | ดู slim schema (`?full=true` สำหรับ full schema) |
| `POST` | `/api/schema/refresh` | bust schema cache แล้วโหลดใหม่จาก DB |
| `POST` | `/api/transcribe` | แปลง audio → text ด้วย Gemini |

### ตัวอย่าง Request

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "ยอดขายรายเดือนในปี 2024 แยกตาม product category"}'
```

### Response format

```json
{
  "sql":         "SELECT ...",
  "chart_spec":  { /* Vega-Lite JSON */ },
  "insights":    [{ "type": "anomaly", "message": "..." }],
  "explanation": "ยอดขายรวมในปี 2024 อยู่ที่...",
  "data":        [{ "month": "Jan", "sales": 120000 }],
  "columns":     ["month", "sales"],
  "row_count":   12,
  "error":       null
}
```

---

## Supported Chart Types

`bar` · `hbar` · `line` · `area` · `scatter` · `pie` · `heatmap` · `boxplot` · `histogram` · `bubble`

chart_agent จะเลือก type ที่เหมาะสมกับ data และคำถามโดยอัตโนมัติ

---

## Development

### รัน dev server พร้อม auto-reload

```bash
uv run uvicorn main:app --reload
```

### เพิ่ม dependency

```bash
uv add <package-name>
```

### รัน tests

```bash
uv run pytest
```

### Lint และ format

```bash
uv run ruff check .
uv run ruff format .
```

---

## Troubleshooting

**DB connection failed**
ตรวจว่า ODBC Driver ติดตั้งแล้ว และชื่อ driver ใน `.env` ตรงกับที่ลงไว้:
```bash
odbcinst -q -d   # Linux/macOS — แสดง driver ที่ติดตั้ง
```

**Schema ไม่อัปเดต**
เรียก endpoint refresh:
```bash
curl -X POST http://localhost:8000/api/schema/refresh
```

**Gemini API error**
ตรวจสอบว่า `GOOGLE_API_KEY` ใน `.env` ถูกต้องและ quota ยังเหลือ
