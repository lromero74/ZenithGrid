"""Donation tracking models."""

from app.utils.timeutil import utcnow

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Donation(Base):
    """Tracks individual donations with self-report → admin confirm workflow."""
    __tablename__ = "donations"
    __table_args__ = {'schema': 'reporting'}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth.users.id"), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    payment_method = Column(String(50), nullable=False)
    tx_reference = Column(String(255), nullable=True)
    donor_name = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    confirmed_by = Column(Integer, ForeignKey("auth.users.id"), nullable=True)
    donation_date = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", foreign_keys=[user_id])
