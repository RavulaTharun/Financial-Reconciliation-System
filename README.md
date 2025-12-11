# Financial Reconciliation System

A clean and modular system designed to automate financial reconciliation between ERP records and bank statements.
It identifies mismatches, missing transactions, and inconsistencies while providing clear and actionable summaries.

---

## Overview

Traditional reconciliation is manual, time-consuming, and error-prone.
This project offers an end-to-end backend and a simple frontend that enables users to:

* Upload ERP and bank statement files
* Extract and validate the data
* Automatically match transactions
* Detect mismatches and missing entries
* Generate clear reconciliation reports

The system is structured to be extensible and production-ready.

---

## Project Structure

```
Financial-Reconciliation-System/
│
├── app/                     # FastAPI backend with core logic
│   ├── agents/              # Agents handling extraction, cleaning, matching
│   ├── services/            # Matching engine and business logic
│   ├── routers/             # API route definitions
│   └── utils/               # Helper utilities
│
├── frontend/                # Basic frontend interface
│
├── data/                    # Sample datasets (local only; ignored in production)
│
├── main.py                  # FastAPI entry point
├── requirements.txt         # Dependencies
├── pyproject.toml           # Project configuration
└── README.md                # Project documentation
```

---

## Features

### 1. File Upload and Validation

Supports ERP Excel files and bank statements. Automatically extracts, normalizes, and validates the data.

### 2. Transaction Matching Engine

Matches ERP and bank transactions using:

* Date comparison
* Amount matching
* Description similarity
* Custom rule-based logic

### 3. Mismatch Detection

Identifies:

* Missing entries
* Duplicates
* Amount mismatches
* Date mismatches

### 4. Reconciliation Summary

Provides a structured report:

* Total matched
* Unmatched ERP transactions
* Unmatched bank transactions
* Exceptions and discrepancies

### 5. Modular Agent Architecture

Each task is handled by a dedicated agent (extraction, formatting, matching), enabling easier scaling and improvements.

---

## Tech Stack

| Layer         | Technology          |
| ------------- | ------------------- |
| Backend       | FastAPI, Python     |
| Data Handling | Pandas, Pydantic    |
| Logic Engine  | Custom Agents       |
| Frontend      | HTML, CSS, JS       |
| Server        | Uvicorn             |
| Packaging     | PEP 621 (pyproject) |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/RavulaTharun/Financial-Reconciliation-System.git
cd Financial-Reconciliation-System
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the backend server

```bash
uvicorn app.main:app --reload
```

### 4. Access the application

Open your browser and go to:

```
http://127.0.0.1:8000
```

---

## How Reconciliation Works

1. User uploads ERP and bank statement files
2. System extracts, formats, and cleans the data
3. Matching engine compares both datasets
4. Mismatches and exceptions are highlighted
5. Summary report is generated and returned to the frontend

Process Flow:

```
Upload → Extract → Validate → Match → Compare → Report → Display
```

---

## Sample Data

The `data/` folder includes sample files to test the workflow.
Sensitive or unnecessary files are removed and ignored from version control.

---

## Future Improvements

* Machine learning-based transaction classification
* Interactive dashboard and charts
* Multi-bank support
* Integration with ERP systems for automated adjustments
* User authentication and role-based access
* Deployment on cloud platforms (AWS/GCP)

---

## Contributing

Contributions are welcome.
For large updates, please open an issue first to discuss proposed changes.

---
