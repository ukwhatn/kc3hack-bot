from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, String, JSON, BigInteger, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text, true as sql_true, false as sql_false

from .connection import Base


class UserSessionStorage(Base):
    __tablename__ = "user_session_storage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(BigInteger)

    data: Mapped[dict] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    short_name: Mapped[str] = mapped_column(String(255), nullable=False)

    is_disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=sql_false
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    participants: Mapped[list["Participant"]] = relationship(
        "Participant", back_populates="group"
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)

    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id"), nullable=False
    )
    group: Mapped[Group] = relationship("Group", back_populates="participants")

    github_user_name: Mapped[str] = mapped_column(String(255), nullable=False)

    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class VoiceChatLog(Base):
    __tablename__ = "voice_chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    team_id: Mapped[str] = mapped_column(String(255), nullable=False)

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class TextChatLog(Base):
    __tablename__ = "text_chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    team_id: Mapped[str] = mapped_column(String(255), nullable=False)

    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
