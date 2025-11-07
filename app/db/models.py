# models.py
from __future__ import annotations
from typing import Optional, Dict, List
from datetime import datetime, date, time, timedelta

from sqlalchemy import (
    Integer, String, Text, Boolean, Date, TIMESTAMP, ForeignKey, Numeric,
    Index, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------- core ----------------

class Base(DeclarativeBase):
    pass

class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True)
    first_name: Mapped[Optional[str]] = mapped_column(Text)
    last_name: Mapped[Optional[str]] = mapped_column(Text)
    dob: Mapped[Optional[Date]] = mapped_column(Date)
    mrn: Mapped[Optional[str]] = mapped_column(Text)

    calls: Mapped[List["Call"]] = relationship(back_populates="patient")
    appointments: Mapped[List["Appointment"]] = relationship(back_populates="patient")

class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    patient_id: Mapped[Optional[int]] = mapped_column(ForeignKey("patients.id"))
    from_number: Mapped[Optional[str]] = mapped_column(String(32))

    intent: Mapped[Optional[str]] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    patient: Mapped[Optional[Patient]] = relationship(back_populates="calls")
    transcripts: Mapped[List["Transcript"]] = relationship(back_populates="call", cascade="all, delete-orphan")

class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # 'user' | 'assistant'
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    call: Mapped["Call"] = relationship(back_populates="transcripts")

class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # who / provenance
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    call_id: Mapped[Optional[int]] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"), nullable=True)

    # when
    starts_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), index=True)  # canonical, tz-aware
    duration_min: Mapped[int] = mapped_column(Integer, default=30, server_default="30")

    # clinic time zone (string like "America/Los_Angeles"); useful if you serve multiple clinics
    clinic_tz: Mapped[str] = mapped_column(String(64), default="America/Los_Angeles", server_default="America/Los_Angeles")

    # reason for appt
    reason: Mapped[Optional[str]] = mapped_column(Text)

    # bookkeeping
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # appt status
    status: Mapped[str] = mapped_column(Text, default="scheduled", nullable=False)

    patient: Mapped[Patient] = relationship(back_populates="appointments")

class RefillRequest(Base):
    __tablename__ = "refill_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), unique=True)
    drug_name: Mapped[Optional[str]] = mapped_column(Text)
    dosage: Mapped[Optional[str]] = mapped_column(Text)
    pharmacy: Mapped[Optional[str]] = mapped_column(Text)
    last_fill_date: Mapped[Optional[Date]] = mapped_column(Date)

class Analytics(Base):
    __tablename__ = "analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(Text)  # 'latency_ms','turns','words','interrupts'
    value: Mapped[float] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

