from sqlalchemy import select
from sqlalchemy.orm import Session

from transactagent_db.models import User


def find_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))
