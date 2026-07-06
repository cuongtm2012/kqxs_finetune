import json
from typing import Any, Optional

from app.db import fetch_all, fetch_one, get_conn


class ForumRepository:
    def upsert_session(
        self,
        target_date: str,
        window_start: Optional[str],
        window_end: Optional[str],
        finalized_at: Optional[str],
        payload: dict,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO forum_sessions (
                    target_date, window_start, window_end, finalized_at, payload, updated_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, now())
                ON CONFLICT (target_date) DO UPDATE SET
                    window_start = EXCLUDED.window_start,
                    window_end = EXCLUDED.window_end,
                    finalized_at = EXCLUDED.finalized_at,
                    payload = EXCLUDED.payload,
                    updated_at = now()
                """,
                (
                    target_date,
                    window_start,
                    window_end,
                    finalized_at,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def replace_user_picks(self, target_date: str, picks: list[dict]) -> int:
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM forum_user_picks WHERE target_date = %s",
                (target_date,),
            )
            for p in picks:
                conn.execute(
                    """
                    INSERT INTO forum_user_picks (
                        target_date, username, pick_type, numbers, forum,
                        post_id, posted_at, raw_excerpt
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        target_date,
                        p["username"],
                        p["pick_type"],
                        p["numbers"],
                        p.get("forum"),
                        p.get("post_id"),
                        p.get("posted_at"),
                        p.get("raw_excerpt"),
                    ),
                )
            conn.commit()
        return len(picks)

    def get_session(self, target_date: str) -> Optional[dict]:
        row = fetch_one(
            """
            SELECT target_date::text, window_start, window_end, finalized_at,
                   payload, created_at, updated_at
            FROM forum_sessions
            WHERE target_date = %s
            """,
            (target_date,),
        )
        if not row:
            return None
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return {
            "target_date": row["target_date"],
            "window_start": row["window_start"].isoformat() if row["window_start"] else None,
            "window_end": row["window_end"].isoformat() if row["window_end"] else None,
            "finalized_at": row["finalized_at"].isoformat() if row["finalized_at"] else None,
            "payload": payload,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    def has_session(self, target_date: str) -> bool:
        row = fetch_one(
            "SELECT 1 FROM forum_sessions WHERE target_date = %s",
            (target_date,),
        )
        return row is not None

    def get_user_picks_range(self, start_date: str, end_date: str) -> list[dict]:
        rows = fetch_all(
            """
            SELECT target_date::text AS target_date, username, pick_type, numbers,
                   forum, post_id, posted_at, raw_excerpt
            FROM forum_user_picks
            WHERE target_date >= %s AND target_date <= %s
            ORDER BY target_date, posted_at DESC NULLS LAST
            """,
            (start_date, end_date),
        )
        return [
            {
                "target_date": r["target_date"],
                "username": r["username"],
                "pick_type": r["pick_type"],
                "numbers": list(r["numbers"] or []),
                "forum": r["forum"],
                "post_id": r["post_id"],
                "posted_at": r["posted_at"].isoformat() if r["posted_at"] else None,
                "raw_excerpt": r["raw_excerpt"],
            }
            for r in rows
        ]

    def get_user_picks(self, target_date: str) -> list[dict]:
        rows = fetch_all(
            """
            SELECT username, pick_type, numbers, forum, post_id, posted_at, raw_excerpt
            FROM forum_user_picks
            WHERE target_date = %s
            ORDER BY posted_at DESC NULLS LAST
            """,
            (target_date,),
        )
        return [
            {
                "username": r["username"],
                "pick_type": r["pick_type"],
                "numbers": list(r["numbers"] or []),
                "forum": r["forum"],
                "post_id": r["post_id"],
                "posted_at": r["posted_at"].isoformat() if r["posted_at"] else None,
                "raw_excerpt": r["raw_excerpt"],
            }
            for r in rows
        ]

    def summary_dict_from_picks(self, target_date: str) -> dict[str, Any]:
        session = self.get_session(target_date)
        cached = (session or {}).get("payload", {}).get("summary") or {}

        picks = self.get_user_picks(target_date)
        stl_k2n_users: dict = {}
        btl_k3n_users: dict = {}
        daily_users: dict = {}
        de_cham_leaders: list = []
        dan_de: list = []
        muc_lo: dict = {}
        stl_pairs: list[tuple[str, str]] = []
        btl_pairs: list[tuple[str, str]] = []

        for p in picks:
            user = p["username"]
            nums = p["numbers"]
            pt = p["pick_type"]
            excerpt = (p.get("raw_excerpt") or "")[:200]

            if pt == "stl":
                bucket = stl_k2n_users if p.get("forum") == "chan_nuoi" else daily_users
                if user not in bucket:
                    bucket[user] = {"stl": [], "btl": [], "raw": excerpt}
                bucket[user]["stl"] = nums
                bucket[user]["raw"] = excerpt
                for n in nums:
                    stl_pairs.append((n, user))
            elif pt == "btl":
                bucket = btl_k3n_users if p.get("forum") == "chan_nuoi" else daily_users
                if user not in bucket:
                    bucket[user] = {"btl": [], "raw": excerpt}
                bucket[user]["btl"] = nums
                bucket[user]["raw"] = excerpt
                for n in nums:
                    btl_pairs.append((n, user))
            elif pt == "de_cham":
                de_cham_leaders.append({"user": user, "cham": nums})
                if user not in daily_users:
                    daily_users[user] = {
                        "stl": [], "btl": [],
                        "de": {"cham": [], "tong": [], "dau": []},
                    }
                daily_users[user]["de"] = daily_users[user].get("de") or {
                    "cham": [], "tong": [], "dau": []
                }
                daily_users[user]["de"]["cham"] = nums
            elif pt in ("dan_de", "dan_40s", "dan_36s", "dan_64s") and nums:
                dan_de = nums
            elif pt == "muc_lo" and nums:
                muc_lo[0] = nums

        def _freq_map(entries: list[tuple[str, str]]) -> dict:
            out: dict = {}
            for num, user in entries:
                if num not in out:
                    out[num] = {"count": 0, "users": []}
                out[num]["count"] += 1
                if user not in out[num]["users"]:
                    out[num]["users"].append(user)
            return dict(sorted(out.items(), key=lambda x: -x[1]["count"]))

        built = {
            "date": target_date,
            "target_date": target_date,
            "stl_k2n_users": stl_k2n_users,
            "btl_k3n_users": btl_k3n_users,
            "daily_users": daily_users,
            "de_cham_leaders": de_cham_leaders,
            "dan_de": dan_de,
            "muc_lo": muc_lo,
            "stl_frequency": _freq_map(stl_pairs),
            "btl_frequency": _freq_map(btl_pairs),
        }
        for key in ("forums", "weekday", "collected_at", "dan_board", "all_posts"):
            if cached.get(key):
                built[key] = cached[key]
        return built


forum_repo = ForumRepository()
