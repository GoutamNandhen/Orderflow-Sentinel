"""Separate fresh demo database, never delete/overwrite normal or prior demo data."""

import argparse
import os
from pathlib import Path
import uuid
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
parser = argparse.ArgumentParser()
parser.add_argument("--database", default="backend/data/judge-demo.db")
parser.add_argument("--book-five", action="store_true")
args = parser.parse_args()
target = Path(args.database).resolve()
if target.exists():
    raise SystemExit(f"Refusing to overwrite {target}. Choose a fresh --database path.")
target.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + target.as_posix()
from backend.services import core, worker
from backend.schemas import Booking
from backend.db import transaction

core.initialize()
if args.book_five:
    for position in range(1, 6):
        request = Booking(
            user_name="Judge Demo Customer",
            phone="DEMO_CONTACT",
            address="DEMO_LOCATION",
            contact_mode="demo",
            pincode="560038",
            items=[
                {"product_id": "PROD-101" if position == 4 else "PROD-109", "qty": 1}
            ],
        )
        with transaction() as session:
            result = core.book(
                session,
                request,
                "judge-script-session-private-" + uuid.uuid4().hex,
                str(uuid.uuid4()),
                profile="judge",
            )
            print(
                result["id"],
                result["status"],
                "Tracking token:",
                result["tracking_token"],
            )
print(f"Demo database created: {target}")
print("Start backend with DATABASE_URL=sqlite:///" + target.as_posix())
