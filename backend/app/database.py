import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .impact import ASSUMPTIONS, EVENTS, analyze
from .schemas import Analysis, EconomicEvent, Profile, ProfileInput


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    occupation TEXT NOT NULL,
                    income_range TEXT NOT NULL,
                    business_owner INTEGER NOT NULL,
                    investor INTEGER NOT NULL,
                    property_owner INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS economic_events (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    event_id INTEGER NOT NULL REFERENCES economic_events(id),
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            connection.executemany(
                """INSERT INTO economic_events (id, title, category, description)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                   category=excluded.category, description=excluded.description""",
                [(event.id, event.title, event.category, event.description) for event in EVENTS],
            )

    def events(self) -> list[EconomicEvent]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM economic_events ORDER BY id").fetchall()
        return [EconomicEvent.model_validate(dict(row)) for row in rows]

    def create_profile(self, data: ProfileInput) -> Profile:
        created_at = timestamp()
        with self.connection() as connection:
            cursor = connection.execute(
                """INSERT INTO users
                   (name, occupation, income_range, business_owner, investor, property_owner, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (data.name.strip(), data.occupation.strip(), data.income_range,
                 data.business_owner, data.investor, data.property_owner, created_at),
            )
            row = connection.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
        return self._profile(row)

    def profile(self, user_id: int) -> Profile | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id=?", (user_id,),
            ).fetchone()
        return self._profile(row) if row is not None else None

    @staticmethod
    def _profile(row: sqlite3.Row) -> Profile:
        return Profile(
            id=row["id"], name=row["name"], occupation=row["occupation"],
            incomeRange=row["income_range"], businessOwner=bool(row["business_owner"]),
            investor=bool(row["investor"]), propertyOwner=bool(row["property_owner"]),
            createdAt=row["created_at"],
        )

    def create_analysis(self, user_id: int, event_id: int) -> Analysis:
        with self.connection() as connection:
            profile_row = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if profile_row is None:
                raise LookupError("Profile not found")
            event_row = connection.execute("SELECT * FROM economic_events WHERE id=?", (event_id,)).fetchone()
            if event_row is None:
                raise LookupError("Economic event not found")
            profile = self._profile(profile_row)
            event = EconomicEvent.model_validate(dict(event_row))
            result = Analysis(
                id=0, profile=profile, event=event, impacts=analyze(profile, event),
                assumptions=ASSUMPTIONS, createdAt=timestamp(),
            )
            cursor = connection.execute(
                "INSERT INTO analysis_results (user_id, event_id, result_json, created_at) VALUES (?, ?, ?, ?)",
                (user_id, event_id, result.model_dump_json(by_alias=True), result.created_at),
            )
            result.id = cursor.lastrowid
            connection.execute(
                "UPDATE analysis_results SET result_json=? WHERE id=?",
                (result.model_dump_json(by_alias=True), result.id),
            )
        return result

    def analysis(self, analysis_id: int) -> Analysis | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM analysis_results WHERE id=?", (analysis_id,),
            ).fetchone()
        return Analysis.model_validate_json(row["result_json"]) if row else None
