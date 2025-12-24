"""Admin CLI: Create (mint) an API token.

Prints the raw token once. Only the SHA-256 hash is stored in the DB.

Usage examples:
  python scripts/create_token.py --email user@example.com --name laptop
  python scripts/create_token.py --alpha-user-id <uuid> --name ci
"""

import argparse
import asyncio
import os
import sys
from typing import Optional


def _ensure_import_path() -> None:
    server_root = os.path.dirname(os.path.dirname(__file__))
    if server_root not in sys.path:
        sys.path.insert(0, server_root)


async def _run(email: Optional[str], alpha_user_id: Optional[str], name: str) -> int:
    _ensure_import_path()

    from app.settings import DATABASE_URL
    from app import db

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is not set.")
        return 2

    await db.init_pool()
    try:
        if email:
            user = await db.get_or_create_alpha_user(email)
            alpha_user_id = user["id"]
        assert alpha_user_id

        raw_token, token_row = await db.create_api_token(alpha_user_id=alpha_user_id, name=name)

        print("alpha_user_id:", alpha_user_id)
        print("token_id:", token_row["id"])
        print("token_name:", token_row["name"])
        print("created_at:", token_row.get("created_at"))
        print("\nRAW_TOKEN (store this securely; it will not be shown again):")
        print(raw_token)
        return 0
    finally:
        await db.close_pool()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an API token (prints raw token once).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="Alpha user email (will be created if missing)")
    group.add_argument("--alpha-user-id", help="Alpha user id")
    parser.add_argument("--name", default="default", help="Token name/label")
    args = parser.parse_args()

    return asyncio.run(_run(args.email, args.alpha_user_id, args.name))


if __name__ == "__main__":
    raise SystemExit(main())
