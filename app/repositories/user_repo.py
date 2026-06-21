import logging

from app.db import execute, fetch_one

logger = logging.getLogger(__name__)


class UserRepository:
    def login(self, user: dict) -> bool:
        try:
            existing = fetch_one("SELECT 1 FROM users WHERE user_id = %s", (user["userId"],))
            if existing:
                return False
            execute(
                """
                INSERT INTO users (user_id, email, display_name, access_token)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user["userId"],
                    user.get("email", ""),
                    user.get("displayName", ""),
                    user.get("accessToken", ""),
                ),
            )
            return True
        except Exception as exc:
            logger.error("%s", exc)
            return False


user_repo = UserRepository()
