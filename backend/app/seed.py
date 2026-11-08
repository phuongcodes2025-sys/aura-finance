import argparse
import os

from .database import Database
from .v1_schemas import ProfileCreate, PropertyInput


def seed_demo(database: Database) -> tuple[int, int]:
    database.initialize()
    profile = database.create_profile(ProfileCreate(
        name="Sarah", occupation="Nail Salon Owner", income_range="75k-100k",
        business_owner=True, stocks=["NVDA", "AAPL"],
        properties=[PropertyInput(property_type="Rental Property", property_count=2)],
    ).profile_data())
    analysis = database.create_analysis(profile.id, 2)
    return profile.id, analysis.id


def main():
    parser = argparse.ArgumentParser(description="Create a new synthetic Sarah profile and rate-hike analysis.")
    parser.add_argument("--database", default=os.getenv("DATABASE_PATH", "./aura.sqlite3"))
    args = parser.parse_args()
    user_id, analysis_id = seed_demo(Database(args.database))
    print(f"Created demo profile {user_id} and analysis {analysis_id}.")
    print(f"Dashboard: /api/v1/dashboard/{analysis_id}")


if __name__ == "__main__":
    main()
