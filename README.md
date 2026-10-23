# Agentic AI Data Analyst

Ask questions about business sales data in plain English and get the SQL, the result table, a chart and a short AI insight. No SQL knowledge needed.

## Overview

This is a local portfolio project that combines an LLM (OpenAI), a LangGraph agent workflow, a read-only SQLite database accessed through SQLAlchemy, Pandas analysis and a Streamlit UI. It works on a fictional company, **NovaMart Analytics**, with generated sample sales data.

## Problem Statement

Business users have questions ("Which region sells most?") but the answers live in databases that need SQL. Writing SQL is a bottleneck for non-technical people.

## Solution

The app turns a natural-language question into a SQL query using an LLM that is given the database schema. The query is checked for safety, executed through a database tool, analysed with Pandas, visualised when a chart helps, and explained in one to three sentences.

## Key Features

- Natural-language to SQL (text-to-SQL) with schema-aware prompting
- SQL validation: only single read-only `SELECT`/`WITH` queries can run
- Read-only database connection as a second safety layer
- Self-correction: SQL errors are sent back to the LLM, up to 2 retries
- Clarifying questions for vague requests, honest "no data" answers for out-of-scope requests
- Pandas facts (highest, lowest, total, share, trend) feed the insight, so the LLM does not do arithmetic
- Automatic bar/line chart or KPI value
- Debug mode showing which workflow steps ran
- Upload your own data from the page: a SQLite database or CSV files

## Architecture

```
Streamlit UI (app.py)
      │  run_analysis(question)
      ▼
LangGraph workflow (src/graph.py)
      ├── LLM calls: OpenAI via LangChain (src/sql_generator.py, src/prompts.py)
      ├── SQL validator (src/sql_validator.py)
      ├── Database tool execute_sql (src/tools.py)
      │       └── SQLAlchemy read-only engine (src/database.py) ── data/sales.db
      └── Pandas analysis + chart choice (src/analysis.py, src/visualization.py)
```

The UI never touches the database or the LLM directly.

## Text-to-SQL Pipeline

1. `schema.py` reads the real tables, columns, keys and types with SQLAlchemy `inspect()` and adds short business notes (e.g. how revenue is calculated).
2. The prompt gives the LLM the schema and strict rules (only listed columns, one SELECT, SQLite syntax).
3. The LLM returns **structured output** (`status`, `sql`, `message`) validated by a Pydantic model, so the SQL never needs to be cut out of free text.

## LangGraph Workflow

```
START → get_schema → generate_sql ─┬─ ambiguous / unsupported → END (message to user)
                                   ▼
                              validate_sql ─ invalid ─┐
                                   ▼ valid            │ (retry_count < 2 → generate_sql
                              execute_sql ─ error ────┤   with the error message)
                                   ▼ ok               │ (retry_count = 2 → respond_error → END)
                            analyze_result            
                                   ▼
                           generate_insight → END
```

The shared **state** holds the question, schema, SQL, validation result, error, retry count, result rows, Pandas facts, chart choice and final answer.

## Database Schema

| Table | Columns |
|---|---|
| customers | customer_id, customer_name, region, city, customer_segment |
| products | product_id, product_name, category, unit_price (current list price) |
| orders | order_id, customer_id, order_date (YYYY-MM-DD) |
| order_items | order_item_id, order_id, product_id, quantity, unit_price (price charged) |

Revenue = `order_items.quantity * order_items.unit_price`. Region is stored only on customers (one source of truth). Data: 120 customers, 25 products, 400 orders, about 1,070 order items, January 2024 to December 2025. All names are fictional and generated with a fixed random seed.

## SQL Validation

