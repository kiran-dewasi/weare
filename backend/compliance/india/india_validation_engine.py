"""
K24 Indian Compliance - Validation Engine
==========================================
Main validation engine that runs all India-specific rules.
"""

import logging
from typing import Dict, Any, List
from datetime import date
from pydantic import BaseModel, Field
from backend.compliance.india import india_validation_rules as rules

logger = logging.getLogger(__name__)

class ValidationIssue(BaseModel):
    """Single validation issue"""
    rule_name: str
    severity: str  # BLOCK, WARN, INFO
    message: str
    action: str
    is_blocking: bool

class ValidationResult(BaseModel):
    """Complete validation result"""
    is_valid: bool = True
    errors: List[ValidationIssue] = Field(default_factory=list)
    warnings: List[ValidationIssue] = Field(default_factory=list)
    infos: List[ValidationIssue] = Field(default_factory=list)
    
    def add_issue(self, rule_name: str, is_valid: bool, severity: str, message: str, action: str):
        """Add a validation issue"""
        issue = ValidationIssue(
            rule_name=rule_name,
            severity=severity,
            message=message,
            action=action,
            is_blocking=(severity == rules.SEVERITY_BLOCK)
        )
        
        if severity == rules.SEVERITY_BLOCK:
            self.errors.append(issue)
            self.is_valid = False
        elif severity == rules.SEVERITY_WARN:
            self.warnings.append(issue)
        else:  # INFO
            self.infos.append(issue)
    
    def has_blocking_errors(self) -> bool:
        """Check if there are blocking errors"""
        return len(self.errors) > 0
    
    def get_summary(self) -> str:
        """Get summary string"""
        return f"{len(self.errors)} errors, {len(self.warnings)} warnings, {len(self.infos)} infos"

