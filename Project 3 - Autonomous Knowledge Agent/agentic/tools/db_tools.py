"""Database query tools for accessing CultPass and UDA-Hub databases."""

import os
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine
from langchain_core.tools import tool
from utils import get_session

# Import models
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))
from data.models import cultpass, udahub


def _get_cultpass_engine():
    """Get engine for CultPass external database."""
    db_path = os.path.join(os.path.dirname(__file__), "../../data/external/cultpass.db")
    return create_engine(f"sqlite:///{db_path}", echo=False)


def _get_udahub_engine():
    """Get engine for UDA-Hub core database."""
    db_path = os.path.join(os.path.dirname(__file__), "../../data/core/udahub.db")
    return create_engine(f"sqlite:///{db_path}", echo=False)


def create_user_lookup_tool():
    """Create a tool to lookup user information."""
    
    @tool
    def lookup_user(user_id: Optional[str] = None, email: Optional[str] = None) -> str:
        """Lookup user information from the CultPass database.
        
        Args:
            user_id: The user ID to lookup (e.g., 'a4ab87').
            email: The email address to lookup (e.g., 'alice@example.com').
        
        Returns:
            User information including name, email, blocked status, and subscription details.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            user = None
            if user_id:
                user = session.query(cultpass.User).filter_by(user_id=user_id).first()
            elif email:
                user = session.query(cultpass.User).filter_by(email=email).first()
            else:
                return "Error: Please provide either user_id or email."
            
            if not user:
                return f"User not found with {'user_id' if user_id else 'email'}: {user_id or email}"
            
            subscription_info = ""
            if user.subscription:
                sub = user.subscription
                subscription_info = (
                    f"\nSubscription: {sub.tier} tier, Status: {sub.status}, "
                    f"Monthly Quota: {sub.monthly_quota}"
                )
            
            reservations_info = ""
            if user.reservations:
                reservations_info = f"\nReservations: {len(user.reservations)} total"
                active = [r for r in user.reservations if r.status == "reserved"]
                if active:
                    reservations_info += f" ({len(active)} active)"
            
            return (
                f"User: {user.full_name} ({user.email})\n"
                f"User ID: {user.user_id}\n"
                f"Blocked: {user.is_blocked}"
                f"{subscription_info}"
                f"{reservations_info}"
            )
    
    return lookup_user


def create_subscription_lookup_tool():
    """Create a tool to lookup subscription information."""
    
    @tool
    def lookup_subscription(user_id: str) -> str:
        """Lookup subscription details for a user.
        
        Args:
            user_id: The user ID to lookup subscription for.
        
        Returns:
            Subscription information including tier, status, and quota.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            user = session.query(cultpass.User).filter_by(user_id=user_id).first()
            
            if not user:
                return f"User not found: {user_id}"
            
            if not user.subscription:
                return f"User {user_id} has no subscription."
            
            sub = user.subscription
            return (
                f"Subscription for {user.full_name}:\n"
                f"- Tier: {sub.tier}\n"
                f"- Status: {sub.status}\n"
                f"- Monthly Quota: {sub.monthly_quota}\n"
                f"- Started: {sub.started_at}"
            )
    
    return lookup_subscription


def create_reservation_lookup_tool():
    """Create a tool to lookup reservation information."""
    
    @tool
    def lookup_reservations(user_id: str, status: Optional[str] = None) -> str:
        """Lookup reservations for a user.
        
        Args:
            user_id: The user ID to lookup reservations for.
            status: Optional filter by status (e.g., 'reserved', 'cancelled', 'completed').
        
        Returns:
            List of reservations with details.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            user = session.query(cultpass.User).filter_by(user_id=user_id).first()
            
            if not user:
                return f"User not found: {user_id}"
            
            reservations = user.reservations
            if status:
                reservations = [r for r in reservations if r.status == status]
            
            if not reservations:
                status_text = f" with status '{status}'" if status else ""
                return f"No reservations found for user {user_id}{status_text}."
            
            result = f"Reservations for {user.full_name}:\n\n"
            for res in reservations:
                exp = session.query(cultpass.Experience).filter_by(
                    experience_id=res.experience_id
                ).first()
                exp_title = exp.title if exp else "Unknown Experience"
                result += (
                    f"- Reservation ID: {res.reservation_id}\n"
                    f"  Experience: {exp_title}\n"
                    f"  Status: {res.status}\n"
                    f"  Created: {res.created_at}\n\n"
                )
            
            return result
    
    return lookup_reservations


def create_experience_lookup_tool():
    """Create a tool to lookup experience information."""
    
    @tool
    def lookup_experience(experience_id: Optional[str] = None, title_search: Optional[str] = None) -> str:
        """Lookup experience information.
        
        Args:
            experience_id: The experience ID to lookup.
            title_search: Search for experiences by title (partial match).
        
        Returns:
            Experience information including title, description, location, and availability.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            if experience_id:
                exp = session.query(cultpass.Experience).filter_by(
                    experience_id=experience_id
                ).first()
                
                if not exp:
                    return f"Experience not found: {experience_id}"
                
                return (
                    f"Experience: {exp.title}\n"
                    f"Description: {exp.description}\n"
                    f"Location: {exp.location}\n"
                    f"When: {exp.when}\n"
                    f"Slots Available: {exp.slots_available}\n"
                    f"Premium: {exp.is_premium}"
                )
            
            elif title_search:
                exps = session.query(cultpass.Experience).filter(
                    cultpass.Experience.title.ilike(f"%{title_search}%")
                ).all()
                
                if not exps:
                    return f"No experiences found matching: {title_search}"
                
                result = f"Found {len(exps)} experience(s):\n\n"
                for exp in exps:
                    result += (
                        f"- {exp.title} (ID: {exp.experience_id})\n"
                        f"  Location: {exp.location}\n"
                        f"  When: {exp.when}\n"
                        f"  Slots: {exp.slots_available}\n"
                        f"  Premium: {exp.is_premium}\n\n"
                    )
                
                return result
            
            else:
                return "Error: Please provide either experience_id or title_search."
    
    return lookup_experience

