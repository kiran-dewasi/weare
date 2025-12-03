# K24 AI Agent - Error Handler with Retry Logic
# ===============================================
# Implements exponential backoff, retry policies, and fallback strategies

from typing import Dict, Any, Callable, Optional, TypeVar, List
import logging
import time
import functools
from datetime import datetime
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    retry_if_exception_type,
    RetryError
)
from backend.agent_errors import (
    AgentError,
    K24ErrorCode,
    ErrorSeverity,
    ErrorCategory,
    create_error
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior"""
    
    # Retry policies by error code
    POLICIES = {
        K24ErrorCode.GEMINI_API_TIMEOUT: {
            "max_attempts": 3,
            "wait_strategy": "exponential",
            "wait_multiplier": 1,
            "wait_max": 10,
            "fallback": "use_template"
        },
        K24ErrorCode.GEMINI_API_ERROR: {
            "max_attempts": 2,
            "wait_strategy": "exponential",
            "wait_multiplier": 2,
            "wait_max": 8,
            "fallback": "use_template"
        },
        K24ErrorCode.TALLY_CONNECTION_FAILED: {
            "max_attempts": 2,
            "wait_strategy": "fixed",
            "wait_seconds": 3,
            "fallback": "queue_for_later"
        },
        K24ErrorCode.XML_VALIDATION_FAILED: {
            "max_attempts": 2,
            "wait_strategy": "none",
            "fallback": "manual_form"
        },
        K24ErrorCode.LEDGER_NOT_FOUND: {
            "max_attempts": 1,
            "wait_strategy": "none",
            "fallback": "suggest_alternatives"
        },
    }
    
    @classmethod
    def get_policy(cls, error_code: K24ErrorCode) -> Dict[str, Any]:
        """Get retry policy for error code"""
        return cls.POLICIES.get(error_code, {
            "max_attempts": 1,
            "wait_strategy": "none",
            "fallback": None
        })


class AgentErrorHandler:
    """
    Centralized error handling with retry logic and fallbacks.
    Tracks retry attempts and provides structured error responses.
    """
    
    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.fallback_handlers: Dict[str, Callable] = {}
    
    def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any] = None,
        retry_count: int = 0
    ) -> AgentError:
        """
        Handle an error and convert to AgentError.
        Determines if retry is possible.
        """
        context = context or {}
        
        # Classify the error
        error_code = self._classify_error(error)
        
        # Get retry policy
        policy = RetryConfig.get_policy(error_code)
        max_retries = policy.get("max_attempts", 1) - 1  # -1 because first attempt doesn't count
        
        # Determine if retryable
        is_retryable = retry_count < max_retries
        
        # Get suggestions
        suggestions = self._get_error_suggestions(error_code, context)
        
        # Create structured error
        agent_error = create_error(
            error_code=error_code,
            message=str(error),
            suggestions=suggestions,
            context=context,
            retry_count=retry_count
        )
        
        # Log error
        logger.error(
            f"Error handled: {error_code.value} (retry {retry_count}/{max_retries})",
            extra={"error_details": agent_error.to_dict()}
        )
        
        return agent_error
    
    def _classify_error(self, error: Exception) -> K24ErrorCode:
        """Classify exception into K24ErrorCode"""
        
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        # Gemini API errors
        if "timeout" in error_message or "timed out" in error_message:
            return K24ErrorCode.GEMINI_API_TIMEOUT
        
        if any(word in error_message for word in ["api", "gemini", "rate limit"]):
            return K24ErrorCode.GEMINI_API_ERROR
        
        # Tally errors
        if any(word in error_message for word in ["tally", "connection", "localhost:9000"]):
            return K24ErrorCode.TALLY_CONNECTION_FAILED
        
        # XML errors
        if any(word in error_message for word in ["xml", "parse", "malformed"]):
            return K24ErrorCode.XML_VALIDATION_FAILED
        
        # Ledger errors
        if "ledger" in error_message and "not found" in error_message:
            return K24ErrorCode.LEDGER_NOT_FOUND
        
        # Default
        return K24ErrorCode.UNKNOWN_ERROR
    
    def _get_error_suggestions(self, error_code: K24ErrorCode, context: Dict[str, Any]) -> List[str]:
        """Get actionable suggestions for an error"""
        
        suggestions_map = {
            K24ErrorCode.GEMINI_API_TIMEOUT: [
                "The AI is taking longer than expected. Retrying automatically...",
                "If this persists, try again in a few minutes"
            ],
            K24ErrorCode.GEMINI_API_ERROR: [
                "There's a temporary issue with the AI service",
                "Retrying with fallback method..."
            ],
            K24ErrorCode.TALLY_CONNECTION_FAILED: [
                "Make sure Tally is running",
                "Check that Tally is on port 9000",
                "Verify network connection to Tally",
                "Try restarting Tally"
            ],
            K24ErrorCode.XML_VALIDATION_FAILED: [
                "The transaction data couldn't be formatted correctly",
                "Try rephrasing your request",
                "Use the manual form instead"
            ],
            K24ErrorCode.LEDGER_NOT_FOUND: [
                "Check the party name spelling",
                "Create the ledger in Tally first",
                "Use exact name from Tally"
            ],
            K24ErrorCode.AMOUNT_OUT_OF_RANGE: [
                "Enter a valid positive amount",
                f"Maximum allowed: ₹{context.get('max_limit', 1000000):,.2f}"
            ],
        }
        
        return suggestions_map.get(error_code, ["Please try again or contact support"])
    
    def with_retry(
        self,
        func: Callable[..., T],
        error_code: K24ErrorCode,
        context: Dict[str, Any] = None
    ) -> Callable[..., T]:
        """
        Decorator factory to add retry logic to a function.
        """
        policy = RetryConfig.get_policy(error_code)
        max_attempts = policy.get("max_attempts", 1)
        wait_strategy = policy.get("wait_strategy", "none")
        
        # Build retry decorator
        retry_kwargs = {
            "stop": stop_after_attempt(max_attempts),
            "reraise": True
        }
        
        if wait_strategy == "exponential":
            retry_kwargs["wait"] = wait_exponential(
                multiplier=policy.get("wait_multiplier", 1),
                max=policy.get("wait_max", 10)
            )
        elif wait_strategy == "fixed":
            retry_kwargs["wait"] = wait_fixed(policy.get("wait_seconds", 2))
        
        retry_decorator = retry(**retry_kwargs)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return retry_decorator(func)(*args, **kwargs)
            except RetryError as e:
                # All retries exhausted
                logger.error(f"All retries exhausted for {func.__name__}")
                raise e.last_attempt.exception()
        
        return wrapper


class FallbackStrategies:
    """
    Fallback strategies when primary methods fail.
    """
    
    @staticmethod
    def use_template_xml(voucher_type: str, params: Dict[str, Any]) -> str:
        """
        Generate XML using template when Gemini fails.
        Simple but reliable fallback.
        """
        from backend.tally_xml_builder import build_voucher_xml
        
        logger.info("Using template-based XML generation as fallback")
        
        try:
            # Use existing XML builder
            xml = build_voucher_xml(
                voucher_type=voucher_type,
                party_name=params.get("party_name"),
                amount=params.get("amount"),
                date=params.get("date"),
                narration=params.get("narration", ""),
                company_name=params.get("company_name")
            )
            return xml
        except Exception as e:
            logger.error(f"Template XML generation also failed: {e}")
            raise
    
    @staticmethod
    def queue_for_later(transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Queue transaction for later processing when Tally is unavailable.
        """
        logger.info("Queueing transaction for later processing")
        
        # TODO: Implement actual queue (Redis, database, etc.)
        # For now, just return a pending status
        
        return {
            "status": "QUEUED",
            "message": "Tally is currently unavailable. Transaction will be processed when connection is restored.",
            "transaction_id": transaction_data.get("transaction_id"),
            "queued_at": datetime.utcnow().isoformat() + "Z"
        }
    
    @staticmethod
    def suggest_alternatives(query: str, available_options: List[str]) -> Dict[str, Any]:
        """
        Suggest alternatives when exact match not found.
        Uses fuzzy matching.
        """
        from difflib import get_close_matches
        
        # Find close matches
        matches = get_close_matches(query, available_options, n=5, cutoff=0.6)
        
        return {
            "status": "NEEDS_CLARIFICATION",
            "message": f"'{query}' not found",
            "suggestions": matches,
            "action_required": "select_from_suggestions"
        }
    
    @staticmethod
    def manual_form_fallback(intent: str, partial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return data structure for manual form entry.
        """
        return {
            "status": "MANUAL_ENTRY_REQUIRED",
            "message": "Automatic processing failed. Please use manual entry form.",
            "intent": intent,
            "pre_filled_data": partial_data,
            "form_url": f"/vouchers/new/{intent.replace('create_', '')}"
        }


def retry_with_backoff(
    error_code: K24ErrorCode,
    max_attempts: int = None
):
    """
    Decorator to add retry logic with backoff to any function.
    
    Usage:
        @retry_with_backoff(K24ErrorCode.GEMINI_API_TIMEOUT)
        def my_function():
            # ... code that might fail
    """
    policy = RetryConfig.get_policy(error_code)
    attempts = max_attempts or policy.get("max_attempts", 3)
    wait_strategy = policy.get("wait_strategy", "exponential")
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == attempts - 1:
                        # Last attempt failed
                        logger.error(f"{func.__name__} failed after {attempts} attempts: {e}")
                        raise
                    
                    # Calculate wait time
                    if wait_strategy == "exponential":
                        wait_time = min(2 ** attempt, policy.get("wait_max", 10))
                    elif wait_strategy == "fixed":
                        wait_time = policy.get("wait_seconds", 2)
                    else:
                        wait_time = 0
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{attempts} failed. "
                        f"Retrying in {wait_time}s... Error: {e}"
                    )
                    
                    if wait_time > 0:
                        time.sleep(wait_time)
        
        return wrapper
    return decorator


# Example usage
if __name__ == "__main__":
    handler = AgentErrorHandler()
    
    # Simulate handling different errors
    test_errors = [
        (Exception("Gemini API timeout"), {"operation": "xml_generation"}),
        (Exception("Tally connection refused"), {"tally_url": "localhost:9000"}),
        (Exception("Ledger 'ABC Corp' not found"), {"party_name": "ABC Corp"}),
    ]
    
    for error, context in test_errors:
        agent_error = handler.handle_error(error, context, retry_count=0)
        print(f"\nError: {error}")
        print(f"Classified as: {agent_error.code.value}")
        print(f"Suggestions: {agent_error.suggestions}")
        print(f"Retryable: {agent_error.retry_available}")
