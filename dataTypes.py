from __future__ import annotations

import datetime
from typing import List
from sqlalchemy import String, Column, Integer, DateTime, create_engine, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, Mapped, relationship, mapped_column
from telegram import User

Base = declarative_base()



class TelegramUser(Base):
    __tablename__ = "user"
    id: Mapped[int] = Column(Integer, primary_key=True)
    username: Mapped[str | None] = Column(String)
    first_name: Mapped[str] = Column(String)
    last_name: Mapped[str | None] = Column(String)
    language_code: Mapped[str | None] = Column(String)
    last_seen: Mapped[datetime.datetime] = Column(DateTime)
    birthdays: Mapped[List["Birthday"]] = relationship("Birthday", back_populates="user")
    monthly: Mapped[bool] = Column(Boolean, default=True)
    weekly: Mapped[bool] = Column(Boolean, default=True)
    dailiy: Mapped[bool] = Column(Boolean, default=True)


    @staticmethod
    def from_user(user: User) -> TelegramUser:
        return TelegramUser(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            last_seen=datetime.datetime.now(),
            monthly = True,
            weekly = True,
            dailiy = True,
        )

    def update_user(self, user: User) -> None:
        self.username = user.username
        self.first_name = user.first_name
        self.last_name = user.last_name
        self.language_code = user.language_code
        self.last_seen = datetime.datetime.now()


    def __repr__(self) -> str:
        return f"<TelegramUser(id={self.id}, username={self.username}, first_name={self.first_name}, last_name={self.last_name}, language_code={self.language_code}, last_seen={self.last_seen})>"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} (@{self.username})"




class Birthday(Base):
    __tablename__ = "birthday"
    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = Column(String)
    last_name: Mapped[str] = Column(String)
    birth: Mapped[datetime.datetime] = Column(DateTime)
    user_id: Mapped[int] = Column(Integer, ForeignKey("user.id"))
    user: Mapped["TelegramUser"] = relationship("TelegramUser", back_populates="birthdays")
    is_anniversary: Mapped[bool] = Column(Boolean, default=False)
