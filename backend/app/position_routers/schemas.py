"""
Position Router Schemas

Shared request/response models for position router modules.
"""

from pydantic import BaseModel


class AddFundsRequest(BaseModel):
    btc_amount: float


class UpdateNotesRequest(BaseModel):
    notes: str


class LimitCloseRequest(BaseModel):
    limit_price: float


class UpdateLimitCloseRequest(BaseModel):
    new_limit_price: float
