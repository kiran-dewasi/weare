# K24 AI Agent - FastAPI Router
# ===============================
# API endpoints for the AI agent

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime

from backend.agent_orchestrator_v2 import K24AgentOrchestrator
from backend.agent_response import format_agent_response
from backend.auth import get_current_user
from fastapi.security import APIKeyHeader
from fastapi import Security
import os

API_KEY_NAME = "x-api-key"
API_KEY = os.getenv("API_KEY", "k24-secret-key-123")
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["AI Agent"])

# Global orchestrator instance (initialized on startup)
_orchestrator: Optional[K24AgentOrchestrator] = None


def get_orchestrator() -> K24AgentOrchestrator:
    """Dependency to get orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = K24AgentOrchestrator()
    return _orchestrator


async def get_current_user_or_api_key(
    api_key: str = Security(api_key_header),
    token_user: dict = Depends(get_current_user)
):
    """
    Authenticate via Bearer Token OR API Key.
    Prioritizes Token if valid, otherwise checks API Key.
    """
    # If API Key is provided and matches, return a dummy user
    if api_key == API_KEY:
        return {
            "username": "k24_user",
            "role": "admin",
            "company_name": "Krishasales"
        }
    
    # If no API key, rely on the token user (which will raise 401 if missing/invalid)
    # Note: Since get_current_user is a dependency, it might raise 401 before we check API key.
    # To fix this, we need to make get_current_user optional or handle it differently.
    # But for now, let's try a simpler approach:
    return token_user

# Revised approach to avoid 401 from get_current_user blocking API key
from fastapi import Request

async def get_auth_user(
    request: Request,
    api_key: str = Security(api_key_header)
):
    # 1. Check API Key first (easiest for frontend right now)
    if api_key == API_KEY:
        return {
            "username": "k24_user",
            "role": "admin",
            "company_name": "Krishasales",
            "tier": "enterprise"
        }
    
    # 2. If no API key, try to extract Bearer token manually to avoid auto-401
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # In a real scenario, we'd verify the token here.
        # For now, if the frontend is sending API key, we are good.
        pass
        
    # If we are here, authentication failed
    raise HTTPException(status_code=401, detail="Not authenticated")


# ========== Request/Response Models ==========

class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str = Field(..., description="User's natural language command")
    context: Optional[Dict[str, Any]] = Field(default={}, description="Additional context")
    auto_approve: bool = Field(default=False, description="Auto-approve transactions (testing only)")
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Create invoice for HDFC Bank for ₹50,000 with 18% GST",
                "context": {},
                "auto_approve": False
            }
        }


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    status: str
    type: str
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str


class ApprovalRequest(BaseModel):
    """Request model for approval endpoint"""
    transaction_id: str = Field(..., description="Transaction ID to approve")
    approved: bool = Field(..., description="True to approve, False to cancel")
    notes: Optional[str] = Field(default=None, description="Approval notes")
    
    class Config:
        schema_extra = {
            "example": {
                "transaction_id": "TXN_20251202_001",
                "approved": True,
                "notes": "Approved by manager"
            }
        }


# ========== Endpoints ==========

from backend.middleware.main_middleware import RequestOrchestrator



@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    req: Request,
    current_user: dict = Depends(get_auth_user),
    orchestrator: K24AgentOrchestrator = Depends(get_orchestrator)
) -> Dict[str, Any]:
    """
    Main chat endpoint - process user's natural language command.
    """
    # Run comprehensive pre-request validation
    await RequestOrchestrator.validate_request(
        request=req,
        user_id=current_user.get("username"),
        user_tier=current_user.get("tier", "free"),
        message_content=request.message
    )
    
    try:
        print(f"[API RECEIVED] User: {request.message}")
        print(f"[API] Request headers: {{'x-api-key': '***'}}")
        logger.info(f"Chat request from user {current_user.get('username')}: {request.message}")
        
        # Get company name from user context or default
        company_name = current_user.get("company_name", "Krishasales")
        
        # Process message through orchestrator
        agent_output = await orchestrator.process_message(
            user_message=request.message,
            user_id=current_user.get("username"),
            company_name=company_name,
            auto_approve=request.auto_approve
        )
        
        # Format response
        formatted_response = format_agent_response(agent_output)
        
        logger.info(f"Response status: {formatted_response.get('status')}")
        
        return formatted_response
    
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        
        # Use AgentErrorHandler to format the error
        from backend.agent_error_handler import AgentErrorHandler
        handler = AgentErrorHandler()
        agent_error = handler.handle_error(e, {"operation": "chat_endpoint"})
        
        raise HTTPException(
            status_code=500,
            detail=agent_error.to_dict()
        )


@router.post("/approve")
async def approve_transaction(
    request: ApprovalRequest,
    current_user: dict = Depends(get_auth_user),
    orchestrator: K24AgentOrchestrator = Depends(get_orchestrator)
) -> Dict[str, Any]:
    """
    Approve (or reject) a pending transaction.
    
    This endpoint:
    1. Retrieves the pending transaction
    2. Executes it in Tally (if approved)
    3. Returns the result
    """
    
    try:
        logger.info(
            f"Approval request from {current_user.get('username')}: "
            f"{request.transaction_id} - {'APPROVED' if request.approved else 'REJECTED'}"
        )
        
        if not request.approved:
            # User rejected the transaction
            return {
                "status": "CANCELLED",
                "type": "success",
                "message": "Transaction cancelled",
                "transaction_id": request.transaction_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        # Execute the transaction
        result = await orchestrator.approve_transaction(
            transaction_id=request.transaction_id,
            user_id=current_user.get("username")
        )
        
        # Format response
        formatted_response = format_agent_response(result)
        
        return formatted_response
    
    except Exception as e:
        logger.error(f"Approval endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "status": "ERROR",
                "message": f"Approval failed: {str(e)}",
                "error_code": "APPROVAL_ERROR"
            }
        )


@router.get("/preview/{transaction_id}")
async def get_transaction_preview(
    transaction_id: str,
    current_user: dict = Depends(get_auth_user),
    orchestrator: K24AgentOrchestrator = Depends(get_orchestrator)
) -> Dict[str, Any]:
    """
    Get preview/details of a transaction.
    
    Used to refresh preview data or retrieve transaction status.
    """
    
    try:
        # Get transaction status from orchestrator
        status = orchestrator.transaction_manager.get_transaction_status(transaction_id)
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "NOT_FOUND",
                    "message": f"Transaction {transaction_id} not found"
                }
            )
        
        return {
            "status": "SUCCESS",
            "type": "preview",
            "transaction_id": transaction_id,
            "transaction_status": status,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "status": "ERROR",
                "message": f"Failed to get preview: {str(e)}"
            }
        )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for the AI agent service.
    
    Returns:
    - Status of the agent service
    - Status of dependencies (Tally, Gemini)
    """
    
    try:
        orchestrator = get_orchestrator()
        
        # Check Tally connection
        tally_status = "ONLINE"
        try:
            ledgers = orchestrator.tally.fetch_ledgers()
            if ledgers.empty:
                tally_status = "EMPTY"
        except Exception as e:
            tally_status = f"OFFLINE: {str(e)}"
        
        # Check Gemini API
        gemini_status = "ONLINE"
        try:
            # Simple check if API key is present and orchestrator is initialized
            # We avoid making a live call here to prevent quota drain from monitoring tools
            if not orchestrator.api_key:
                gemini_status = "OFFLINE: No API Key"
            else:
                # Assume online if initialized, deep check happens in middleware if needed
                gemini_status = "ONLINE"
        except Exception as e:
            gemini_status = f"OFFLINE: {str(e)}"
        
        overall_status = "HEALTHY" if tally_status == "ONLINE" and gemini_status == "ONLINE" else "DEGRADED"
        
        return {
            "status": overall_status,
            "components": {
                "orchestrator": "ONLINE",
                "tally": tally_status,
                "gemini": gemini_status
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "ERROR",
            "components": {
                "orchestrator": f"ERROR: {str(e)}"
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/capabilities")
async def get_capabilities() -> Dict[str, Any]:
    """
    Get information about agent capabilities.
    
    Returns list of supported intents, features, and limitations.
    """
    
    return {
        "status": "SUCCESS",
        "capabilities": {
            "supported_intents": [
                {
                    "intent": "create_invoice",
                    "description": "Create a sales invoice",
                    "example": "Create invoice for HDFC Bank for ₹50,000 with 18% GST"
                },
                {
                    "intent": "create_receipt",
                    "description": "Record a payment received from customer",
                    "example": "Received payment of ₹25,000 from Reliance"
                },
                {
                    "intent": "create_payment",
                    "description": "Record a payment made to vendor",
                    "example": "Paid ₹10,000 to Electricity Board"
                },
                {
                    "intent": "query_data",
                    "description": "Query financial data",
                    "example": "Show me outstanding receivables"
                },
                {
                    "intent": "audit_transactions",
                    "description": "Audit and review transactions",
                    "example": "Check all transactions above ₹1 lakh"
                }
            ],
            "features": [
                "Natural language processing",
                "Automatic ledger lookup and fuzzy matching",
                "Amount validation and risk detection",
                "GST calculation",
                "Transaction preview before execution",
                "Automatic rollback on failure",
                "Audit trail logging"
            ],
            "limitations": [
                "Tally must be running and accessible",
                "Internet connection required for AI processing",
                "Maximum transaction amount: ₹10,00,000",
                "Educational Tally mode has date restrictions"
            ]
        },
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# ========== Initialization ==========

def init_orchestrator():
    """Initialize orchestrator on app startup"""
    global _orchestrator
    try:
        _orchestrator = K24AgentOrchestrator()
        logger.info("AI Agent orchestrator initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator: {e}")
        _orchestrator = None
