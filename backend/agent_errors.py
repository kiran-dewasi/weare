# K24 AI Agent - Error Types and Handling System
# ==============================================

from enum import Enum
from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime


class ErrorSeverity(Enum):
    """Error severity levels for K24 Agent"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of errors in K24 system"""
    VALIDATION = "validation"  # User input issues
    SYSTEM = "system"  # Our infrastructure issues
    FINANCIAL = "financial"  # High-risk financial operations
    TALLY_CONNECTION = "tally_connection"  # Tally connectivity issues
    GEMINI_API = "gemini_api"  # Gemini API issues


class K24ErrorCode(Enum):
    """Comprehensive error codes for K24 operations"""
    
    # Validation Errors (User's fault, fixable)
    LEDGER_NOT_FOUND = "LEDGER_NOT_FOUND"
    AMOUNT_OUT_OF_RANGE = "AMOUNT_OUT_OF_RANGE"
    INVALID_TAX_CODE = "INVALID_TAX_CODE"
    INVALID_DATE_FORMAT = "INVALID_DATE_FORMAT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_VOUCHER_TYPE = "INVALID_VOUCHER_TYPE"
    UNKNOWN_INTENT = "UNKNOWN_INTENT"
    
    # System Errors (Our fault, needs investigation)
    GEMINI_API_TIMEOUT = "GEMINI_API_TIMEOUT"
    GEMINI_API_ERROR = "GEMINI_API_ERROR"
    TALLY_CONNECTION_FAILED = "TALLY_CONNECTION_FAILED"
    XML_VALIDATION_FAILED = "XML_VALIDATION_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    
    # Financial Errors (High risk)
    DUPLICATE_TRANSACTION_DETECTED = "DUPLICATE_TRANSACTION_DETECTED"
    CREDIT_LIMIT_EXCEEDED = "CREDIT_LIMIT_EXCEEDED"
    AMOUNT_SUSPICIOUSLY_LARGE = "AMOUNT_SUSPICIOUSLY_LARGE"
    UNAUTHORIZED_TRANSACTION = "UNAUTHORIZED_TRANSACTION"


@dataclass
class AgentError:
    """Structured error object for agent operations"""
    code: K24ErrorCode
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    suggestions: List[str]
    retry_available: bool
    retry_count: int = 0
    max_retries: int = 2
    timestamp: str = None
    context: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
        if self.context is None:
            self.context = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API responses"""
        return {
            "status": "FAILED",
            "error_code": self.code.value,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "suggestions": self.suggestions,
            "retry_available": self.retry_available,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "timestamp": self.timestamp,
            "context": self.context
        }


# Error Configuration Map
ERROR_CONFIG: Dict[K24ErrorCode, Dict[str, Any]] = {
    K24ErrorCode.LEDGER_NOT_FOUND: {
        "severity": ErrorSeverity.MEDIUM,
        "category": ErrorCategory.VALIDATION,
        "retry_available": True,
        "max_retries": 1,
        "default_message": "Ledger not found in Tally"
    },
    K24ErrorCode.AMOUNT_OUT_OF_RANGE: {
        "severity": ErrorSeverity.MEDIUM,
        "category": ErrorCategory.VALIDATION,
        "retry_available": True,
        "max_retries": 2,
        "default_message": "Amount is outside acceptable range"
    },
    K24ErrorCode.INVALID_TAX_CODE: {
        "severity": ErrorSeverity.HIGH,
        "category": ErrorCategory.VALIDATION,
        "retry_available": True,
        "max_retries": 2,
        "default_message": "Invalid GST/tax code provided"
    },
    K24ErrorCode.UNKNOWN_INTENT: {
        "severity": ErrorSeverity.LOW,
        "category": ErrorCategory.VALIDATION,
        "retry_available": False,
        "max_retries": 0,
        "default_message": "Could not understand user intent"
    },
    K24ErrorCode.GEMINI_API_TIMEOUT: {
        "severity": ErrorSeverity.HIGH,
        "category": ErrorCategory.GEMINI_API,
        "retry_available": True,
        "max_retries": 3,
        "default_message": "Gemini API request timed out"
    },
    K24ErrorCode.TALLY_CONNECTION_FAILED: {
        "severity": ErrorSeverity.CRITICAL,
        "category": ErrorCategory.TALLY_CONNECTION,
        "retry_available": True,
        "max_retries": 2,
        "default_message": "Failed to connect to Tally"
    },
    K24ErrorCode.XML_VALIDATION_FAILED: {
        "severity": ErrorSeverity.CRITICAL,
        "category": ErrorCategory.SYSTEM,
        "retry_available": True,
        "max_retries": 2,
        "default_message": "Generated XML failed validation"
    },
    K24ErrorCode.DUPLICATE_TRANSACTION_DETECTED: {
        "severity": ErrorSeverity.CRITICAL,
        "category": ErrorCategory.FINANCIAL,
        "retry_available": False,
        "max_retries": 0,
        "default_message": "Duplicate transaction detected"
    },
    K24ErrorCode.CREDIT_LIMIT_EXCEEDED: {
        "severity": ErrorSeverity.HIGH,
        "category": ErrorCategory.FINANCIAL,
        "retry_available": False,
        "max_retries": 0,
        "default_message": "Customer credit limit exceeded"
    },
    K24ErrorCode.AMOUNT_SUSPICIOUSLY_LARGE: {
        "severity": ErrorSeverity.HIGH,
        "category": ErrorCategory.FINANCIAL,
        "retry_available": True,
        "max_retries": 1,
        "default_message": "Transaction amount is unusually large"
    },
}


def create_error(
    error_code: K24ErrorCode,
    message: str = None,
    suggestions: List[str] = None,
    context: Dict[str, Any] = None,
    retry_count: int = 0
) -> AgentError:
    """Factory function to create standardized errors"""
    
    config = ERROR_CONFIG.get(error_code, {
        "severity": ErrorSeverity.MEDIUM,
        "category": ErrorCategory.SYSTEM,
        "retry_available": False,
        "max_retries": 0,
        "default_message": "An error occurred"
    })
    
    return AgentError(
        code=error_code,
        severity=config["severity"],
        category=config["category"],
        message=message or config["default_message"],
        suggestions=suggestions or [],
        retry_available=config["retry_available"],
        retry_count=retry_count,
        max_retries=config["max_retries"],
        context=context or {}
    )
