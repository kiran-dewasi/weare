"""
K24 Orchestrator ("The Brain")
Coordinates Intent Recognition, Context Management, and Tally Integration.
Implements the "Competence over Magic" philosophy.
"""
import logging
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

from backend.intent_recognizer import IntentRecognizer, IntentType, Intent
from backend.context_manager import ContextManager, UserContext
from backend.tally_connector import TallyConnector

logger = logging.getLogger(__name__)

@dataclass
class DraftResponse:
    """Structured response for the frontend"""
    message: str
    type: str  # 'text', 'draft_voucher', 'report', 'clarification'
    data: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    
    def to_dict(self):
        return asdict(self)

class K24Orchestrator:
    def __init__(self, api_key: str, redis_url: str = "redis://localhost:6379"):
        self.intent_recognizer = IntentRecognizer(api_key)
        self.context_manager = ContextManager(redis_url=redis_url)
        # Tally connector for lookups (not writes, writes go through draft confirmation)
        self.tally = TallyConnector() 
        
    async def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """
        Main entry point: Process user message and return structured response.
        """
        # 1. Get Context
        context = self.context_manager.get_context(user_id)
        
        # 2. Recognize Intent
        intent = await self.intent_recognizer.recognize(message, context=context.to_dict())
        
        # 3. Route based on Intent
        response = await self._route_intent(user_id, intent, context)
        
        # 4. Update History
        self.context_manager.add_to_history(
            user_id=user_id,
            user_message=message,
            assistant_response=response.message,
            intent=intent.dict()
        )
        
        return response.to_dict()

    async def _route_intent(self, user_id: str, intent: Intent, context: UserContext) -> DraftResponse:
        """Route intent to specific handlers"""
        
        if intent.action in [IntentType.CREATE_SALE, IntentType.CREATE_PURCHASE]:
            return await self._handle_transaction_draft(user_id, intent, context)
            
        elif intent.action == IntentType.QUERY_DATA:
            return await self._handle_query(user_id, intent, context)
            
        elif intent.action == IntentType.UNKNOWN:
            return DraftResponse(
                message="Unclear. Try 'Sale to Sharma' or 'Show Revenue'.",
                type="clarification"
            )
            
        else:
            # Fallback for other intents
            return DraftResponse(
                message=f"Intent: {intent.action.value}. Workflow pending.",
                type="text"
            )

    async def _handle_transaction_draft(self, user_id: str, intent: Intent, context: UserContext) -> DraftResponse:
        """
        The "Slot Filler" Engine.
        Creates a draft voucher, filling missing slots from history/defaults.
        """
        # 1. Identify Party (The most critical slot)
        party_name = intent.entity
        if not party_name:
             return DraftResponse(
                message="Party name?",
                type="clarification",
                data={"missing_slot": "party"}
            )

        # 2. Context Lookup (The "Hook")
        # Check if we know this party from Tally or History
        # For MVP, we'll simulate a lookup or use what's provided
        # TODO: Implement fuzzy lookup against Tally Ledgers here
        
        # 3. Fill Defaults
        # If item is missing, check what they usually buy
        item = intent.parameters.get("item", "General Services") # Default
        amount = intent.parameters.get("amount", 0)
        
        # 4. Construct Draft
        draft_voucher = {
            "party_name": party_name,
            "voucher_type": "Sales" if intent.action == IntentType.CREATE_SALE else "Purchase",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "name": item,
                    "amount": amount,
                    "rate": intent.parameters.get("rate", 0),
                    "quantity": intent.parameters.get("quantity", 1)
                }
            ],
            "total_amount": amount
        }
        
        return DraftResponse(
            message=f"Draft: {draft_voucher['voucher_type']} for {party_name}. Save?",
            type="draft_voucher",
            data=draft_voucher
        )

    async def _handle_query(self, user_id: str, intent: Intent, context: UserContext) -> DraftResponse:
        """Handle data queries (Reports/Analytics)"""
        # For MVP, just acknowledge. Real implementation would query Tally/Pandas.
        return DraftResponse(
            message=f"Query: {intent.raw_query}. (Engine pending)",
            type="text"
        )
