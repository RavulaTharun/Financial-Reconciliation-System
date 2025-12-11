# Financial Reconciliation MVP

## Overview
An AI-powered financial reconciliation system using LangChain and LangGraph agents to automatically match ERP Excel data with Bank Statement PDF, classify discrepancies, and generate reconciliation reports with full audit trails.

## Project Structure
```
├── app/
│   ├── agents/           # AI agent implementations
│   │   ├── ingest_bank.py    # Bank PDF parser agent
│   │   ├── ingest_erp.py     # ERP Excel parser agent
│   │   ├── dedupe.py         # Duplicate detection agent
│   │   ├── matcher.py        # Multi-tier matching agent
│   │   ├── classifier.py     # Exception classification agent
│   │   ├── explain.py        # Explanation generation agent
│   │   ├── orchestrator.py   # LangGraph workflow orchestrator
│   │   └── output_generator.py # Output file generator
│   ├── api/
│   │   └── routes.py     # FastAPI endpoints
│   ├── core/
│   │   ├── config.py     # Configuration and thresholds
│   │   ├── utils.py      # Utility functions and logging
│   │   └── storage.py    # Run storage and vector DB
│   ├── outputs/
│   │   ├── logs/         # Agent logs (JSON)
│   │   └── results/      # Reconciled files, reports
│   └── main.py           # FastAPI application entry point
├── frontend/
│   ├── index.html        # Web interface
│   ├── styles.css        # Styling
│   └── app.js            # Frontend JavaScript
├── data/
│   ├── bank_statement.pdf    # Input bank statement
│   └── erp_data.xlsx         # Input ERP data
└── attached_assets/      # Original uploaded files
```

## Tech Stack
- **Backend**: Python 3.11, FastAPI, LangChain, LangGraph
- **Agents**: 6 specialized AI agents orchestrated via LangGraph
- **Data Processing**: pandas, pdfplumber, openpyxl
- **Vector DB**: ChromaDB (for fuzzy matching)
- **Logging**: Loguru with structured JSON logs
- **Frontend**: HTML/CSS/JavaScript (vanilla)

## Agent Pipeline
1. **BankIngestAgent** - Parses bank statement PDF, extracts transactions
2. **ERPIngestAgent** - Parses ERP Excel, auto-detects columns
3. **DedupeAgent** - Identifies duplicate transactions in both sources
4. **MatcherAgent** - Performs exact, rounding, and fuzzy matching
5. **ClassifierAgent** - Classifies exceptions and discrepancies
6. **ExplainAgent** - Generates human-readable explanations

## API Endpoints
- `POST /api/start` - Start a new reconciliation run
- `GET /api/status/{run_id}` - Get run status and progress
- `GET /api/logs/{run_id}` - Get agent logs for a run
- `GET /api/download/{run_id}` - Download results ZIP file
- `GET /api/runs` - List all runs
- `GET /api/health` - Health check

## Configuration Thresholds
- `AMOUNT_ROUNDING_TOLERANCE`: $0.01
- `FUZZY_AMOUNT_ABS`: $1.00
- `FUZZY_DATE_DAYS`: 3 days
- `CONFIDENCE_THRESHOLD_HUMAN_REVIEW`: 0.6

## Running the Application
The application runs on port 5000 via uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 5000
```

## Outputs Generated
- `reconciled_master_{run_id}.xlsx` - Full reconciliation results
- `summary_report_{run_id}.pdf` - Executive summary report
- `{run_id}_config.json` - Configuration snapshot
- `workflow_graph_{run_id}.txt` - Agent workflow diagram
- Agent logs in `app/outputs/logs/`

## Recent Changes
- Initial MVP implementation (2025-12-11)
- Implemented all 6 AI agents with LangGraph orchestration
- Created FastAPI backend with async processing
- Built responsive frontend with live progress tracking