class IndiaValidationEngine:
    """Main validation engine for Indian compliance"""
    
    def validate_india(
        self,
        parameters: Dict[str, Any],
        intent: str,
        context: Dict[str, Any] = None
    ) -> ValidationResult:
        """
        Run all applicable Indian compliance rules.
        
        Args:
            parameters: Extracted parameters (customer, amount, date, etc.)
            intent: User intent (CREATE_INVOICE, etc.)
            context: Additional context (turnover, etc.)
            
        Returns:
            ValidationResult with all issues
            
        Example:
            >>> engine = IndiaValidationEngine()
            >>> result = engine.validate_india(
            ...     {"amount": 50000, "gst_rate": 18, "customer": "ABC"},
            ...     "CREATE_INVOICE"
            ... )
            >>> print(result.get_summary())
            "0 errors, 2 warnings, 1 infos"
        """
        result = ValidationResult()
        context = context or {}
        
        # Extract parameters
        amount = parameters.get("amount", 0)
        gst_rate = parameters.get("gst_rate")
        customer = parameters.get("customer_name")
        invoice_date = parameters.get("date", date.today())
        supplier_gstin = parameters.get("supplier_gstin")
        payment_type = parameters.get("payment_type")
        
        # Context
        turnover = context.get("annual_turnover", 0)
        business_type = context.get("business_type", "GOODS")
        ytd_turnover = context.get("ytd_turnover", 0)
        months_elapsed = context.get("months_elapsed", date.today().month)
        
        # RULE 1: GST Registration Required
        if turnover > 0:
            is_valid, severity, message, action = rules.rule_gst_registration_required(turnover, business_type)
            result.add_issue("GST_REGISTRATION_REQUIRED", is_valid, severity, message, action)
        
        # RULE 2: GST Rate Validity
        if gst_rate is not None:
            item_type = parameters.get("item_type")
            is_valid, severity, message, action = rules.rule_gst_rate_validity_india(gst_rate, item_type)
            result.add_issue("GST_RATE_VALIDITY", is_valid, severity, message, action)
        
        # RULE 3: Reverse Charge Mechanism
        if intent in ["CREATE_INVOICE", "CREATE_PAYMENT"] and amount > 0:
            is_valid, severity, message, action = rules.rule_reverse_charge_applicable(amount, supplier_gstin)
            result.add_issue("REVERSE_CHARGE_APPLICABLE", is_valid, severity, message, action)
        
        # RULE 4: TDS on Contractor/Professional Payments
        if intent == "CREATE_PAYMENT" and payment_type in ["CONTRACTOR", "PROFESSIONAL"]:
            aggregate = context.get("aggregate_annual_to_party", 0)
            is_valid, severity, message, action = rules.rule_tds_contractor_payment(amount, payment_type, aggregate)
            result.add_issue("TDS_CONTRACTOR_PAYMENT", is_valid, severity, message, action)
        
        # RULE 5: TDS on Cash Withdrawals
        if payment_type == "CASH_WITHDRAWAL":
            annual_aggregate = context.get("annual_cash_withdrawals", 0)
            is_valid, severity, message, action = rules.rule_tds_cash_withdrawal(amount, annual_aggregate)
            result.add_issue("TDS_CASH_WITHDRAWAL", is_valid, severity, message, action)
        
        # RULE 6: GSTR Filing Deadline Warning
        is_valid, severity, message, action = rules.rule_gstr_filing_deadline_warning()
        result.add_issue("GSTR_FILING_DEADLINE", is_valid, severity, message, action)
        
        # RULE 7: Duplicate Invoice Check
        if intent == "CREATE_INVOICE" and customer and amount > 0:
            gst_amount = amount * (gst_rate / 100) if gst_rate else 0
            is_valid, severity, message, action = rules.rule_duplicate_invoice_gst(
                customer, amount, gst_amount, invoice_date
            )
            result.add_issue("DUPLICATE_INVOICE", is_valid, severity, message, action)
        
        # RULE 8: MSME Form 1 Compliance
        if context.get("is_msme_supplier") and context.get("days_unpaid", 0) > 0:
            is_valid, severity, message, action = rules.rule_msme_form1_compliance(
                customer or "Supplier",
                amount,
                context.get("days_unpaid", 0)
            )
            result.add_issue("MSME_FORM1_COMPLIANCE", is_valid, severity, message, action)
        
        # RULE 9: E-Invoicing Mandatory
        if intent == "CREATE_INVOICE" and turnover > 0:
            is_valid, severity, message, action = rules.rule_e_invoicing_mandatory(turnover, amount)
            result.add_issue("E_INVOICING_MANDATORY", is_valid, severity, message, action)
        
        # RULE 10: E-Way Bill Required
        if intent == "CREATE_INVOICE" and context.get("is_goods", False):
            is_valid, severity, message, action = rules.rule_e_way_bill_required(amount, True)
            result.add_issue("E_WAY_BILL_REQUIRED", is_valid, severity, message, action)
        
        # RULE 21: Annual Turnover Limit Check
        if ytd_turnover > 0 and months_elapsed > 0:
            is_valid, severity, message, action = rules.rule_annual_turnover_limit_check(ytd_turnover, months_elapsed)
            result.add_issue("ANNUAL_TURNOVER_LIMIT", is_valid, severity, message, action)
        
        logger.info(f"Validation complete: {result.get_summary()}")
        return result

# Global instance
_engine: IndiaValidationEngine = None

def get_validation_engine() -> IndiaValidationEngine:
    """Get or create global validation engine"""
    global _engine
    if _engine is None:
        _engine = IndiaValidationEngine()
    return _engine

def validate_india(parameters: Dict[str, Any], intent: str, context: Dict[str, Any] = None) -> ValidationResult:
    """
    Convenience function for Indian validation.
    
    Args:
        parameters: Extracted parameters
        intent: User intent
        context: Additional context
        
    Returns:
        ValidationResult
    """
    engine = get_validation_engine()
    return engine.validate_india(parameters, intent, context)
