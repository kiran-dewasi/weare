from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import pandas as pd
from backend.loader import LedgerLoader
from backend.agent import TallyAuditAgent
from backend.tally_connector import TallyConnector, get_customer_details
from backend import crud
import io
import os
import logging
from dotenv import load_dotenv
from fastapi.encoders import jsonable_encoder

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Tally AI Agent Backend")
# Global simulated in-memory dataframe (single-user MVP)
dataframe = None
DATA_LOG_PATH = "data_log.pkl"
TALLY_COMPANY = os.getenv("TALLY_COMPANY", "SHREE JI SALES")
TALLY_URL = os.getenv("TALLY_URL", "http://localhost:9000")
LIVE_SYNC = bool(os.getenv("TALLY_LIVE_SYNC", ""))

def checkpoint(df):
    crud.log_change(df, DATA_LOG_PATH)

class AuditRequest(BaseModel):
    question: str
    # Optionally allow text fields for CSV content or path

class ModifyRequest(BaseModel):
    action: str  # 'add' | 'update' | 'delete'
    data: Dict[str, Any]
    idx: Optional[int] = None  # For update/delete
    live_sync: Optional[bool] = False  # If True, always push change to Tally

# ----------------------- New Routes (minimal additions) -----------------------
class ImportXMLRequest(BaseModel):
    xml_input: str

@app.post("/import-tally/")
def import_tally(req: ImportXMLRequest):
    global dataframe
    xml_text = req.xml_input
    # Try parsing as ledgers first
    df_ledgers = TallyConnector._parse_ledger_xml(xml_text)
    if not df_ledgers.empty:
        dataframe = df_ledgers
        rows = jsonable_encoder(df_ledgers.to_dict(orient="records"))
        return {"status": "ok", "type": "ledger", "rows": rows}
    # Try parsing as vouchers
    df_vouchers = TallyConnector._parse_voucher_xml(xml_text)
    if not df_vouchers.empty:
        rows = jsonable_encoder(df_vouchers.to_dict(orient="records"))
        return {"status": "ok", "type": "voucher", "rows": rows}
    # Unknown/empty
    return {"status": "ok", "type": "unknown", "rows": []}

class AgentQuery(BaseModel):
    query: str

@app.post("/ask-agent/")
def ask_agent(request: AgentQuery):
    if dataframe is None:
        raise HTTPException(status_code=400, detail="No ledger data loaded.")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY environment variable not set")
    agent = TallyAuditAgent(api_key=api_key)
    result = agent.ask_audit_question(dataframe, request.query)
    return {"result": result}

class CustomerDetailsRequest(BaseModel):
    name: str

@app.post("/customer-details/")
def customer_details(req: CustomerDetailsRequest):
    if dataframe is None or dataframe.empty:
        return {"status": "error", "detail": "No data loaded."}
    details = get_customer_details(dataframe, req.name)
    return {"status": "ok", "name": req.name, "details": jsonable_encoder(details)}

@app.get("/list-ledgers/")
def list_ledgers():
    try:
        if dataframe is None:
            return {"status": "error", "detail": "No data loaded."}
        if dataframe.empty:
            return {"status": "ok", "rows": []}
        rows = jsonable_encoder(dataframe.to_dict(orient="records"))
        return {"status": "ok", "rows": rows}
    except Exception as e:
        logging.error(f"Error in list_ledgers: {e}")
        return {"status": "error", "detail": str(e)}
# --------------------- End New Routes (minimal additions) ---------------------

@app.post("/audit")
def audit_entry(request: AuditRequest):
    if dataframe is None:
        raise HTTPException(status_code=400, detail="No ledger data loaded.")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY environment variable not set")
    agent = TallyAuditAgent(api_key=api_key)
    result = agent.ask_audit_question(dataframe, request.question)
    return {"result": result}

@app.post("/modify")
def modify_entry(request: ModifyRequest):
    global dataframe
    if dataframe is None:
        raise HTTPException(status_code=400, detail="No data loaded.")
    df = dataframe.copy()
    checkpoint(df)
    try:
        use_live = request.live_sync or LIVE_SYNC
        tc = TallyConnector(TALLY_URL) if use_live else None
        company = TALLY_COMPANY if use_live else None
        # Use enhanced CRUD when live sync is requested
        id_col = "ID" if "ID" in df.columns else df.columns[0]
        crud_obj = crud.LedgerCRUD(df, id_col=id_col, tally_connector=tc, company_name=company) if use_live else None
        if request.action == 'add':
            if use_live:
                crud_obj.add_entry(request.data)
                dataframe = crud_obj.df
            else:
                dataframe = crud.add_entry(df, request.data)
        elif request.action == 'update':
            if use_live:
                entry_id = request.data.get("ID")
                if entry_id is None:
                    raise ValueError("Must supply ID for updates in live mode.")
                crud_obj.update_entry(entry_id, request.data)
                dataframe = crud_obj.df
            else:
                if request.idx is None:
                    raise ValueError("Must supply idx for updates in non-live mode.")
                if request.idx < 0 or request.idx >= len(df):
                    raise ValueError(f"Index {request.idx} is out of bounds. DataFrame has {len(df)} rows.")
                dataframe = crud.update_entry(df, request.idx, request.data)
        elif request.action == 'delete':
            if use_live:
                entry_id = request.data.get("ID")
                if entry_id is None:
                    raise ValueError("Must supply ID for delete in live mode.")
                crud_obj.delete_entry(entry_id)
                dataframe = crud_obj.df
            else:
                if request.idx is None:
                    raise ValueError("Must supply idx for delete in non-live mode.")
                if request.idx < 0 or request.idx >= len(df):
                    raise ValueError(f"Index {request.idx} is out of bounds. DataFrame has {len(df)} rows.")
                dataframe = crud.delete_entry(df, request.idx)
        else:
            raise ValueError("Unknown action")
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/load")
def load_ledger(file: UploadFile = File(...), filetype: str = Form("csv")):
    global dataframe
    content = file.file.read()
    if filetype == "csv":
        df = pd.read_csv(io.BytesIO(content))
    elif filetype == "xlsx":
        df = pd.read_excel(io.BytesIO(content))
    else:
        raise HTTPException(status_code=400, detail="Invalid filetype.")
    dataframe = df
    checkpoint(df)
    return {"status": "loaded", "shape": df.shape}

@app.post("/live_load")
def live_load(company: Optional[str] = Form(None), load_type: str = Form("ledger")):
    """Load ledgers or vouchers live from Tally, fallback to CSV if error."""
    global dataframe
    comp = company or TALLY_COMPANY
    if load_type == "ledger":
        df = LedgerLoader.load_tally_ledgers(comp, tally_url=TALLY_URL)
        if df is None:
            raise HTTPException(status_code=500, detail="Failed to load ledgers from Tally.")
    elif load_type == "voucher":
        df = LedgerLoader.load_tally_vouchers(comp, tally_url=TALLY_URL)
        if df is None:
            raise HTTPException(status_code=500, detail="Failed to load vouchers from Tally.")
    else:
        raise HTTPException(status_code=400, detail="Invalid load_type.")
    dataframe = df
    checkpoint(df)
    return {"status": "loaded", "shape": df.shape, "source": "tally"}

@app.get("/")
def root():
    return {"status": "ok", "message": "Tally AI Agent Backend"}