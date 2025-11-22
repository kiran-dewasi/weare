from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Depends, BackgroundTasks, Security
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, Iterable
import pandas as pd
from backend.loader import LedgerLoader
from backend.agent import TallyAuditAgent
from backend.tally_connector import TallyConnector, get_customer_details
from backend import crud
from backend.tally_live_update import (
    dispatch_tally_update,
    TallyAPIError,
    TallyIgnoredError,
)
from backend.tally_xml_builder import TallyXMLValidationError
from backend.orchestration.workflows.update_gstin import update_gstin_workflow
from backend.audit_engine import AuditEngine
import io
import os
import logging
from dotenv import load_dotenv
from fastapi.encoders import jsonable_encoder

# Load environment variables from .env file
load_dotenv()

from fastapi.security.api_key import APIKeyHeader

API_KEY_NAME = "x-api-key"
API_KEY = os.getenv("API_KEY", "k24-secret-key-123") # In production, use os.getenv("API_KEY")

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(status_code=403, detail="Could not validate credentials")

from fastapi.middleware.cors import CORSMiddleware
from backend.routers import reports, operations, gst

app = FastAPI(title="K24 API", description="Financial Intelligence Engine")

# Enable CORS for local development (allows chat_demo.html to talk to backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include Routers
app.include_router(reports.router)
app.include_router(operations.router)
app.include_router(gst.router)
# Global simulated in-memory dataframe (single-user MVP)
dataframe = None
DATA_LOG_PATH = "data_log.pkl"
TALLY_COMPANY = os.getenv("TALLY_COMPANY", "SHREE JI SALES")
TALLY_URL = os.getenv("TALLY_URL", "http://localhost:9000")
LIVE_SYNC = bool(os.getenv("TALLY_LIVE_SYNC", ""))
# Safety flag for live Tally updates - set to "true" to enable actual sync to Tally
TALLY_LIVE_UPDATE_ENABLED = os.getenv("TALLY_LIVE_UPDATE_ENABLED", "true").lower() == "true"
print(f"🚀 TALLY LIVE UPDATE ENABLED: {TALLY_LIVE_UPDATE_ENABLED}")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tally_api")
from backend.orchestrator import K24Orchestrator
from backend.database import init_db, get_db, Ledger, StockItem, Bill, Voucher
from sqlalchemy.orm import Session
from backend.orchestration.response_builder import ResponseBuilder, ResponseType
from backend.orchestration.follow_up_manager import FollowUpManager
@app.get("/audit/run", dependencies=[Depends(get_api_key)])
def run_pre_audit(db: Session = Depends(get_db)):
    """
    Run Pre-Audit Compliance Check (Section 44AB)
    Returns a comprehensive audit report with issues and recommendations
    """
    try:
        audit_engine = AuditEngine(db)
        report = audit_engine.run_full_audit()
        return report
    except Exception as e:
        logger.error(f"Audit Engine Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Global Sync Instance
from backend.sync_engine import SyncEngine # Assuming SyncEngine is a class
sync_engine = SyncEngine()
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from datetime import datetime
from typing import List

# Initialize Shadow DB
init_db()

# Global Orchestrator instance
orchestrator = None

# Global FollowUpManager for conversation state
follow_up_mgr = FollowUpManager()

@app.on_event("startup")
async def startup_event():
    global orchestrator
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY not set. Orchestrator will fail.")
    orchestrator = K24Orchestrator(api_key=api_key or "dummy")

def checkpoint(df):
    crud.log_change(df, DATA_LOG_PATH)

def _load_initial_data():
    import os
    import pickle
    # Try from pkl, then XML
    if os.path.exists(DATA_LOG_PATH):
        try:
            with open(DATA_LOG_PATH, 'rb') as f:
                last_df = None
                while True:
                    try:
                        last_df = pickle.load(f)
                    except EOFError:
                        break
                if last_df is not None and not last_df.empty:
                    return last_df
        except Exception as ex:
            logger.warning(f"Could not load dataframe from {DATA_LOG_PATH}: {ex}")
    # Fallback: try to parse sample_tally.xml
    if os.path.exists('sample_tally.xml'):
        try:
            with open('sample_tally.xml', 'r', encoding='utf-8') as f:
                xml_text = f.read()
            df_ledgers = TallyConnector._parse_ledger_xml(xml_text)
            if not df_ledgers.empty:
                return df_ledgers
        except Exception as ex:
            logger.warning(f"Could not load from sample_tally.xml: {ex}")
    return None

def _ensure_dataframe():
    global dataframe
    if dataframe is None or dataframe.empty:
        logger.warning("No live data available yet. Please try your query again after Tally data is fetched.")
        return pd.DataFrame()  # Return empty instead of raising error
    return dataframe

def _normalize_update_keys(df, updates):
    # Maps keys to their DataFrame counterparts (case-insensitive)
    col_map = {col.lower(): col for col in df.columns}
    normalized = {}
    invalids = []
    for k, v in updates.items():
        keynorm = col_map.get(k.lower())
        if keynorm:
            normalized[keynorm] = v
        else:
            invalids.append(k)
    return normalized, invalids

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

@app.post("/import-tally/", dependencies=[Depends(get_api_key)])
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

@app.post("/ask-agent/", dependencies=[Depends(get_api_key)])
def ask_agent(request: AgentQuery):
    df = _ensure_dataframe()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY environment variable not set")
    agent = TallyAuditAgent(api_key=api_key)
    result = agent.ask_audit_question(df, request.query)
    return {"result": result}

class CustomerDetailsRequest(BaseModel):
    name: str

@app.post("/customer-details/", dependencies=[Depends(get_api_key)])
def customer_details(req: CustomerDetailsRequest):
    df = _ensure_dataframe()
    details = get_customer_details(df, req.name)
    return {"status": "ok", "name": req.name, "details": jsonable_encoder(details)}

@app.get("/list-ledgers/", dependencies=[Depends(get_api_key)])
def list_ledgers():
    try:
        df = _ensure_dataframe()
        rows = jsonable_encoder(df.to_dict(orient="records"))
        return {"status": "ok", "rows": rows}
    except HTTPException as e:
        raise
    except Exception as e:
        logging.error(f"Error in list_ledgers: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# --------------------- End New Routes (minimal additions) ---------------------

@app.post("/audit", dependencies=[Depends(get_api_key)])
def audit_entry(request: AuditRequest):
    df = _ensure_dataframe()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY environment variable not set")
    agent = TallyAuditAgent(api_key=api_key)
    result = agent.ask_audit_question(df, request.question)
    return {"result": result}

def _get_ledger_name_from_dataframe(df: pd.DataFrame, idx: int, id_col: str = "ID") -> Optional[str]:
    """
    Extract ledger name from dataframe row.
    Tries common column names: NAME, LEDGERNAME, LEDGER_NAME, PARTYNAME, etc.
    """
    if idx < 0 or idx >= len(df):
        return None
    
    row = df.iloc[idx]
    # Try common name column variations
    name_columns = ['NAME', 'LEDGERNAME', 'LEDGER_NAME', 'PARTYNAME', 'PARTY_NAME', 'COMPANY_NAME']
    for col in name_columns:
        if col in df.columns:
            name = row.get(col)
            if pd.notna(name) and name:
                return str(name)
    # Fallback: try to find any column containing 'name' (case-insensitive)
    for col in df.columns:
        if 'name' in str(col).lower() and pd.notna(row.get(col)) and row.get(col):
            return str(row.get(col))
    return None


def _sync_to_tally_live(company_name: str, ledger_name: Optional[str], updates: Dict[str, Any],
                        action: str, tally_url: str, entity_type: str = "ledger",
                        line_items: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Sync changes to Tally using live update API.
    Only performs sync if TALLY_LIVE_UPDATE_ENABLED is True.
    Returns dict with sync status and any errors.
    """
    if not TALLY_LIVE_UPDATE_ENABLED:
        logger.info(f"Tally live update is disabled (dry-run mode). Would sync: {action} for ledger '{ledger_name}' with updates: {updates}")
        return {"status": "skipped", "reason": "dry_run_mode", "message": "Tally live update is disabled"}
    
    if entity_type == "ledger" and not ledger_name:
        raise HTTPException(status_code=400, detail="Ledger name not found")
    
    if entity_type == "ledger" and (not updates or action == 'delete'):
        # Skip sync for delete actions or if no updates
        logger.info(f"Skipping Tally sync for {action} action (no updates to sync)")
        return {"status": "skipped", "reason": "no_updates", "message": f"No updates to sync for {action} action"}
    
    try:
        logger.info(
            "Syncing %s change to Tally: company='%s', ledger='%s', entity='%s', updates=%s",
            action,
            company_name,
            ledger_name,
            entity_type,
            updates,
        )
        if entity_type == "ledger":
            payload = {"ledger_name": ledger_name, "fields": updates}
        else:
            payload = {
                "action": action,
                "voucher": updates,
                "line_items": line_items or [],
            }
        response = dispatch_tally_update(
            entity_type=entity_type,
            company_name=company_name,
            payload=payload,
            tally_url=tally_url,
            timeout=15,
        )
        logger.info(
            "Successfully synced %s to Tally (entity=%s, ledger='%s')",
            action,
            entity_type,
            ledger_name,
        )
        return {"status": "success", "response": response.to_dict()}
    except TallyIgnoredError as exc:
        logger.warning(
            "Tally ignored %s update for ledger '%s': %s",
            action,
            ledger_name,
            exc,
        )
        response = getattr(exc, "response", None)
        return {
            "status": "ignored",
            "reason": "tally_ignored",
            "message": str(exc),
            "response": response.to_dict() if response else None,
        }
    except (TallyAPIError, TallyXMLValidationError) as exc:
        logger.error(
            "Failed to sync %s to Tally for ledger '%s': %s",
            action,
            ledger_name,
            exc,
        )
        response = getattr(exc, "response", None)
        raise HTTPException(status_code=400, detail=str(exc))
    except TallyXMLValidationError as exc:
        # If exc.args[0] is a dict (from revised _sanitize_ledger_fields), return as detail
        if exc.args and isinstance(exc.args[0], dict):
            raise HTTPException(status_code=400, detail=exc.args[0])
        else:
            raise HTTPException(status_code=400, detail={"status": "error", "message": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error during Tally sync")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/modify", dependencies=[Depends(get_api_key)])
def modify_entry(request: ModifyRequest):
    df = _ensure_dataframe()
    checkpoint(df)
    sync_result = None
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
                df = crud_obj.df
            else:
                df = crud.add_entry(df, request.data)
            
            # Sync to Tally after successful add
            if TALLY_LIVE_UPDATE_ENABLED or request.live_sync:
                ledger_name = request.data.get('NAME') or request.data.get('LEDGERNAME') or request.data.get('PARTYNAME')
                if ledger_name:
                    updates = {k: v for k, v in request.data.items() if k not in ['ID', 'NAME', 'LEDGERNAME', 'PARTYNAME']}
                    sync_result = _sync_to_tally_live(
                        company_name=TALLY_COMPANY,
                        ledger_name=ledger_name,
                        updates=updates if updates else request.data,
                        action='add',
                        tally_url=TALLY_URL
                    )
                
        elif request.action == 'update':
            ledger_name = None
            if use_live:
                entry_id = request.data.get("ID")
                if entry_id is None:
                    raise HTTPException(status_code=400, detail="Must supply ID for updates in live mode.")
                try:
                    crud_obj.update_entry(entry_id, request.data)
                except Exception as ee:
                    raise HTTPException(status_code=400, detail=str(ee))
                df = crud_obj.df
                # Get ledger name from updated row
                updated_row = df[df[id_col] == entry_id]
                if not updated_row.empty:
                    ledger_name = _get_ledger_name_from_dataframe(df, updated_row.index[0], id_col)
            else:
                if request.idx is None:
                    raise HTTPException(status_code=400, detail="Must supply idx for updates in non-live mode.")
                if request.idx < 0 or request.idx >= len(df):
                    raise HTTPException(status_code=400, detail=f"Index {request.idx} is out of bounds. DataFrame has {len(df)} rows.")
                try:
                    df = crud.update_entry(df, request.idx, request.data)
                except Exception as ee:
                    raise HTTPException(status_code=400, detail=str(ee))
                # Get ledger name from updated row
                ledger_name = _get_ledger_name_from_dataframe(df, request.idx, id_col)
            
            # Sync to Tally after successful update
            if TALLY_LIVE_UPDATE_ENABLED or request.live_sync:
                sync_result = _sync_to_tally_live(
                    company_name=TALLY_COMPANY,
                    ledger_name=ledger_name,
                    updates=request.data,
                    action='update',
                    tally_url=TALLY_URL
                )
                
        elif request.action == 'delete':
            if use_live:
                entry_id = request.data.get("ID")
                if entry_id is None:
                    raise HTTPException(status_code=400, detail="Must supply ID for delete in live mode.")
                # Get ledger name before deletion
                row_to_delete = df[df[id_col] == entry_id]
                ledger_name = None
                if not row_to_delete.empty:
                    ledger_name = _get_ledger_name_from_dataframe(df, row_to_delete.index[0], id_col)
                try:
                    crud_obj.delete_entry(entry_id)
                except Exception as ee:
                    raise HTTPException(status_code=400, detail=str(ee))
                df = crud_obj.df
            else:
                if request.idx is None:
                    raise HTTPException(status_code=400, detail="Must supply idx for delete in non-live mode.")
                if request.idx < 0 or request.idx >= len(df):
                    raise HTTPException(status_code=400, detail=f"Index {request.idx} is out of bounds. DataFrame has {len(df)} rows.")
                # Get ledger name before deletion
                ledger_name = _get_ledger_name_from_dataframe(df, request.idx, id_col)
                try:
                    df = crud.delete_entry(df, request.idx)
                except Exception as ee:
                    raise HTTPException(status_code=400, detail=str(ee))
            
            # Note: We typically don't sync deletes to Tally, but log it
            if TALLY_LIVE_UPDATE_ENABLED or request.live_sync:
                logger.info(f"Delete action for ledger '{ledger_name}' - Tally sync skipped for delete operations")
                sync_result = {"status": "skipped", "reason": "delete_action", "message": "Delete operations are not synced to Tally"}
        else:
            raise HTTPException(status_code=400, detail="Unknown action")
        
        response = {"status": "success"}
        if sync_result:
            response["tally_sync"] = sync_result
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in modify_entry: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/load", dependencies=[Depends(get_api_key)])
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

@app.post("/live_load", dependencies=[Depends(get_api_key)])
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

@app.post("/tally/push", dependencies=[Depends(get_api_key)])
async def push_tally(xml_data: str = Body(..., embed=True)):
    from backend.tally_connector import push_to_tally
    result = push_to_tally(xml_data)
    if result is None:
        return {"status": "error", "detail": "Tally push failed"}
    return {"status": "success", "response": result}

# ============================================================================
# WORKFLOW ORCHESTRATION ENDPOINTS
# ============================================================================

class WorkflowRequest(BaseModel):
    workflow_name: str
    party_name: str
    company: Optional[str] = "SHREE JI SALES"
    auto_approve: Optional[bool] = False

@app.post("/workflows/execute", dependencies=[Depends(get_api_key)])
async def execute_workflow(request: WorkflowRequest):
    """
    Execute a KITTU workflow
    
    Currently supports:
    - invoice_reconciliation: Detect and fix invoice discrepancies
    """
    from backend.orchestration.workflows.invoice_reconciliation import reconcile_invoices_workflow
    
    if request.workflow_name == "invoice_reconciliation":
        try:
            result = reconcile_invoices_workflow(
                party_name=request.party_name,
                company=request.company,
                tally_url=TALLY_URL,
                auto_approve=request.auto_approve
            )
            return result
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            raise HTTPException(status_code=500, detail=f"Workflow failed: {str(e)}")
    else:
        raise HTTPException(status_code=404, detail=f"Workflow '{request.workflow_name}' not found")

@app.get("/workflows/list", dependencies=[Depends(get_api_key)])
async def list_workflows():
    """List available workflows"""
    return {
        "workflows": [
            {
                "name": "invoice_reconciliation",
                "description": "Detect and fix invoice discrepancies for a party",
                "parameters": {
                    "party_name": "string (required)",
                    "company": "string (optional, default: SHREE JI SALES)",
                    "auto_approve": "boolean (optional, default: false)"
                }
            }
        ]
    }

# ============================================================================
# CONVERSATIONAL AI ENDPOINTS (KITTU)
# ============================================================================

from backend.context_manager import ContextManager
from backend.intent_recognizer import IntentRecognizer, IntentType

# Initialize components
# Use fallback if Redis is not available
context_mgr = ContextManager(use_fallback=True)
intent_recognizer = None

def get_intent_recognizer():
    """Lazy initialization of IntentRecognizer"""
    global intent_recognizer
    if intent_recognizer is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set, IntentRecognizer will fail")
            return None
        intent_recognizer = IntentRecognizer(api_key=api_key)
    return intent_recognizer

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"
    company: Optional[str] = None # Allow user to specify company for chat

@app.post("/chat", dependencies=[Depends(get_api_key)])
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for KITTU.
    1. Get Context
    2. Recognize Intent
    3. Route Intent to appropriate action (e.g., workflow, data query, Tally update)
    4. Update context and return response
    """
    try:
        # 1. Get Context
        # Use provided company or default from env
        company = request.company or TALLY_COMPANY
        context = context_mgr.get_context(request.user_id, company=company)
        
        # Update context with latest company if provided
        if request.company:
            context_mgr.update_context(request.user_id, {"company": request.company})
            
        # 2. Recognize Intent
        recognizer = get_intent_recognizer()
        if not recognizer:
            return JSONResponse(
                status_code=500, 
                content={"error": "Intent recognition unavailable (missing API key)"}
            )
            
        intent = await recognizer.recognize(request.message, context.to_dict())
        
        response_text = ""
        workflow_result = None
        
        data_source = "cached"
        fetch_error = None

        # 3. Route Intent
        if intent.action == IntentType.RECONCILE_INVOICES:
            if intent.entity:
                # Trigger reconciliation workflow
                from backend.orchestration.workflows.invoice_reconciliation import reconcile_invoices_workflow
                
                response_text = f"I'll start reconciling invoices for {intent.entity}."
                
                try:
                    # Run workflow
                    workflow_result = reconcile_invoices_workflow(
                        party_name=intent.entity,
                        company=context.company,
                        tally_url=TALLY_URL,
                        auto_approve=False # Default to manual approval for safety
                    )
                    
                    # Format response based on result
                    if workflow_result.get("status") == "pending_approval":
                        issues = workflow_result.get("issues_found", 0)
                        fixes = workflow_result.get("fixes_suggested", 0)
                        response_text += f" I found {issues} potential issues and have suggested {fixes} fixes. Please review and approve them."
                    elif workflow_result.get("status") == "complete":
                        fixes = workflow_result.get("fixes_applied", 0)
                        response_text += f" Reconciliation complete. I've applied {fixes} fixes."
                    else:
                        response_text += " Workflow finished with status: " + workflow_result.get("status", "unknown")
                        
                    # Track active workflow
                    context_mgr.set_active_workflow(
                        request.user_id, 
                        "reconciliation", 
                        {"party": intent.entity, "status": workflow_result.get("status")}
                    )
                    
                except Exception as e:
                    logger.error(f"Workflow failed: {e}")
                    response_text += f" However, I encountered an error running the workflow: {str(e)}"
            else:
                response_text = "I understood you want to reconcile invoices, but I need to know which party/supplier to check. Could you specify the name?"

        elif intent.action == IntentType.CREATE_PURCHASE:
            # Create purchase voucher
            if intent.entity:
                try:
                    from backend.tally_live_update import create_voucher_in_tally
                    
                    # Extract parameters
                    params = intent.parameters
                    quantity = params.get("quantity", 0)
                    amount = params.get("amount")
                    rate = params.get("rate")
                    item = params.get("item", "")
                    
                    # Calculate total if rate and quantity provided
                    if not amount and rate and quantity:
                        amount = float(rate) * float(quantity)
                    
                    if not amount:
                        response_text = f"I need the total amount or rate per item to create a purchase entry for {intent.entity}. Please specify."
                    else:
                        # Build voucher
                        voucher_fields = {
                            "DATE": pd.Timestamp.now().strftime("%Y%m%d"),
                            "VOUCHERTYPENAME": "Purchase",
                            "PARTYLEDGERNAME": intent.entity,
                            "NARRATION": f"Purchase: {quantity} {item}" if item else "Purchase entry via KITTU",
                        }
                        
                        line_items = [
                            {
                                "ledger_name": intent.entity,
                                "amount": -float(amount),  # Credit party
                                "is_deemed_positive": False,
                            },
                            {
                                "ledger_name": "Purchase",  # Debit purchase account
                                "amount": float(amount),
                                "is_deemed_positive": True,
                            }
                        ]
                        
                        if TALLY_LIVE_UPDATE_ENABLED:
                            try:
                                result = create_voucher_in_tally(
                                    company_name=context.company,
                                    voucher_fields=voucher_fields,
                                    line_items=line_items,
                                    tally_url=TALLY_URL
                                )
                                response_text = f"✅ Purchase entry created successfully for {intent.entity}! Amount: ₹{amount}"
                                if result.voucher_number:
                                    response_text += f" (Voucher #: {result.voucher_number})"
                            except Exception as e:
                                logger.error(f"Tally voucher creation failed: {e}")
                                response_text = f"I tried to create the purchase entry but Tally returned an error: {str(e)}"
                        else:
                            response_text = "Live updates are disabled. I've prepared the purchase entry but haven't pushed it to Tally yet."
                except Exception as e:
                    logger.error(f"Purchase workflow failed: {e}")
                    response_text = f"I encountered an error processing your purchase: {str(e)}"
            else:
                response_text = "I can help create a purchase entry. Please specify the party name (e.g., 'I bought from ABC Corp')."

        elif intent.action == IntentType.CREATE_SALE:
            # Create sales voucher
            if intent.entity:
                try:
                    from backend.tally_live_update import create_voucher_in_tally
                    
                    # Extract parameters
                    params = intent.parameters
                    quantity = params.get("quantity", 0)
                    amount = params.get("amount")
                    rate = params.get("rate")
                    item = params.get("item", "")
                    
                    # Calculate total if rate and quantity provided
                    if not amount and rate and quantity:
                        amount = float(rate) * float(quantity)
                    
                    if not amount:
                        response_text = f"I need the total amount or rate per item to create a sales entry for {intent.entity}. Please specify."
                    else:
                        # Build voucher
                        voucher_fields = {
                            "DATE": pd.Timestamp.now().strftime("%Y%m%d"),
                            "VOUCHERTYPENAME": "Sales",
                            "PARTYLEDGERNAME": intent.entity,
                            "NARRATION": f"Sales: {quantity} {item}" if item else "Sales entry via KITTU",
                        }
                        
                        line_items = [
                            {
                                "ledger_name": intent.entity,
                                "amount": float(amount),  # Debit party
                                "is_deemed_positive": True,
                            },
                            {
                                "ledger_name": "Sales",  # Credit sales account
                                "amount": -float(amount),
                                "is_deemed_positive": False,
                            }
                        ]
                        
                        if TALLY_LIVE_UPDATE_ENABLED:
                            try:
                                result = create_voucher_in_tally(
                                    company_name=context.company,
                                    voucher_fields=voucher_fields,
                                    line_items=line_items,
                                    tally_url=TALLY_URL
                                )
                                response_text = f"✅ Sales entry created successfully for {intent.entity}! Amount: ₹{amount}"
                                if result.voucher_number:
                                    response_text += f" (Voucher #: {result.voucher_number})"
                            except Exception as e:
                                logger.error(f"Tally voucher creation failed: {e}")
                                response_text = f"I tried to create the sales entry but Tally returned an error: {str(e)}"
                        else:
                            response_text = "Live updates are disabled. I've prepared the sales entry but haven't pushed it to Tally yet."
                except Exception as e:
                    logger.error(f"Sales workflow failed: {e}")
                    response_text = f"I encountered an error processing your sale: {str(e)}"
            else:
                response_text = "I can help create a sales entry. Please specify the customer name (e.g., 'I sold to XYZ Corp')."

        elif intent.action == IntentType.UPDATE_GSTIN:
            # Update GSTIN workflow
            if intent.entity:
                gstin = intent.parameters.get("gstin")
                if not gstin:
                    response_text = f"I can help update the GSTIN for {intent.entity}, but I need the new GST number. Please provide it."
                else:
                    try:
                        result = update_gstin_workflow(
                            party_name=intent.entity,
                            new_gstin=gstin,
                            company=context.company,
                            tally_url=TALLY_URL
                        )
                        
                        if result.get("status") == "success":
                            response_text = f"✅ Successfully updated GSTIN for {intent.entity} to {gstin}."
                        else:
                            response_text = f"❌ Failed to update GSTIN: {result.get('message')}"
                            
                    except Exception as e:
                        logger.error(f"GSTIN update failed: {e}")
                        response_text = f"I encountered an error updating the GSTIN: {str(e)}"
            else:
                response_text = "I can help update a GSTIN. Please specify the party name and the new GST number."
                
        elif intent.action == IntentType.QUERY_DATA:
            # Fallback to TallyAuditAgent for general queries
            try:
                # Try to fetch live data if enabled
                if TALLY_LIVE_UPDATE_ENABLED:
                    from backend.loader import LedgerLoader
                    logger.info("Fetching live data from Tally for query...")
                    try:
                        # Fetch vouchers for better context (transactions)
                        live_df = LedgerLoader.load_tally_vouchers(
                            company_name=context.company, 
                            tally_url=TALLY_URL
                        )
                        if live_df is not None and not live_df.empty:
                            global dataframe
                            dataframe = live_df
                            data_source = "live_tally"
                            logger.info(f"Loaded {len(live_df)} live records from Tally")
                        else:
                            fetch_error = "Tally returned no data or connection failed"
                            logger.warning("Failed to fetch live data, using cached data")
                    except Exception as e:
                        fetch_error = str(e)
                        logger.error(f"Live fetch error: {e}")

                df = _ensure_dataframe()
                api_key = os.getenv("GOOGLE_API_KEY")
                agent = TallyAuditAgent(api_key=api_key)
                response_text = agent.ask_audit_question(df, request.message)
            except Exception as e:
                logger.error(f"Audit agent failed: {e}")
                response_text = "I tried to analyze the data but encountered an error."

        else:
            # Default/Unknown intent
            response_text = f"I understood you want to '{intent.action}', but I'm not fully trained on that yet. I can help you reconcile invoices or answer questions about your data."


        # 4. Check if we need follow-ups (using FollowUpManager)
        conversation = follow_up_mgr.get_conversation(request.user_id)
        
        # Only start a conversation if:
        # 1. User has CREATE_SALE or CREATE_PURCHASE intent
        # 2. We have SOME information (entity or parameters) - not just a misclassified greeting
        # 3. This is a genuine attempt to create something
        should_start_conversation = (
            not conversation and 
            intent.action in [IntentType.CREATE_SALE, IntentType.CREATE_PURCHASE] and
            (intent.entity or (intent.parameters and any(intent.parameters.values())))
        )
        
        if should_start_conversation:
            intent_str = "create_sale" if intent.action == IntentType.CREATE_SALE else "create_purchase"
            conversation = follow_up_mgr.start_conversation(request.user_id, intent_str)
            
            # Extract slots from intent
            slots = follow_up_mgr.extract_slots_from_intent({
                "entity": intent.entity,
                "parameters": intent.parameters
            })
            
            # Update conversation with extracted slots
            if slots:
                follow_up_mgr.update_conversation(request.user_id, slots)
        
        # If we have an active conversation, check for missing slots
        if conversation and follow_up_mgr.should_ask_follow_up(request.user_id):
            next_question = follow_up_mgr.get_next_question(request.user_id)
            missing_slots = conversation.get_missing_slots()
            
            # Update history
            context_mgr.add_to_history(
                request.user_id, 
                request.message, 
                next_question, 
                intent=intent.dict()
            )
            
            # Return follow-up question using ResponseBuilder
            return ResponseBuilder.follow_up(
                question=next_question,
                missing_slots=missing_slots,
                context={"intent": intent.action}
            )
        
        # If conversation is complete, clear it
        if conversation and conversation.is_complete():
            follow_up_mgr.clear_conversation(request.user_id)
        
        # 5. Update History & Return with ResponseBuilder
        context_mgr.add_to_history(
            request.user_id, 
            request.message, 
            response_text, 
            intent=intent.dict()
        )
        
        # Use ResponseBuilder for structured response
        return ResponseBuilder.text(
            message=response_text,
            metadata={
                "intent": intent.dict(),
                "workflow_result": workflow_result,
                "context": context.to_dict(),
                "debug_info": {
                    "data_source": data_source,
                    "fetch_error": fetch_error,
                    "tally_url": TALLY_URL,
                    "company": context.company
                }
            }
        )

    except Exception as e:
        logger.exception("Chat processing failed")
        raise HTTPException(status_code=500, detail=str(e))

# --- Headless Tally Endpoints (Shadow DB) ---

@app.get("/ledgers", dependencies=[Depends(get_api_key)])
def get_ledgers(db: Session = Depends(get_db)):
    """Get all ledgers from Shadow DB (Instant)"""
    return db.query(Ledger).all()

@app.get("/items", dependencies=[Depends(get_api_key)])
def get_items(db: Session = Depends(get_db)):
    """Get all stock items from Shadow DB (Instant)"""
    return db.query(StockItem).all()

@app.get("/bills", dependencies=[Depends(get_api_key)])
def get_bills(db: Session = Depends(get_db)):
    """Get outstanding bills from Shadow DB (Instant)"""
    return db.query(Bill).all()

@app.get("/bills/receivables", dependencies=[Depends(get_api_key)])
def get_receivables(db: Session = Depends(get_db)):
    """Get only money owed TO us (Psychological: Anxiety Reduction)"""
    # Assuming positive amount is receivable
    return db.query(Bill).filter(Bill.amount > 0).all()

@app.get("/dashboard/kpi", dependencies=[Depends(get_api_key)])
def get_dashboard_kpi(db: Session = Depends(get_db)):
    """
    Get Key Performance Indicators for the Dashboard.
    - Total Sales (from Vouchers)
    - Total Receivables (from Bills)
    - Total Payables (from Bills)
    - Cash in Hand (from Ledgers)
    """
    try:
        # 1. Total Sales (Sum of Sales Vouchers)
        # In a real app, filter by date range (e.g., this month)
        sales_total = db.query(func.sum(Voucher.amount)).filter(Voucher.voucher_type == "Sales").scalar() or 0.0
        
        # 2. Receivables & Payables (from Bills)
        receivables = db.query(func.sum(Bill.amount)).filter(Bill.amount > 0).scalar() or 0.0
        payables = db.query(func.sum(Bill.amount)).filter(Bill.amount < 0).scalar() or 0.0
        
        # 3. Cash in Hand (from Ledger)
        # Assuming ledger name is "Cash"
        cash_ledger = db.query(Ledger).filter(Ledger.name == "Cash").first()
        cash_balance = cash_ledger.closing_balance if cash_ledger else 0.0
        
        return {
            "sales": sales_total,
            "receivables": receivables,
            "payables": abs(payables), # Return positive number for display
            "cash": cash_balance,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"KPI Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reports/daybook", dependencies=[Depends(get_api_key)])
def get_daybook(db: Session = Depends(get_db)):
    """Get today's transactions (Psychological: Dopamine/Activity)"""
    # For MVP, returning all. In real app, filter by date.
    return db.query(Voucher).order_by(Voucher.date.desc()).all()

@app.get("/search", dependencies=[Depends(get_api_key)])
def global_search(q: str, db: Session = Depends(get_db)):
    """Global Search (Psychological: Control)"""
    ledgers = db.query(Ledger).filter(Ledger.name.ilike(f"%{q}%")).all()
    items = db.query(StockItem).filter(StockItem.name.ilike(f"%{q}%")).all()
    vouchers = db.query(Voucher).filter(or_(
        Voucher.voucher_number.ilike(f"%{q}%"),
        Voucher.party_name.ilike(f"%{q}%")
    )).all()
    
    return {
        "ledgers": ledgers,
        "items": items,
        "vouchers": vouchers
    }

@app.post("/sync", dependencies=[Depends(get_api_key)])
async def trigger_sync(background_tasks: BackgroundTasks):
    """Trigger Tally Sync in Background"""
    background_tasks.add_task(sync_engine.sync_now)
    return {"status": "Sync Started", "message": "Data is being pulled from Tally..."}

class VoucherDraft(BaseModel):
    voucher_type: str
    party_name: str
    amount: float
    date: Optional[str] = None
    narration: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = []

@app.post("/vouchers", dependencies=[Depends(get_api_key)])
async def create_voucher_endpoint(voucher: VoucherDraft):
    """
    Create a voucher in Tally via the Sync Engine (Transactional).
    """
    try:
        # 1. Construct voucher data
        voucher_data = voucher.dict()
        if not voucher_data.get('date'):
            from datetime import datetime
            voucher_data['date'] = datetime.now().strftime("%Y%m%d")

        # 2. Use Transactional Push
        result = sync_engine.push_voucher_safe(voucher_data)
        
        if result['success']:
            return {"status": "success", "message": result['message'], "tally_response": result.get('tally_response')}
        else:
             return JSONResponse(status_code=400, content={"status": "error", "message": result['error'], "details": result.get('tally_response')})

    except Exception as e:
        logger.error(f"Failed to create voucher: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vouchers/{voucher_id}/undo", dependencies=[Depends(get_api_key)])
async def undo_voucher_endpoint(voucher_id: int):
    """
    Undo a voucher (Delete from Tally & Local DB).
    """
    result = sync_engine.undo_voucher_safe(voucher_id)
    if result["success"]:
        return {"status": "success", "message": result["message"]}
    else:
        return JSONResponse(status_code=400, content={"status": "error", "message": result["error"]})

@app.get("/")
def root():
    return {"status": "ok", "message": "K24 Backend with KITTU Orchestration & Conversational AI"}