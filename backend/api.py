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
from backend.compliance.gst_engine import GSTEngine
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
from backend.routers import reports, operations, gst, setup, debug, compliance, auth, agent
from backend.compliance.audit_service import AuditService
from typing import Optional

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
app.include_router(auth.router)  # Auth first (no API key required)
app.include_router(agent.router) # AI Agent router
app.include_router(reports.router)
app.include_router(operations.router)
app.include_router(gst.router)
app.include_router(setup.router)
app.include_router(debug.router)
app.include_router(compliance.router)
# Global simulated in-memory dataframe (single-user MVP)
dataframe = None
DATA_LOG_PATH = "data_log.pkl"
TALLY_COMPANY = os.getenv("TALLY_COMPANY", "Krishasales")
TALLY_URL = os.getenv("TALLY_URL", "http://localhost:9000")
LIVE_SYNC = bool(os.getenv("TALLY_LIVE_SYNC", ""))
# Safety flag for live Tally updates - set to "true" to enable actual sync to Tally
TALLY_LIVE_UPDATE_ENABLED = os.getenv("TALLY_LIVE_UPDATE_ENABLED", "true").lower() == "true"
print(f"[INFO] TALLY LIVE UPDATE ENABLED: {TALLY_LIVE_UPDATE_ENABLED}")

# Load Config from JSON (Overrides env vars)
import json
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if os.path.exists("k24_config.json"):
    try:
        with open("k24_config.json", "r") as f:
            config = json.load(f)
            GOOGLE_API_KEY = config.get("google_api_key", GOOGLE_API_KEY)
            TALLY_COMPANY = config.get("company_name", TALLY_COMPANY)
            TALLY_URL = config.get("tally_url", TALLY_URL)
    except:
        pass

# Initialize Tally Connector
tally = TallyConnector(url=TALLY_URL, company_name=TALLY_COMPANY)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tally_api")
from backend.orchestrator import K24Orchestrator
from backend.database import init_db, get_db, Ledger, StockItem, Bill, Voucher
from sqlalchemy.orm import Session
from backend.orchestration.response_builder import ResponseBuilder, ResponseType
from backend.orchestration.follow_up_manager import FollowUpManager
from backend.sync.sync_monitor import monitor as sync_monitor

# Initialize Orchestrator
orchestrator = None
if GOOGLE_API_KEY:
    try:
        orchestrator = K24Orchestrator(api_key=GOOGLE_API_KEY)
        logger.info("Orchestrator initialized successfully")
    except Exception as e:
        logger.error(f"Failed to init Orchestrator: {e}")
else:
    logger.warning("GOOGLE_API_KEY not found. Chat will not work.")
@app.get("/audit/run", dependencies=[Depends(get_api_key)])
def run_pre_audit():
    """
    Run Pre-Audit Compliance Check (Section 44AB)
    Returns a comprehensive audit report with issues and recommendations
    """
    try:
        # Use the global 'tally' instance
        audit_engine = AuditEngine(tally)
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
    
    # Initialize AI Agent Orchestrator
    try:
        agent.init_orchestrator()
        logger.info("[SUCCESS] AI Agent orchestrator initialized")
    except Exception as e:
        logger.error(f"[ERROR] Failed to initialize AI Agent: {e}")

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

@app.get("/vouchers", dependencies=[Depends(get_api_key)])
async def get_vouchers(voucher_type: Optional[str] = None, db: Session = Depends(get_db)):
    """Fetch vouchers from K24 Database (fast local access)"""
    try:
        # Query from database instead of Tally (much faster + shows recent entries)
        query = db.query(Voucher).order_by(Voucher.date.desc())
        
        if voucher_type:
            query = query.filter(Voucher.voucher_type == voucher_type)
        
        vouchers = query.all()
        
        # Convert to dict format
        voucher_list = [{
            "date": v.date.strftime("%Y-%m-%d") if v.date else "",
            "voucher_type": v.voucher_type,
            "voucher_number": v.voucher_number,
            "party_name": v.party_name,
            "amount": v.amount,
            "narration": v.narration,
            "sync_status": v.sync_status
        } for v in vouchers]
        
        return {"vouchers": voucher_list}
    except Exception as e:
        logger.exception("Failed to fetch vouchers from database")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ledgers/{ledger_name}/vouchers", dependencies=[Depends(get_api_key)])