`src/sql_validator.py` removes comments, then rejects the query if it is empty, contains more than one statement, does not start with `SELECT`/`WITH`, or contains `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `ATTACH`, `DETACH`, `PRAGMA` and similar keywords (text inside quotes is ignored). In addition, the SQLite connection is opened with `mode=ro`, so writes fail even if a check were missed.

## Pandas Analysis

`src/analysis.py` converts the result to a DataFrame and computes highest/lowest values, total, average, share of the top item, peak period and first-to-last change for time series. These facts are passed to the insight prompt.

## Visualization

Rule-based: a date/month/year column with a number → line chart; a label column with a number (2–30 rows) → bar chart; a single value → KPI metric; anything else → table only. Charts use Streamlit's built-in `st.bar_chart` / `st.line_chart`.

## Technology Stack

Python, OpenAI API, LangChain (`langchain-openai`, tools, structured output), LangGraph, SQLite, SQLAlchemy, Pandas, Streamlit, python-dotenv, pytest.

## Project Structure

```
agentic-ai-data-analyst/
├── app.py                  Streamlit UI
├── requirements.txt
├── .env.example
├── .gitignore
├── pytest.ini
├── README.md
├── data/                   sales.db is created here
├── scripts/
│   └── create_database.py  builds the sample database
├── src/
│   ├── config.py           settings and .env loading
│   ├── database.py         SQLAlchemy read-only engine, run_query()
│   ├── schema.py           schema text for the LLM, dataset info
│   ├── prompts.py          all prompts
│   ├── sql_generator.py    LLM calls (SQL + insight)
│   ├── sql_validator.py    safety checks
│   ├── tools.py            execute_sql LangChain tool
│   ├── uploads.py          turns uploaded SQLite/CSV files into a database
│   ├── analysis.py         Pandas analysis + chart choice
│   ├── visualization.py    Streamlit charts
│   └── graph.py            LangGraph agent
└── tests/                  50 tests, no API key needed
```

## Setup (Windows, VS Code)

Requires Python 3.11 or 3.12.

```powershell
cd agentic-ai-data-analyst
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again. (Command Prompt: `.venv\Scripts\activate.bat`. macOS/Linux: `source .venv/bin/activate`.)

## Environment Variables

```powershell
copy .env.example .env
```

Open `.env` and set:

```
OPENAI_API_KEY=sk-...your key...
OPENAI_MODEL=gpt-5.4-mini
```

`.env` is in `.gitignore` and must never be committed. Any OpenAI chat model that supports structured outputs can be used.

## Database Initialization

```powershell
python scripts/create_database.py
```

Expected output: row counts for customers (120), products (25), orders (400) and order_items (~1,072).

## Running the Application

```powershell
streamlit run app.py
```

Your browser opens at http://localhost:8501. Click an example question or type your own.

Terminal test without the UI:

```powershell
python -m src.graph "Which region generated the most revenue?"
```

Run the tests (no API key or internet needed; LLM calls are mocked):

```powershell
python -m pytest
```

## Using Your Own Data

The app starts on the NovaMart sample. To analyse your own data, use **Upload your own data** at the top of the sidebar:

- **One SQLite file** (`.db`, `.sqlite`, `.sqlite3`): used as it is.
- **One or more CSV files**: each file becomes one table. Names are simplified for SQL, so `Store Sales.csv` with a column `Sales Amount` becomes table `store_sales` with column `sales_amount`.

The file is saved on the server running Streamlit, in `data/uploads/` (ignored by git), and opened read-only, so the same safety rules apply. The sidebar lists the tables and row counts. For uploaded data the LLM gets the real tables and columns, row counts and example values of short text columns, but no business notes, so clear column names give better answers. Remove the file in the uploader to go back to the sample data.

## Example Questions

1. What is the total revenue?
2. Which region generated the most revenue?
3. What are the top 5 products by revenue?
4. Which category has the highest sales?
5. How many orders were placed?
6. Show monthly revenue in 2025.
7. Which region has the most customers?
8. What was the average order value?
9. Which products generated less than ₹50,000 in revenue?
10. Which products have declining sales from 2024 to 2025?
11. *Show performance.* → asks for clarification
12. *What is the weather today?* → explains the data is not available

## Screenshots

Add screenshots to a `screenshots/` folder and link them here.

## Limitations

- Text-to-SQL is not perfectly accurate; the LLM can misunderstand a question or write a query that runs but answers something slightly different. The SQL is always shown so it can be checked.
- Each question is handled independently (no conversation memory for follow-ups like "and in 2024?").
- The keyword-based validator is intentionally simple; the read-only connection is the stronger guarantee.
- Small fictional dataset, single local user, not built for production.
- Needs an OpenAI API key and internet; each question makes 2 LLM calls (more on retries).

## Future Improvements

- Conversation memory for follow-up questions
- Few-shot examples or retrieval of similar past questions to improve SQL accuracy
- A SQL parser (e.g. sqlglot) instead of keyword checks
- Evaluation set with expected results to measure accuracy
- Excel (.xlsx) uploads and a size limit per upload
