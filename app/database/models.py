from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ChannelType(str, enum.Enum):
    SOURCE = "source"
    DESTINATION = "destination"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    type: Mapped[ChannelType] = mapped_column(Enum(ChannelType))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ForwardJob(Base):
    __tablename__ = "forward_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_channel_id: Mapped[int] = mapped_column(BigInteger)
    destination_channel_id: Mapped[int] = mapped_column(BigInteger)
    start_message_id: Mapped[int] = mapped_column(Integer)
    end_message_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    successful_messages: Mapped[int] = mapped_column(Integer, default=0)
    failed_messages: Mapped[int] = mapped_column(Integer, default=0)
    skipped_messages: Mapped[int] = mapped_column(Integer, default=0)
    last_processed_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages: Mapped[list["ForwardedMessage"]] = relationship(back_populates="job")


class ForwardedMessage(Base):
    __tablename__ = "forwarded_messages"
    __table_args__ = (
        UniqueConstraint(
            "source_channel_id",
            "source_message_id",
            "destination_channel_id",
            name="uq_forward_unique_message",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("forward_jobs.id"))
    source_channel_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(Integer)
    destination_channel_id: Mapped[int] = mapped_column(BigInteger)
    destination_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[MessageStatus] = mapped_column(Enum(MessageStatus))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[ForwardJob] = relationship(back_populates="messages")


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(Text)