async def get_ledger_vouchers(ledger_name: str):
    """Fetch vouchers for a specific ledger"""
    try:
        # Decode ledger name if needed, but FastAPI handles URL decoding
        df = tally.fetch_ledger_vouchers(ledger_name)
        if df.empty:
            return {"vouchers": []}
        return {"vouchers": df.to_dict(orient="records")}
    except Exception as e:
        logger.exception(f"Failed to fetch vouchers for {ledger_name}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reports/outstanding", dependencies=[Depends(get_api_key)])
async def get_outstanding_bills():
    """Fetch outstanding bills"""
    try:
        df = tally.fetch_outstanding_bills()
        if df.empty:
            return {"bills": []}
        return {"bills": df.to_dict(orient="records")}
    except Exception as e:
        logger.exception("Failed to fetch outstanding bills")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ledgers/search", dependencies=[Depends(get_api_key)])
async def search_ledgers(query: str):
    """Search ledgers for autocomplete"""
    try:
        matches = tally.lookup_ledger(query)
        return {"matches": matches}
    except Exception as e:
        logger.exception(f"Failed to search ledgers for '{query}'")
        raise HTTPException(status_code=500, detail=str(e))

class ReceiptVoucherRequest(BaseModel):
    party_name: str
    amount: float
    deposit_to: str = "Cash"
    narration: str = ""
    date: str  # YYYY-MM-DD
    reason: Optional[str] = "New Entry"

