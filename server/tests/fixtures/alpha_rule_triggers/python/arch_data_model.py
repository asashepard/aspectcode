# Should trigger: arch.data_model
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class User:
    """User data model - core domain entity"""
    id: int
    username: str
    email: str
    created_at: datetime
    is_active: bool = True
    profile_picture: Optional[str] = None

@dataclass
class Order:
    """Order data model - business entity"""
    order_id: str
    user_id: int
    items: List[str]
    total_amount: float
