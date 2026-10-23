"""Registration and login."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.user import UserCreate


def register_user(db: Session, data: UserCreate) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise ConflictError("Email is already registered")

    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=UserRole.GUEST,  # self-registration never grants admin
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two simultaneous registrations with the same email: the UNIQUE constraint decides
        db.rollback()
        raise ConflictError("Email is already registered") from None
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)  # same timing as a real check
        raise AuthenticationError("Incorrect email or password")
    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Incorrect email or password")
    return user


def login(db: Session, email: str, password: str) -> str:
    user = authenticate(db, email, password)
    return create_access_token(user.id)
