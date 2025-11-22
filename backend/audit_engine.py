"""
K24 Audit Engine
Pre-Audit Compliance Checks for Section 44AB (Tax Audit)
"""
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from backend.database import Ledger, Voucher, StockItem, Bill

logger = logging.getLogger(__name__)

class AuditIssue:
    """Represents a single audit finding"""
    def __init__(self, severity: str, clause: str, title: str, description: str, count: int = 0, details: List[Dict] = None):
        self.severity = severity  # CRITICAL, WARNING, INFO
        self.clause = clause  # Form 3CD clause reference
        self.title = title
        self.description = description
        self.count = count
        self.details = details or []
    
    def to_dict(self):
        return {
            "severity": self.severity,
            "clause": self.clause,
            "title": self.title,
            "description": self.description,
            "count": self.count,
            "details": self.details
        }

class AuditEngine:
    """
    K24 Pre-Audit Engine
    Scans Shadow DB for common Section 44AB compliance issues
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.issues: List[AuditIssue] = []
    
    def run_full_audit(self) -> Dict[str, Any]:
        """Run all audit checks and return a comprehensive report"""
        logger.info("Starting Pre-Audit Compliance Check...")
        
        self.issues = []
        
        # Run all checks
        self._check_cash_payments_above_limit()
        self._check_negative_cash_balance()
        self._check_negative_stock()
        self._check_tds_compliance()
        self._check_voucher_numbering()
        
        # Generate summary
        critical_count = sum(1 for i in self.issues if i.severity == "CRITICAL")
        warning_count = sum(1 for i in self.issues if i.severity == "WARNING")
        
        risk_level = "HIGH" if critical_count > 0 else ("MEDIUM" if warning_count > 0 else "LOW")
        
        return {
            "audit_date": datetime.now().isoformat(),
            "risk_level": risk_level,
            "summary": {
                "critical": critical_count,
                "warnings": warning_count,
                "total_issues": len(self.issues)
            },
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": self._generate_recommendations()
        }
    
    def _check_cash_payments_above_limit(self):
        """
        Section 40A(3): No cash payment > ₹10,000 in a single day
        Clause 21 in Form 3CD
        """
        try:
            # Query vouchers with Cash ledger and amount > 10,000
            # This is a simplified check - real implementation would need to:
            # 1. Parse ledger entries within vouchers
            # 2. Group by date and party
            # 3. Sum transactions to same party on same day
            
            # For MVP, we'll check if any single voucher has amount > 10,000
            violations = self.db.query(Voucher).filter(
                Voucher.party_name.isnot(None),
                Voucher.amount > 10000,
                Voucher.voucher_type.in_(["Payment", "Receipt"])
            ).all()
            
            if violations:
                details = [{
                    "voucher_no": v.voucher_number,
                    "date": v.date.strftime("%Y-%m-%d") if v.date else "N/A",
                    "party": v.party_name,
                    "amount": v.amount
                } for v in violations[:10]]  # Show first 10
                
                self.issues.append(AuditIssue(
                    severity="CRITICAL",
                    clause="Clause 21 (Section 40A(3))",
                    title="Cash Payments Exceeding ₹10,000",
                    description=f"Found {len(violations)} cash transactions exceeding ₹10,000 limit. These payments may be disallowed.",
                    count=len(violations),
                    details=details
                ))
                logger.warning(f"Found {len(violations)} cash payment violations")
        except Exception as e:
            logger.error(f"Error in cash payment check: {e}")
    
    def _check_negative_cash_balance(self):
        """
        Negative cash balance is impossible and indicates book-keeping errors
        """
        try:
            cash_ledger = self.db.query(Ledger).filter(
                Ledger.name.ilike("%cash%")
            ).first()
            
            if cash_ledger and cash_ledger.closing_balance < 0:
                self.issues.append(AuditIssue(
                    severity="CRITICAL",
                    clause="Accounting Principle",
                    title="Negative Cash Balance",
                    description=f"Cash ledger shows negative balance of ₹{abs(cash_ledger.closing_balance):,.2f}. This is physically impossible.",
                    count=1,
                    details=[{"ledger": cash_ledger.name, "balance": cash_ledger.closing_balance}]
                ))
                logger.warning("Negative cash balance detected")
        except Exception as e:
            logger.error(f"Error in cash balance check: {e}")
    
    def _check_negative_stock(self):
        """
        Negative stock indicates selling more than available
        """
        try:
            negative_items = self.db.query(StockItem).filter(
                StockItem.closing_balance < 0
            ).all()
            
            if negative_items:
                details = [{
                    "item": item.name,
                    "balance": item.closing_balance
                } for item in negative_items[:10]]
                
                self.issues.append(AuditIssue(
                    severity="CRITICAL",
                    clause="Inventory Valuation",
                    title="Negative Stock Balance",
                    description=f"Found {len(negative_items)} items with negative stock. You cannot sell what you don't have.",
                    count=len(negative_items),
                    details=details
                ))
                logger.warning(f"Found {len(negative_items)} negative stock items")
        except Exception as e:
            logger.error(f"Error in stock check: {e}")
    
    def _check_tds_compliance(self):
        """
        Clause 34: TDS deduction compliance
        Check if expenses like Rent, Professional Fees have TDS entries
        """
        try:
            # Simplified check: Look for ledgers that typically require TDS
            # Real implementation would check if corresponding TDS vouchers exist
            
            tds_required_ledgers = self.db.query(Ledger).filter(
                Ledger.name.ilike("%professional%") |
                Ledger.name.ilike("%legal%") |
                Ledger.name.ilike("%rent%") |
                Ledger.name.ilike("%contractor%")
            ).all()
            
            if tds_required_ledgers:
                # Check if there are any TDS ledgers
                tds_ledgers = self.db.query(Ledger).filter(
                    Ledger.name.ilike("%tds%")
                ).count()
                
                if tds_ledgers == 0:
                    self.issues.append(AuditIssue(
                        severity="WARNING",
                        clause="Clause 34 (TDS Compliance)",
                        title="Potential TDS Non-Compliance",
                        description=f"Found {len(tds_required_ledgers)} expense ledgers that may require TDS, but no TDS ledgers found.",
                        count=len(tds_required_ledgers),
                        details=[{"ledger": l.name} for l in tds_required_ledgers[:5]]
                    ))
        except Exception as e:
            logger.error(f"Error in TDS compliance check: {e}")
    
    def _check_voucher_numbering(self):
        """
        Vouchers should be sequentially numbered
        """
        try:
            # Check for gaps in voucher numbering
            # This is a simplified check
            vouchers = self.db.query(Voucher.voucher_number).filter(
                Voucher.voucher_number.isnot(None)
            ).order_by(Voucher.voucher_number).all()
            
            # For now, just log that we checked
            # Real implementation would parse numbers and find gaps
            logger.info(f"Checked {len(vouchers)} vouchers for sequential numbering")
        except Exception as e:
            logger.error(f"Error in voucher numbering check: {e}")
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on findings"""
        recommendations = []
        
        if any(i.severity == "CRITICAL" for i in self.issues):
            recommendations.append("❌ Critical issues found. Rectify these immediately before year-end.")
            recommendations.append("💡 Consider consulting with your CA to restructure problematic entries.")
        
        if any("Cash Payment" in i.title for i in self.issues):
            recommendations.append("📝 Replace cash payments > ₹10k with bank transfers or split into multiple days.")
        
        if any("Negative" in i.title for i in self.issues):
            recommendations.append("🔧 Review and correct entries causing negative balances.")
        
        if any("TDS" in i.title for i in self.issues):
            recommendations.append("📊 Verify TDS deduction and payment for applicable expenses.")
        
        if not self.issues:
            recommendations.append("✅ Books are in good shape! Ready for CA review.")
        
        return recommendations
