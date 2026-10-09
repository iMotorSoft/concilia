"""Interactive local-only provisioning. No default account, password, or CLI secret."""
from __future__ import annotations

import asyncio
import getpass
import json

from backend.core.config import runtime_pool
from backend.core.security import password_hash
from backend.repositories.security import SecurityRepository
from backend.scripts.provision_dev import SECRET_PATH


async def create(email: str, encoded: str) -> None:
    pool = runtime_pool(SECRET_PATH)
    async with pool:
        await SecurityRepository(pool).create_first_admin(email, encoded)


def main() -> None:
    try:
        email = input("DEV first administrator email: ").strip().lower()
        if len(email) > 320 or email.count('@') != 1 or not all(email.split('@')):
            raise ValueError("Invalid email")
        password = getpass.getpass("Password (minimum 12 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords differ")
        encoded = password_hash(password)
        del password, confirmation
        asyncio.run(create(email, encoded))
        print(json.dumps({"first_admin": "CREATED", "password": "not logged"}))
    except Exception as exc:
        print(json.dumps({"first_admin": "FAIL", "error_type": type(exc).__name__, "details": "withheld"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
