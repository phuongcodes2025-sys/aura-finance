import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .impact import ASSUMPTIONS, EVENTS, analyze, complete_analysis
from .schemas import (
    Analysis, AnalysisHistoryItem, ChatMessage, EconomicEvent,
    Profile, ProfileChanges, ProfileData, ProfileInput, ProfileUpdate, PropertyHolding,
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProfileConflictError(Exception):
    pass


class RecordNotFoundError(LookupError):
    pass


class Database:
    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def connection(self, *, write: bool = False):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
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
                CREATE TABLE IF NOT EXISTS stocks (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    ticker TEXT NOT NULL,
                    UNIQUE(user_id, ticker)
                );
                CREATE TABLE IF NOT EXISTS properties (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    property_type TEXT NOT NULL,
                    property_count INTEGER NOT NULL CHECK(property_count > 0)
                );
                CREATE TABLE IF NOT EXISTS recommendations (
                    id INTEGER PRIMARY KEY,
                    analysis_id INTEGER NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    recommendation_text TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'rules' CHECK(source = 'rules'),
                    created_at TEXT NOT NULL,
                    UNIQUE(analysis_id, position)
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    analysis_id INTEGER NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS analysis_user_index ON analysis_results(user_id);
                CREATE INDEX IF NOT EXISTS property_user_index ON properties(user_id);
                CREATE INDEX IF NOT EXISTS chat_analysis_index ON chat_messages(analysis_id);
            """)
            connection.executemany(
                """INSERT INTO economic_events (id, title, category, description)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                   category=excluded.category, description=excluded.description""",
                [(event.id, event.title, event.category, event.description) for event in EVENTS],
            )
            rows = connection.execute("""
                SELECT id, result_json FROM analysis_results
                WHERE NOT EXISTS (
                    SELECT 1 FROM recommendations
                    WHERE recommendations.analysis_id = analysis_results.id
                )
            """).fetchall()
            for row in rows:
                result = complete_analysis(Analysis.model_validate_json(row["result_json"]))
                self._save_recommendations(connection, result)
                connection.execute(
                    "UPDATE analysis_results SET result_json=? WHERE id=?",
                    (result.model_dump_json(by_alias=True), row["id"]),
                )

    def events(self) -> list[EconomicEvent]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM economic_events ORDER BY id").fetchall()
        return [EconomicEvent.model_validate(dict(row)) for row in rows]

    def event(self, event_id: int) -> EconomicEvent | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM economic_events WHERE id=?", (event_id,),
            ).fetchone()
        return EconomicEvent.model_validate(dict(row)) if row is not None else None

    def create_profile(self, data: ProfileInput) -> Profile:
        data = ProfileData.model_validate(data.model_dump(by_alias=True))
        created_at = timestamp()
        with self.connection() as connection:
            cursor = connection.execute(
                """INSERT INTO users
                   (name, occupation, income_range, business_owner, investor, property_owner, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (data.name.strip(), data.occupation.strip(), data.income_range,
                 data.business_owner, data.investor, data.property_owner, created_at),
            )
            self._save_holdings(connection, cursor.lastrowid, data.stocks, data.properties)
            row = connection.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
            return self._profile(connection, row)

    def profile(self, user_id: int) -> Profile | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id=?", (user_id,),
            ).fetchone()
            return self._profile(connection, row) if row is not None else None

    @staticmethod
    def _profile(connection: sqlite3.Connection, row: sqlite3.Row) -> Profile:
        stocks = connection.execute(
            "SELECT ticker FROM stocks WHERE user_id=? ORDER BY id", (row["id"],),
        ).fetchall()
        properties = connection.execute(
            "SELECT property_type, property_count FROM properties WHERE user_id=? ORDER BY id",
            (row["id"],),
        ).fetchall()
        return Profile(
            id=row["id"], name=row["name"], occupation=row["occupation"],
            incomeRange=row["income_range"], businessOwner=bool(row["business_owner"]),
            investor=bool(row["investor"]), propertyOwner=bool(row["property_owner"]),
            createdAt=row["created_at"],
            stocks=[stock["ticker"] for stock in stocks],
            properties=[
                PropertyHolding(propertyType=item["property_type"], propertyCount=item["property_count"])
                for item in properties
            ],
        )

    @staticmethod
    def _save_holdings(
        connection: sqlite3.Connection, user_id: int,
        stocks: list[str], properties: list[PropertyHolding],
    ):
        connection.execute("DELETE FROM stocks WHERE user_id=?", (user_id,))
        connection.execute("DELETE FROM properties WHERE user_id=?", (user_id,))
        connection.executemany(
            "INSERT INTO stocks (user_id, ticker) VALUES (?, ?)",
            [(user_id, ticker) for ticker in stocks],
        )
        connection.executemany(
            "INSERT INTO properties (user_id, property_type, property_count) VALUES (?, ?, ?)",
            [(user_id, item.property_type, item.property_count) for item in properties],
        )

    def update_profile(self, user_id: int, data: ProfileUpdate | ProfileChanges) -> Profile:
        with self.connection(write=True) as connection:
            row = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise RecordNotFoundError("Profile not found")
            current = self._profile(connection, row)
            changes = data.model_dump(exclude_unset=True, by_alias=True)
            if "stocks" in changes:
                changes["investor"] = bool(changes["stocks"])
            if "properties" in changes:
                changes["propertyOwner"] = bool(changes["properties"])
            if "stocks" not in changes and changes.get("investor") is False and current.stocks:
                raise ProfileConflictError("Remove stock holdings through /api/v1 before disabling investment exposure")
            if "properties" not in changes and changes.get("propertyOwner") is False and current.properties:
                raise ProfileConflictError("Remove property holdings through /api/v1 before disabling property exposure")
            profile = Profile.model_validate({**current.model_dump(by_alias=True), **changes})
            connection.execute(
                """UPDATE users SET name=?, occupation=?, income_range=?,
                   business_owner=?, investor=?, property_owner=? WHERE id=?""",
                (profile.name.strip(), profile.occupation.strip(), profile.income_range,
                 profile.business_owner, profile.investor, profile.property_owner, user_id),
            )
            self._save_holdings(connection, user_id, profile.stocks, profile.properties)
            row = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            return self._profile(connection, row)

    def delete_profile(self, user_id: int):
        with self.connection(write=True) as connection:
            row = connection.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise RecordNotFoundError("Profile not found")
            connection.execute("DELETE FROM chat_messages WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM analysis_results WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM users WHERE id=?", (user_id,))

    def create_analysis(self, user_id: int, event_id: int) -> Analysis:
        with self.connection(write=True) as connection:
            profile_row = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if profile_row is None:
                raise RecordNotFoundError("Profile not found")
            event_row = connection.execute("SELECT * FROM economic_events WHERE id=?", (event_id,)).fetchone()
            if event_row is None:
                raise RecordNotFoundError("Economic event not found")
            profile = self._profile(connection, profile_row)
            event = EconomicEvent.model_validate(dict(event_row))
            result = complete_analysis(Analysis(
                id=0, profile=profile, event=event, impacts=analyze(profile, event),
                assumptions=ASSUMPTIONS, createdAt=timestamp(),
            ))
            cursor = connection.execute(
                "INSERT INTO analysis_results (user_id, event_id, result_json, created_at) VALUES (?, ?, ?, ?)",
                (user_id, event_id, result.model_dump_json(by_alias=True), result.created_at),
            )
            result.id = cursor.lastrowid
            connection.execute(
                "UPDATE analysis_results SET result_json=? WHERE id=?",
                (result.model_dump_json(by_alias=True), result.id),
            )
            self._save_recommendations(connection, result)
        return result

    @staticmethod
    def _save_recommendations(connection: sqlite3.Connection, result: Analysis):
        connection.executemany(
            """INSERT INTO recommendations
               (analysis_id, position, recommendation_text, created_at) VALUES (?, ?, ?, ?)""",
            [(result.id, index, text, result.created_at) for index, text in enumerate(result.recommendations)],
        )

    def analysis(self, analysis_id: int) -> Analysis | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM analysis_results WHERE id=?", (analysis_id,),
            ).fetchone()
        return Analysis.model_validate_json(row["result_json"]) if row else None

    def analysis_history(self, user_id: int) -> list[AnalysisHistoryItem]:
        with self.connection() as connection:
            if connection.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone() is None:
                raise RecordNotFoundError("Profile not found")
            rows = connection.execute(
                "SELECT result_json FROM analysis_results WHERE user_id=? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        results = [Analysis.model_validate_json(row["result_json"]) for row in rows]
        return [
            AnalysisHistoryItem(analysisId=result.id, event=result.event.title, createdAt=result.created_at)
            for result in results
        ]

    def save_chat(
        self, analysis_id: int, user_id: int, question: str,
        answer: str, expected_created_at: str,
    ):
        with self.connection(write=True) as connection:
            row = connection.execute(
                "SELECT user_id, created_at FROM analysis_results WHERE id=?", (analysis_id,),
            ).fetchone()
            if row is None or row["user_id"] != user_id or row["created_at"] != expected_created_at:
                raise RecordNotFoundError("Analysis not found for this profile")
            connection.executemany(
                """INSERT INTO chat_messages (user_id, analysis_id, role, message, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                [(user_id, analysis_id, role, message, timestamp())
                 for role, message in (("user", question.strip()), ("assistant", answer))],
            )

    def chat_history(self, analysis_id: int) -> list[ChatMessage]:
        with self.connection() as connection:
            if connection.execute(
                "SELECT id FROM analysis_results WHERE id=?", (analysis_id,),
            ).fetchone() is None:
                raise RecordNotFoundError("Analysis not found")
            rows = connection.execute(
                "SELECT * FROM chat_messages WHERE analysis_id=? ORDER BY id", (analysis_id,),
            ).fetchall()
        return [
            ChatMessage(id=row["id"], userId=row["user_id"], analysisId=row["analysis_id"],
                        role=row["role"], message=row["message"], createdAt=row["created_at"])
            for row in rows
        ]
