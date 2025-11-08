# Tally AI Agent Backend (MVP)

## Overview
This project provides a backend-only MVP AI agent system for interacting with, auditing, and modifying Tally accounting data via natural language. It uses FastAPI, Gemini (LangChain), and Pandas, and works with Tally CSV/XLSX exports.

### Features
- Load Tally ledger/voucher exports with Pandas
- Conversational audit/question answering with Gemini (LangChain)
- CRUD operations and modification logging with undo support
- REST API endpoints for audit and modification

## Directory Structure
- `/backend` — All Python logic, modularized

## Quickstart
1. **Install dependencies:**
   ```sh
   python -m venv .venv
   .venv\Scripts\activate  # On Windows
   pip install --upgrade pip
   pip install fastapi uvicorn pandas langchain-google-genai
   ```
2. **Run the API server:**
   ```sh
   uvicorn backend.api:app --reload
   ```
3. Use tools like Postman/curl to POST to `/audit` and `/modify` endpoints.

## Development
Backend code is modularized in `/backend`. Add sample Tally CSV/XLSX data and extend logic as needed.

---
For detailed instructions, consult documentation (WIP).
