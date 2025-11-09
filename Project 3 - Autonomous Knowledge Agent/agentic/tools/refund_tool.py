"""Refund tool for processing refunds (requires approval)."""

from langchain_core.tools import tool
from typing import Optional


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
            Status of the refund request.
        """
        # In a real system, this would integrate with payment processing
        # For now, this is a simulation that requires approval
        
        if not reason:
            return (
                "Error: Refund reason is required. "
                "Refunds can only be processed with approval from support lead. "
                "Please escalate this request."
            )
        
        # Check if this is within the refund policy
        refund_policy_note = (
            "Note: Refunds are typically only available for cancelled subscriptions "
            "within 7 days of signup. This request requires manual approval."
        )
        
        return (
            f"Refund request submitted for user {user_id}:\n"
            f"- Reason: {reason}\n"
            f"- Amount: {amount if amount else 'To be calculated'}\n"
            f"- Status: Pending approval from support lead\n\n"
            f"{refund_policy_note}\n\n"
            f"Action required: This refund request has been logged and requires "
            f"manual review and approval before processing."
        )
    
    return process_refund

