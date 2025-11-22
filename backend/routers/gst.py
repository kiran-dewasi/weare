from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Dict, Any
from datetime import datetime

from backend.database import get_db, Voucher
from backend.api import get_api_key

router = APIRouter(prefix="/reports", tags=["gst"])

@router.get("/gst-summary", dependencies=[Depends(get_api_key)])
def get_gst_summary(db: Session = Depends(get_db)):
    """
    Get GST Summary (GSTR-1 vs GSTR-3B Proxy).
    Calculates Output Tax (from Sales) and Input Tax (from Purchases).
    """
    year = datetime.now().year
    
    # 1. Output Tax (Sales) - Proxy
    # In real Tally, we'd check 'Duties & Taxes' ledgers in the voucher.
    # Here we assume a flat 18% on all Sales for estimation, or sum actual tax ledgers if available.
    # For MVP, we'll calculate 18% of Total Sales as estimated Output Tax.
    total_sales = db.query(func.sum(Voucher.amount)).filter(
        Voucher.voucher_type == 'Sales',
        extract('year', Voucher.date) == year
    ).scalar() or 0.0
    
    output_tax = total_sales * 0.18 # Estimated
    
    # 2. Input Tax (Purchases) - Proxy
    total_purchases = db.query(func.sum(Voucher.amount)).filter(
        Voucher.voucher_type == 'Purchase',
        extract('year', Voucher.date) == year
    ).scalar() or 0.0
    
    input_tax = total_purchases * 0.18 # Estimated
    
    return {
        "period": f"FY {year}-{year+1}",
        "gstr1": {
            "label": "Outward Supplies (GSTR-1)",
            "taxable_value": total_sales,
            "tax_amount": output_tax
        },
        "gstr3b": {
            "label": "Inward Supplies (ITC)",
            "taxable_value": total_purchases,
            "tax_amount": input_tax
        },
        "net_payable": output_tax - input_tax
    }
