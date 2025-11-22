from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

from backend.database import get_db, Voucher, Ledger
from backend.api import get_api_key
from backend.sync_engine import sync_engine

router = APIRouter(prefix="/operations", tags=["operations"])

@router.post("/receipt", dependencies=[Depends(get_api_key)])
def create_receipt(data: Dict[str, Any]):
    """
    Create a Receipt Voucher (Money In).
    Required: party_name, amount, bank_cash_ledger
    Optional: date, narration
    """
    try:
        # 1. Construct Voucher Data
        voucher_data = {
            "voucher_type": "Receipt",
            "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
            "party_name": data["party_name"],
            "amount": float(data["amount"]),
            "narration": data.get("narration", f"Receipt from {data['party_name']}"),
            # In a real Tally Receipt, we need a second ledger (Cash/Bank) for the double entry.
            # For this MVP, we'll assume the 'party_name' is the Credit ledger, 
            # and we need a Debit ledger (Cash or Bank).
            "ledger_2": data.get("bank_cash_ledger", "Cash") 
        }
        
        # 2. Push to Tally via Sync Engine (Transactional)
        # Note: We might need to adjust push_voucher_safe to handle specific XML structure for Receipt
        # For now, we assume the generic voucher creator handles it or we'll update it.
        result = sync_engine.push_voucher_safe(voucher_data)
        
        if result["success"]:
            return {"status": "success", "message": "Receipt created successfully", "id": result.get("voucher_id")}
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except KeyError as k:
        raise HTTPException(status_code=400, detail=f"Missing field: {k}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/payment", dependencies=[Depends(get_api_key)])
def create_payment(data: Dict[str, Any]):
    """
    Create a Payment Voucher (Money Out).
    Required: party_name, amount, bank_cash_ledger
    """
    try:
        voucher_data = {
            "voucher_type": "Payment",
            "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
            "party_name": data["party_name"], # Debit Ledger
            "amount": float(data["amount"]),
            "narration": data.get("narration", f"Payment to {data['party_name']}"),
            "ledger_2": data.get("bank_cash_ledger", "Cash") # Credit Ledger
        }
        
        result = sync_engine.push_voucher_safe(voucher_data)
        
        if result["success"]:
            return {"status": "success", "message": "Payment created successfully", "id": result.get("voucher_id")}
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except KeyError as k:
        raise HTTPException(status_code=400, detail=f"Missing field: {k}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
