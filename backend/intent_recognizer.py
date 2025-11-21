"""
Intent Recognizer for KITTU
Uses Gemini to understand user intent from natural language.

Universal Design:
- Works with any accounting query
- Extensible intent system
- High accuracy with confidence scores
- Graceful fallback for ambiguous requests
"""
import json
import logging
from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Supported intent types"""
    RECONCILE_INVOICES = "reconcile_invoices"
    CREATE_PURCHASE = "create_purchase"
    CREATE_SALE = "create_sale"
    UPDATE_GSTIN = "update_gstin"
    UPDATE_LEDGER = "update_ledger"
    QUERY_DATA = "query_data"
    GENERATE_REPORT = "generate_report"
    UNKNOWN = "unknown"


class Intent(BaseModel):
    """
    Recognized user intent
    
    Attributes:
        action: Type of action to perform
        entity: Primary entity (party name, ledger name, etc.)
        parameters: Additional extracted parameters
        confidence: Confidence score (0.0-1.0)
        raw_query: Original user query
    """
    action: IntentType
    entity: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_query: str = ""
    
    @validator('confidence')
    def validate_confidence(cls, v):
        """Ensure confidence is between 0 and 1"""
        return max(0.0, min(1.0, v))
    
    def is_confident(self, threshold: float = 0.7) -> bool:
        """Check if confidence exceeds threshold"""
        return self.confidence >= threshold


class IntentRecognizer:
    """
    Recognize user intent from natural language using Gemini.
    
    Universal Features:
    - Handles any Tally-related query
    - Extracts structured parameters (amounts, dates, quantities)
    - Multiple language support (English, Hindi)
    - Confidence-based routing
    """
    
    # Intent examples for few-shot learning
    INTENT_EXAMPLES = {
        IntentType.RECONCILE_INVOICES: [
            "Reconcile invoices for Acme Corp",
            "Fix discrepancies for Vasudev Enterprises",
            "Check Ramesh Traders ledger for errors"
        ],
        IntentType.CREATE_PURCHASE: [
            "I bought 500 cumin bags from Vasudev Enterprises",
            "Purchase of 100 units from ABC Suppliers at Rs.2500",
            "Create purchase entry for Ramesh Traders"
        ],
        IntentType.CREATE_SALE: [
            "Sold 200 items to Customer ABC",
            "Create sale for Rs.50000 to XYZ Corp",
            "Sales entry for 100 units @500 each"
        ],
        IntentType.UPDATE_GSTIN: [
            "Update GSTIN for Vasudev Enterprises",
            "Add GST number for Acme Corp",
            "Change GSTIN to 12ABCDE1234F1Z5"
        ],
        IntentType.QUERY_DATA: [
            "What's my total revenue?",
            "Show me all parties with pending balances",
            "How much did Acme Corp purchase last month?"
        ],
        IntentType.GENERATE_REPORT: [
            "Generate P&L report",
            "Create balance sheet",
            "Show me party-wise outstanding report"
        ]
    }
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        """
        Initialize Intent Recognizer
        
        Args:
            api_key: Google AI API key
            model: Gemini model to use
        """
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            
            self.llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=0.1,  # Low temperature for consistent intent classification
                max_output_tokens=500,
                max_retries=1,  # Fail fast to use fallback
            )
            logger.info(f"Initialized IntentRecognizer with model {model}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            raise
    
    async def recognize(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Intent:
        """
        Recognize intent from user message
        
        Args:
            user_message: User's natural language input
            context: Optional conversation context
            
        Returns:
            Intent object with action, entity, parameters, and confidence
        """
        # Build prompt with context
        prompt = self._build_prompt(user_message, context)
        
        try:
            # Get LLM response
            response = await self.llm.ainvoke(prompt)
            
            # Parse JSON response
            result = self._parse_response(response.content, user_message)
            
            logger.info(
                f"Recognized intent: action={result.action}, "
                f"entity={result.entity}, confidence={result.confidence:.2f}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Intent recognition failed: {e}")
            # Return fallback intent using keyword matching
            return self._keyword_fallback(user_message)
    
    def _build_prompt(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build classification prompt"""
        
        # Extract context info
        company = context.get("company", "Unknown") if context else "Unknown"
        recent_history = context.get("conversation_history", [])[-2:] if context else []
        
        # Build examples
        examples_text = "\\n\\n".join([
            f"**{intent.value}:**\\n" + "\\n".join(f"  - {ex}" for ex in examples[:2])
            for intent, examples in self.INTENT_EXAMPLES.items()
        ])
        
        prompt = f"""You are an intent classifier for KITTU, an AI accounting assistant for TallyPrime.

USER MESSAGE: "{user_message}"

CONTEXT:
- Company: {company}
- Recent conversation: {json.dumps(recent_history, indent=2) if recent_history else "None"}

AVAILABLE INTENTS & EXAMPLES:
{examples_text}

TASK: Classify the user's intent and extract structured information.

EXTRACT:
1. **action**: One of the intent types above (e.g., "reconcile_invoices", "create_purchase", "query_data")
2. **entity**: Party/ledger name if mentioned (or null)
3. **parameters**: Extract any of these if present:
   - **quantity**: Number of items/units (e.g., "500 bags" → 500)
   - **amount**: Total money value (e.g., "₹150000" or "inr 3000" → 3000)
   - **rate**: Price per unit (e.g., "₹3000 per bag" or "each bag is of 50 kg" with "avg price inr 3000" → 3000)
   - **item**: Item/product name (e.g., "coriander", "cumin bags")
   - **date**: Transaction date if specified
   - **gstin**: GST number if mentioned
   - **unit_weight**: Weight per unit if mentioned (e.g., "50 kg")
   - Any other relevant details
   
   **IMPORTANT FOR PURCHASES/SALES**:
   - If user says "500 bags @ ₹3000 each" extract: quantity=500, rate=3000
   - If user says "total ₹150000" extract: amount=150000
   - If both quantity and rate are present, you can calculate amount
   - Extract the party/customer name as 'entity'
   
4. **confidence**: 0.0-1.0 based on:
   - 0.9-1.0: Very clear intent, all details present
   - 0.7-0.8: Clear intent, some details extracted
   - 0.5-0.6: Intent likely, few details
   - Below 0.5: Unclear/ambiguous

RESPONSE FORMAT (JSON only, no markdown):
{{
  "action": "create_sale",
  "entity": "prince enterprises",
  "parameters": {{"quantity": 500, "item": "coriander bags", "rate": 3000, "unit_weight": "50 kg"}},
  "confidence": 0.95
}}

Return ONLY valid JSON, nothing else."""
        
        return prompt
    
    def _parse_response(self, response_text: str, original_query: str) -> Intent:
        """Parse LLM JSON response into Intent object"""
        try:
            # Clean response (remove markdown code blocks if present)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                # Remove markdown code blocks
                lines = response_text.split("\\n")
                response_text = "\\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )
            
            # Parse JSON
            data = json.loads(response_text.strip())
            
            # Validate and normalize action
            action_str = data.get("action", "unknown")
            try:
                action = IntentType(action_str)
            except ValueError:
                logger.warning(f"Unknown intent type: {action_str}, using QUERY_DATA")
                action = IntentType.QUERY_DATA
            
            # Build Intent object
            intent = Intent(
                action=action,
                entity=data.get("entity"),
                parameters=data.get("parameters", {}),
                confidence=float(data.get("confidence", 0.5)),
                raw_query=original_query
            )
            
            return intent
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            
            # Fallback: Try keyword matching
            return self._keyword_fallback(original_query)
        
        except Exception as e:
            logger.error(f"Intent parsing error: {e}")
            return self._keyword_fallback(original_query)
    
    def _keyword_fallback(self, query: str) -> Intent:
        """Fallback keyword-based intent recognition with entity extraction"""
        from backend.entity_extractor import extract_entity_fallback, extract_parameters_fallback
        
        query_lower = query.lower()
        
        # Keyword mapping
        if any(word in query_lower for word in ["reconcile", "fix", "check", "discrepancy"]):
            action = IntentType.RECONCILE_INVOICES
            confidence = 0.6
        elif any(word in query_lower for word in ["bought", "purchase", "buy"]):
            action = IntentType.CREATE_PURCHASE
            confidence = 0.6
        elif any(word in query_lower for word in ["sold", "sale", "sell"]):
            action = IntentType.CREATE_SALE
            confidence = 0.6
        elif any(word in query_lower for word in ["gstin", "gst number", "tax id"]):
            action = IntentType.UPDATE_GSTIN
            confidence = 0.6
        elif any(word in query_lower for word in ["report", "generate", "show report"]):
            action = IntentType.GENERATE_REPORT
            confidence = 0.6
        else:
            action = IntentType.QUERY_DATA
            confidence = 0.4
        
        # Extract entity and parameters using regex fallback
        entity = extract_entity_fallback(query, action.value)
        parameters = extract_parameters_fallback(query)
        
        logger.info(f"Fallback keyword matching: {action.value} (confidence: {confidence}), entity: {entity}, params: {parameters}")
        
        return Intent(
            action=action,
            entity=entity,
            parameters=parameters,
            confidence=confidence,
            raw_query=query
        )
    
    def get_supported_intents(self) -> List[Dict[str, Any]]:
        """Get list of supported intents with examples"""
        return [
            {
                "intent": intent.value,
                "examples": examples,
                "description": self._get_intent_description(intent)
            }
            for intent, examples in self.INTENT_EXAMPLES.items()
        ]
    
    @staticmethod
    def _get_intent_description(intent: IntentType) -> str:
        """Get human-readable intent description"""
        descriptions = {
            IntentType.RECONCILE_INVOICES: "Find and fix discrepancies in invoices",
            IntentType.CREATE_PURCHASE: "Create a purchase voucher/entry",
            IntentType.CREATE_SALE: "Create a sales voucher/entry",
            IntentType.UPDATE_GSTIN: "Update GST number for a party",
            IntentType.UPDATE_LEDGER: "Update ledger information",
            IntentType.QUERY_DATA: "Ask questions about accounting data",
            IntentType.GENERATE_REPORT: "Generate accounting reports",
            IntentType.UNKNOWN: "Unrecognized request"
        }
        return descriptions.get(intent, "Unknown intent")
