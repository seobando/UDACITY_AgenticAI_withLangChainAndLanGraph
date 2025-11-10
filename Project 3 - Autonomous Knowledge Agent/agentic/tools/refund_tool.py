"""Refund tool for processing refunds (requires approval)."""

import json
from langchain_core.tools import tool
from typing import Optional
from datetime import datetime


def create_refund_tool():
    """Create a tool for processing refunds."""
    
    @tool
    def process_refund(
        user_id: str,
        amount: Optional[float] = None,
        reason: Optional[str] = None
    ) -> str:
        """Process a refund for a user. This requires approval from support lead.
        
        IMPORTANT: Only use this tool if explicitly approved by support lead.
        Refunds are typically only available for cancelled subscriptions within 7 days of signup.
        
        Args:
            user_id: The user ID requesting the refund.
            amount: The refund amount (optional, will be calculated if not provided).
            reason: The reason for the refund.
        
        Returns:
            JSON string with structured refund request status.
        """
        # In a real system, this would integrate with payment processing
        # For now, this is a simulation that requires approval
        
        if not reason:
            return json.dumps({
                "success": False,
                "error": "Refund reason is required. Refunds can only be processed with approval from support lead. Please escalate this request."
            })
        
        refund_id = f"REF-{hash(f'{user_id}{reason}{datetime.now()}') % 10000:04d}"
        
        return json.dumps({
            "success": True,
            "refund_request": {
                "refund_id": refund_id,
                "user_id": user_id,
                "amount": amount,
                "reason": reason,
                "status": "pending_approval",
                "submitted_at": datetime.now().isoformat(),
                "note": "Refunds are typically only available for cancelled subscriptions within 7 days of signup. This request requires manual approval."
            }
        })
    
    return process_refund

