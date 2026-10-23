"""Create an admin account, or promote an existing user to admin.

Registration through the API always creates guests, so the first admin is made here,
on the server, by someone who already has shell access:

    python -m app.scripts.create_admin --email admin@hotel.uz --full-name "Hotel Admin"

The password is asked interactively (or read from the ADMIN_PASSWORD env variable).
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.schemas.user import UserCreate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="Administrator")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is not None:
            user.role = UserRole.ADMIN
            db.commit()
            print(f"User {user.email} promoted to admin")
            return

        password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
        try:
            data = UserCreate(email=args.email, full_name=args.full_name, password=password)
        except ValueError as exc:
            sys.exit(f"Invalid input: {exc}")

        user = User(
            email=data.email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        print(f"Admin {user.email} created")


if __name__ == "__main__":
    main()
