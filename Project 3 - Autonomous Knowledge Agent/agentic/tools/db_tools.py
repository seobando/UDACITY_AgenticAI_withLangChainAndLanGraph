"""Database query tools for accessing CultPass and UDA-Hub databases."""

import os
import json
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
            JSON string with structured user information.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            user = None
            if user_id:
                user = session.query(cultpass.User).filter_by(user_id=user_id).first()
            elif email:
                user = session.query(cultpass.User).filter_by(email=email).first()
            else:
                return json.dumps({
                    "success": False,
                    "error": "Please provide either user_id or email."
                })
            
            if not user:
                return json.dumps({
                    "success": False,
                    "error": f"User not found with {'user_id' if user_id else 'email'}: {user_id or email}"
                })
            
            # Build structured response
            result = {
                "success": True,
                "user": {
                    "user_id": user.user_id,
                    "full_name": user.full_name,
                    "email": user.email,
                    "is_blocked": user.is_blocked,
                }
            }
            
            if user.subscription:
                sub = user.subscription
                result["subscription"] = {
                    "tier": sub.tier,
                    "status": sub.status,
                    "monthly_quota": sub.monthly_quota,
                    "started_at": str(sub.started_at) if sub.started_at else None,
                }
            
            if user.reservations:
                active_reservations = [r for r in user.reservations if r.status == "reserved"]
                result["reservations"] = {
                    "total": len(user.reservations),
                    "active": len(active_reservations),
                }
            
            return json.dumps(result)
    
    return lookup_user


def create_subscription_lookup_tool():
    """Create a tool to lookup subscription information."""
    
    @tool
    def lookup_subscription(user_id: str) -> str:
        """Lookup subscription details for a user.
        
        Args:
            user_id: The user ID to lookup subscription for.
        
        Returns:
            JSON string with structured subscription information.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            user = session.query(cultpass.User).filter_by(user_id=user_id).first()
            
            if not user:
                return json.dumps({
                    "success": False,
                    "error": f"User not found: {user_id}"
                })
            
            if not user.subscription:
                return json.dumps({
                    "success": False,
                    "error": f"User {user_id} has no subscription."
                })
            
            sub = user.subscription
            return json.dumps({
                "success": True,
                "user_id": user_id,
                "user_name": user.full_name,
                "subscription": {
                    "tier": sub.tier,
                    "status": sub.status,
                    "monthly_quota": sub.monthly_quota,
                    "started_at": str(sub.started_at) if sub.started_at else None,
                }
            })
    
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
            JSON string with structured list of reservations.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            user = session.query(cultpass.User).filter_by(user_id=user_id).first()
            
            if not user:
                return json.dumps({
                    "success": False,
                    "error": f"User not found: {user_id}"
                })
            
            reservations = user.reservations
            if status:
                reservations = [r for r in reservations if r.status == status]
            
            if not reservations:
                return json.dumps({
                    "success": True,
                    "user_id": user_id,
                    "user_name": user.full_name,
                    "filter_status": status,
                    "reservations": []
                })
            
            reservations_list = []
            for res in reservations:
                exp = session.query(cultpass.Experience).filter_by(
                    experience_id=res.experience_id
                ).first()
                reservations_list.append({
                    "reservation_id": res.reservation_id,
                    "experience_id": res.experience_id,
                    "experience_title": exp.title if exp else "Unknown Experience",
                    "status": res.status,
                    "created_at": str(res.created_at) if res.created_at else None,
                })
            
            return json.dumps({
                "success": True,
                "user_id": user_id,
                "user_name": user.full_name,
                "filter_status": status,
                "reservations": reservations_list
            })
    
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
            JSON string with structured experience information.
        """
        engine = _get_cultpass_engine()
        
        with get_session(engine) as session:
            if experience_id:
                exp = session.query(cultpass.Experience).filter_by(
                    experience_id=experience_id
                ).first()
                
                if not exp:
                    return json.dumps({
                        "success": False,
                        "error": f"Experience not found: {experience_id}"
                    })
                
                return json.dumps({
                    "success": True,
                    "experience": {
                        "experience_id": exp.experience_id,
                        "title": exp.title,
                        "description": exp.description,
                        "location": exp.location,
                        "when": str(exp.when) if exp.when else None,
                        "slots_available": exp.slots_available,
                        "is_premium": exp.is_premium,
                    }
                })
            
            elif title_search:
                exps = session.query(cultpass.Experience).filter(
                    cultpass.Experience.title.ilike(f"%{title_search}%")
                ).all()
                
                if not exps:
                    return json.dumps({
                        "success": False,
                        "error": f"No experiences found matching: {title_search}"
                    })
                
                experiences_list = []
                for exp in exps:
                    experiences_list.append({
                        "experience_id": exp.experience_id,
                        "title": exp.title,
                        "description": exp.description,
                        "location": exp.location,
                        "when": str(exp.when) if exp.when else None,
                        "slots_available": exp.slots_available,
                        "is_premium": exp.is_premium,
                    })
                
                return json.dumps({
                    "success": True,
                    "search_term": title_search,
                    "count": len(experiences_list),
                    "experiences": experiences_list
                })
            
            else:
                return json.dumps({
                    "success": False,
                    "error": "Please provide either experience_id or title_search."
                })
    
    return lookup_experience