@app.post("/vouchers/receipt", dependencies=[Depends(get_api_key)])
async def create_receipt_voucher(request: ReceiptVoucherRequest, db: Session = Depends(get_db)):
    """Create a Receipt voucher and push to Tally + Save to Database"""
    try:
        # Convert date format YYYY-MM-DD to YYYYMMDD
        date_obj = datetime.strptime(request.date, "%Y-%m-%d")
        tally_date = date_obj.strftime("%Y%m%d")
        
        # Prepare voucher data for Tally
        voucher_data = {
            "voucher_type": "Receipt",
            "date": tally_date,
            "party_name": request.party_name,
            "amount": request.amount,
            "narration": request.narration or f"Receipt from {request.party_name}",
            "deposit_to": request.deposit_to
        }
        
        # Push to Tally FIRST
        result = tally.create_voucher(voucher_data)
        
        tally_success = result.get("status") == "OK" or "Success" in str(result.get("raw", ""))
        
        # Save to Database (even if Tally fails, for offline tracking)
        voucher_record = Voucher(
            guid=f"K24-{datetime.now().timestamp()}",  # Generate temp GUID
            voucher_number=f"RCP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            date=date_obj,
            voucher_type="Receipt",
            party_name=request.party_name,
            amount=request.amount,
            narration=request.narration or f"Receipt from {request.party_name}",
            sync_status="SYNCED" if tally_success else "ERROR"
        )
        db.add(voucher_record)
        db.commit()
        db.refresh(voucher_record)
        
        # 🛡️ AUDIT LOGGING (MCA Compliance)
        AuditService.log_change(
            db=db,
            entity_type="Voucher",
            entity_id=voucher_record.voucher_number,
            action="CREATE",
            user_id="kiran",  # TODO: Get from auth context
            old_data=None,
            new_data={
                "amount": request.amount,
                "party": request.party_name,
                "date": request.date
            },
            reason=request.reason or "New Entry"
        )
        
        if tally_success:
            return {
                "status": "success",
                "message": f"Receipt voucher created for ₹{request.amount}",
                "voucher": voucher_data,
                "db_id": voucher_record.id
            }
        else:
            logger.warning(f"Tally rejected voucher but saved to DB: {result.get('status')}")
            return {
                "status": "partial",
                "message": f"Receipt saved to K24 but Tally sync failed. Will retry later.",
                "voucher": voucher_data,
                "db_id": voucher_record.id,
                "tally_error": result.get('status', 'Unknown error')
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.exception("Failed to create receipt voucher")
        raise HTTPException(status_code=500, detail=str(e))

class SalesInvoiceItem(BaseModel):
    description: str
    quantity: float
    rate: float
    amount: float

class SalesInvoiceRequest(BaseModel):
    party_name: str
    invoice_number: str = ""
    date: str  # YYYY-MM-DD
    items: list[SalesInvoiceItem]
    subtotal: float
    discount_percent: float = 0
    discount_amount: float = 0
    gst_rate: float = 0
    gst_amount: float = 0
    grand_total: float
    narration: str = ""

@app.post("/vouchers/sales", dependencies=[Depends(get_api_key)])
async def create_sales_invoice(request: SalesInvoiceRequest, db: Session = Depends(get_db)):
    """Create a Sales Invoice with multiple line items and push to Tally + Save to Database"""
    try:
        # Convert date format
        date_obj = datetime.strptime(request.date, "%Y-%m-%d")
        tally_date = date_obj.strftime("%Y%m%d")
        
        # Prepare voucher data for Tally
        voucher_data = {
            "voucher_type": "Sales",
            "date": tally_date,
            "party_name": request.party_name,
            "amount": request.grand_total,
            "narration": request.narration or f"Sales Invoice for {request.party_name}",
            "items": [
                {
                    "name": item.description,
                    "quantity": item.quantity,
                    "rate": item.rate,
                    "amount": item.amount
                }
                for item in request.items
            ]
        }
        
        # Push to Tally FIRST
        result = tally.create_voucher(voucher_data)
        
        tally_success = result.get("status") == "OK" or "Success" in str(result.get("raw", ""))
        
        # Save to Database
        voucher_record = Voucher(
            guid=f"K24-{datetime.now().timestamp()}",
            voucher_number=request.invoice_number or f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            date=date_obj,
            voucher_type="Sales",
            party_name=request.party_name,
            amount=request.grand_total,
            narration=request.narration or f"Sales Invoice for {request.party_name}",
            sync_status="SYNCED" if tally_success else "ERROR"
        )
        db.add(voucher_record)
        db.commit()
        db.refresh(voucher_record)
        
        if tally_success:
            return {
                "status": "success",
                "message": f"Sales Invoice created for ₹{request.grand_total:,.2f}",
                "invoice": {
                    "party": request.party_name,
                    "total": request.grand_total,
                    "items_count": len(request.items),
                    "gst_amount": request.gst_amount
                },
                "db_id": voucher_record.id
            }
        else:
            logger.warning(f"Tally rejected invoice but saved to DB: {result.get('status')}")
            return {
                "status": "partial",
                "message": f"Invoice saved to K24 but Tally sync failed",
                "invoice": {
                    "party": request.party_name,
                    "total": request.grand_total,
                    "items_count": len(request.items)
                },
                "db_id": voucher_record.id,
                "tally_error": result.get('status', 'Unknown error')
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.exception("Failed to create sales invoice")
        raise HTTPException(status_code=500, detail=str(e))

class PaymentVoucherRequest(BaseModel):
    party_name: str
    amount: float
    bank_cash_ledger: str = "Cash"
    narration: str = ""
    date: str = datetime.now().strftime("%Y-%m-%d")

@app.post("/vouchers/payment", dependencies=[Depends(get_api_key)])
async def create_payment_voucher(request: PaymentVoucherRequest, db: Session = Depends(get_db)):
    """Create a Payment voucher and push to Tally + Save to Database"""
    try:
        # Convert date format
        date_obj = datetime.strptime(request.date, "%Y-%m-%d")
        tally_date = date_obj.strftime("%Y%m%d")
        
        # Prepare voucher data for Tally
        voucher_data = {
            "voucher_type": "Payment",
            "date": tally_date,
            "party_name": request.party_name,
            "amount": request.amount,
            "narration": request.narration or f"Payment to {request.party_name}",
            "deposit_to": request.bank_cash_ledger # In Tally logic, this is the Credit ledger (Cash/Bank)
        }
        
        # Push to Tally FIRST
        result = tally.create_voucher(voucher_data)
        
        tally_success = result.get("status") == "OK" or "Success" in str(result.get("raw", ""))
        
        # Save to Database
        voucher_record = Voucher(
            guid=f"K24-{datetime.now().timestamp()}",
            voucher_number=f"PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            date=date_obj,
            voucher_type="Payment",
            party_name=request.party_name,
            amount=request.amount,
            narration=request.narration or f"Payment to {request.party_name}",
            sync_status="SYNCED" if tally_success else "ERROR"
        )
        db.add(voucher_record)
        db.commit()
        db.refresh(voucher_record)
        
        if tally_success:
            return {
                "status": "success",
                "message": f"Payment created for ₹{request.amount}",
                "voucher": voucher_data,
                "db_id": voucher_record.id
            }
        else:
            logger.warning(f"Tally rejected payment but saved to DB: {result.get('status')}")
            return {
                "status": "partial",
                "message": f"Payment saved to K24 but Tally sync failed",
                "voucher": voucher_data,
                "db_id": voucher_record.id,
                "tally_error": result.get('status', 'Unknown error')
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.exception("Failed to create payment voucher")
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

@app.get("/sync/status", dependencies=[Depends(get_api_key)])
def get_sync_status():
    """Get current sync health status"""
    return sync_monitor.get_health_report()

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"
    company: Optional[str] = None # Allow user to specify company for chat
    client_context: Optional[Dict[str, Any]] = None # Context from frontend (e.g. current page)
    active_draft: Optional[Dict[str, Any]] = None

@app.post("/chat", dependencies=[Depends(get_api_key)])
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for KITTU.
    Delegates to the K24Orchestrator ("The Director").
    """
    try:
        if not orchestrator:
            raise HTTPException(status_code=500, detail="Orchestrator not initialized")

        # Pass request to the Director
        response_data = await orchestrator.process_message(
            user_id=request.user_id,
            message=request.message,
            active_draft=request.active_draft
        )
        
        return response_data

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
    - Total Sales (This Month vs Last Month)
    - Total Receivables (Current)
    - Total Payables (Current)
    - Cash in Hand (Current)
    """
    try:
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)
        
        # Calculate Last Month Start/End
        if now.month == 1:
            start_of_last_month = datetime(now.year - 1, 12, 1)
            end_of_last_month = datetime(now.year - 1, 12, 31)
        else:
            start_of_last_month = datetime(now.year, now.month - 1, 1)
            # Last day of last month is start_of_month - 1 day
            end_of_last_month = start_of_month - timedelta(days=1)

        # 1. Sales Logic
        # This Month
        sales_this_month = db.query(func.sum(Voucher.amount)).filter(
            Voucher.voucher_type == "Sales",
            Voucher.date >= start_of_month
        ).scalar() or 0.0
        
        # Last Month
        sales_last_month = db.query(func.sum(Voucher.amount)).filter(
            Voucher.voucher_type == "Sales",
            Voucher.date >= start_of_last_month,
            Voucher.date <= end_of_last_month
        ).scalar() or 0.0
        
        # Sales Change %
        if sales_last_month == 0:
            sales_change = 100.0 if sales_this_month > 0 else 0.0
        else:
            sales_change = ((sales_this_month - sales_last_month) / sales_last_month) * 100.0

        # Total Sales (All Time or Year to Date? Usually Dashboard shows YTD or Monthly. Let's show Monthly for "Total Sales" context or All Time? 
        # The UI says "Total Sales". Usually implies YTD. But for change %, we compare months.
        # Let's return This Month's Sales as the main number for now, as that's more actionable.
        # OR return Total YTD. Let's stick to Total YTD for the main number, but change is monthly? 
        # Actually, let's make "Total Sales" be "This Month's Sales" to match the change metric. 
        # User wants "math logic more correct". If I show Total All Time and say "12% from last month", that's confusing.
        # Let's return This Month's Sales.
        
        # 2. Receivables & Payables (Snapshot)
        # We don't have historical snapshots, so we can't calculate change accurately.
        # Better to show 0% change than fake data.
        receivables = db.query(func.sum(Bill.amount)).filter(Bill.amount > 0).scalar() or 0.0
        payables = db.query(func.sum(Bill.amount)).filter(Bill.amount < 0).scalar() or 0.0
        
        # 3. Cash in Hand
        cash_ledger = db.query(Ledger).filter(Ledger.name == "Cash").first()
        cash_balance = cash_ledger.closing_balance if cash_ledger else 0.0
        
        return {
            "sales": sales_this_month,
            "sales_change": round(sales_change, 1),
            "receivables": receivables,
            "receivables_change": 0.0, # No historical data yet
            "payables": abs(payables),
            "payables_change": 0.0, # No historical data yet
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

class LedgerDraft(BaseModel):
    name: str
    parent: str
    opening_balance: float
    gstin: Optional[str] = None
    email: Optional[str] = None

@app.post("/ledgers", dependencies=[Depends(get_api_key)])
async def create_ledger_endpoint(ledger: LedgerDraft):
    """
    Create a new ledger in Tally via the Sync Engine.
    """
    # 1. Validate GSTIN if provided
    if ledger.gstin:
        validation = GSTEngine.validate_gstin(ledger.gstin)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=f"Invalid GSTIN: {validation['error']}")

    try:
        # 2. Construct ledger data
        ledger_data = ledger.dict()
        
        # 3. Push to Tally
        result = sync_engine.tally.create_ledger(ledger_data)
        
        if result['status'] == "Success":
            # 4. Save to Shadow DB
            db = SessionLocal()
            try:
                new_ledger = Ledger(
                    name=ledger.name,
                    parent=ledger.parent,
                    opening_balance=ledger.opening_balance,
                    gstin=ledger.gstin,
                    email=ledger.email,
                    last_synced=datetime.now()
                )
                db.add(new_ledger)
                db.commit()
            except Exception as e:
                logger.error(f"Shadow DB Error: {e}")
                # Don't fail request if Tally succeeded
            finally:
                db.close()
                
            return {"status": "success", "message": "Ledger created successfully", "tally_response": result}
        else:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Tally Rejected", "details": result})

    except Exception as e:
        logger.error(f"Failed to create ledger: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vouchers", dependencies=[Depends(get_api_key)])
async def create_voucher_endpoint(voucher: VoucherDraft, db: Session = Depends(get_db)):
    """
    Create a voucher in Tally via the Sync Engine (Transactional).
    Includes GST Tax Calculation.
    """
    try:
        # 1. Construct voucher data
        voucher_data = voucher.dict()
        if not voucher_data.get('date'):
            from datetime import datetime
            voucher_data['date'] = datetime.now().strftime("%Y%m%d")

        # 2. GST Calculation
        # Fetch Party GSTIN from Shadow DB
        party_ledger = db.query(Ledger).filter(Ledger.name == voucher.party_name).first()
        party_gstin = party_ledger.gstin if party_ledger else None
        
        # Company GSTIN (Env or Default)
        company_gstin = os.getenv("COMPANY_GSTIN", "27ABCDE1234F1Z5") # Default to Maharashtra
        
        if party_gstin and company_gstin:
            tax_info = GSTEngine.calculate_tax(voucher.amount, party_gstin, company_gstin)
            
            # Append Tax Info to Narration
            tax_str = f" [Tax: {tax_info['type']} ₹{tax_info['total_tax']} (IGST: {tax_info['igst']}, CGST: {tax_info['cgst']}, SGST: {tax_info['sgst']})]"
            if voucher_data.get('narration'):
                voucher_data['narration'] += tax_str
            else:
                voucher_data['narration'] = tax_str.strip()
                
            # Add tax info to response data (for frontend/debug)
            voucher_data['tax_info'] = tax_info

        # 3. Use Transactional Push
        result = sync_engine.push_voucher_safe(voucher_data)
        
        if result['success']:
            return {
                "status": "success", 
                "message": result['message'], 
                "tally_response": result.get('tally_response'),
                "tax_info": voucher_data.get('tax_info')
            }
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