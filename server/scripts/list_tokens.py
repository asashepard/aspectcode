"""Admin CLI: List tokens for an alpha user.

Usage examples:
  python scripts/list_tokens.py --email user@example.com
  python scripts/list_tokens.py --alpha-user-id <uuid> --include-revoked
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


async def _run(email: Optional[str], alpha_user_id: Optional[str], include_revoked: bool) -> int:
    _ensure_import_path()

    from app.settings import DATABASE_URL
    from app import db

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is not set.")
        return 2

    await db.init_pool()
    try:
        if email:
            user = await db.get_alpha_user_by_email(email)
            if not user:
                print("No alpha user found for email:", email)
                return 1
            alpha_user_id = user["id"]

        assert alpha_user_id
        tokens = await db.get_tokens_for_alpha_user(alpha_user_id, include_revoked=include_revoked)

        print("alpha_user_id:", alpha_user_id)
        if not tokens:
            print("(no tokens)")
            return 0

        for t in tokens:
            print(
                "-",
                "id=", t["id"],
                "name=", t["name"],
                "created_at=", t.get("created_at"),
                "last_used_at=", t.get("last_used_at"),
                "revoked_at=", t.get("revoked_at"),
            )
        return 0
    finally:
        await db.close_pool()


def main() -> int:
    parser = argparse.ArgumentParser(description="List tokens for an alpha user.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="Alpha user email")
    group.add_argument("--alpha-user-id", help="Alpha user id")
    parser.add_argument("--include-revoked", action="store_true", help="Include revoked tokens")
    args = parser.parse_args()

    return asyncio.run(_run(args.email, args.alpha_user_id, args.include_revoked))


if __name__ == "__main__":
    raise SystemExit(main())
