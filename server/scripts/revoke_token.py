"""Admin CLI: Revoke an API token.

Supports revoking by token id or by raw token.

Usage examples:
  python scripts/revoke_token.py --token-id <uuid>
  python scripts/revoke_token.py --token <raw_token>
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


async def _run(token_id: Optional[str], raw_token: Optional[str]) -> int:
    _ensure_import_path()

    from app.settings import DATABASE_URL
    from app import db

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is not set.")
        return 2

    await db.init_pool()
    try:
        if token_id:
            ok = await db.revoke_api_token(token_id)
            print("revoked:", bool(ok))
            return 0 if ok else 1

        assert raw_token
        token_hash = db.hash_token(raw_token)
        ok = await db.revoke_api_token_by_hash(token_hash)
        print("revoked:", bool(ok))
        return 0 if ok else 1
    finally:
        await db.close_pool()


def main() -> int:
    parser = argparse.ArgumentParser(description="Revoke an API token.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--token-id", help="Token id")
    group.add_argument("--token", help="Raw token")
    args = parser.parse_args()

    return asyncio.run(_run(args.token_id, args.token))


if __name__ == "__main__":
    raise SystemExit(main())
