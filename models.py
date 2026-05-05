"""Database models for BOWA production system."""

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    memory = relationship("Memory", back_populates="user", uselist=False)
    trajectory = relationship("Trajectory", back_populates="user", uselist=False)
    execution_sessions = relationship("ExecutionSession", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    # Continuity fields
    last_topic = Column(String)
    last_goal = Column(String)
    last_session_summary = Column(String)
    last_active = Column(DateTime)

    # Personality fields
    consistency_score = Column(Float, default=0.5)
    prev_consistency_score = Column(Float, default=0.5)
    interaction_count = Column(Integer, default=0)

    # Pattern fields
    active_hours = Column(JSON)  # list of ints
    study_frequency = Column(Float, default=0)
    completion_rate = Column(Float, default=0.5)
    hesitation_patterns = Column(JSON)  # list of strings

    user = relationship("User", back_populates="memory")


class Trajectory(Base):
    __tablename__ = "trajectory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    current_stage = Column(String)
    current_index = Column(Integer, default=0)
    consistency_score = Column(Float, default=0.5)
    data = Column(JSON)  # full trajectory data

    user = relationship("User", back_populates="trajectory")


class ExecutionSession(Base):
    __tablename__ = "execution_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    task = Column(String)
    duration = Column(Integer, default=25)
    start_time = Column(DateTime)
    status = Column(String, default="running")  # running, completed, failed, expired
    active = Column(Boolean, default=True)

    user = relationship("User", back_populates="execution_sessions")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(Text)
    reason = Column(String)

    user = relationship("User", back_populates="notifications")


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    event_type = Column(String)  # session_start, session_complete, message_sent
    timestamp = Column(DateTime, default=datetime.utcnow)
    data = Column(JSON)  # additional data

    user = relationship("User")