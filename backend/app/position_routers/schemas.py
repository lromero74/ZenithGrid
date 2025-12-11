"""
Position Router Schemas

Shared request/response models for position router modules.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AddFundsRequest(BaseModel):
    btc_amount: float


class UpdateNotesRequest(BaseModel):
    notes: str


class LimitCloseRequest(BaseModel):
    limit_price: float
    time_in_force: str = "gtc"  # "gtc" (Good 'til Cancelled) or "gtd" (Good 'til Date)
    end_time: Optional[datetime] = None  # Required for GTD orders - ISO 8601 format


class UpdateLimitCloseRequest(BaseModel):
    new_limit_price: float
    time_in_force: Optional[str] = None  # If provided, update time_in_force
    end_time: Optional[datetime] = None  # If GTD, new end_time
