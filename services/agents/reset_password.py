"""
Script to reset a user's password in the Smart Building AI database.
Run this script inside the `sb_agents` container:
  docker exec -it sb_agents python reset_password.py
"""

import asyncio
import sys
from database import connect_db, get_pool
from auth_service import _hash_password


async def main():
    username = "youness"  # pragma: allowlist secret
    new_password = "Youness@2026!"  # pragma: allowlist secret

    if len(sys.argv) > 1:
        username = sys.argv[1]
    if len(sys.argv) > 2:
        new_password = sys.argv[2]

    print(f"Resetting password for user '{username}'...")

    await connect_db()
    pool = get_pool()
    if not pool:
        print("Error: Could not connect to the PostgreSQL database.")
        return

    async with pool.acquire() as conn:
        # Check if user exists
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1", username.lower()
        )
        if not row:
            print(f"Error: User '{username}' does not exist in the database.")
            return

        # Hash new password
        password_hash = _hash_password(new_password)

        # Update user
        await conn.execute(
            "UPDATE users SET password_hash = $1, is_active = TRUE WHERE id = $2",
            password_hash,
            row["id"],
        )
        print(f"Successfully reset password for '{username}' to '{new_password}'.")


if __name__ == "__main__":
    asyncio.run(main())
