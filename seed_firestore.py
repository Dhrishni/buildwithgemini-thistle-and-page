# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Seeds Firestore with initial neighborhood P2P community shelf items."""

from datetime import datetime, timezone
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-9683cc1b79ba"
COLLECTION_NAME = "community_shelf"

SEED_ITEMS = [
    {
        "item_id": "item_1",
        "title": "Tomorrow, and Tomorrow, and Tomorrow",
        "author_or_creator": "Gabrielle Zevin",
        "category": "physical_book",
        "format": "hardcover",
        "condition": "like_new",
        "owner_name": "Elena R.",
        "owner_neighborhood": "San Mateo (Downtown / Central Park)",
        "distance_miles": 0.4,
        "status": "available",
        "notes": "First edition hardcover, clean pages. Happy to leave in porch drop-box!",
        "borrowed_by": None,
        "due_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "item_id": "item_2",
        "title": "Project Hail Mary",
        "author_or_creator": "Andy Weir",
        "category": "physical_book",
        "format": "paperback",
        "condition": "good",
        "owner_name": "Marcus T.",
        "owner_neighborhood": "Burlingame (Broadway)",
        "distance_miles": 1.2,
        "status": "available",
        "notes": "Great beach-read condition. Includes built-in ribbon bookmark.",
        "borrowed_by": None,
        "due_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "item_id": "item_3",
        "title": "Glocusent Amber Rechargeable Book Light",
        "author_or_creator": "Glocusent",
        "category": "reading_gear",
        "format": "accessory",
        "condition": "like_new",
        "owner_name": "Sarah K.",
        "owner_neighborhood": "San Mateo (Hillsdale)",
        "distance_miles": 0.8,
        "status": "available",
        "notes": "Warm 1800K eye-friendly neck reading light. Great for nighttime reading without disturbing others.",
        "borrowed_by": None,
        "due_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "item_id": "item_4",
        "title": "Kindle Paperwhite (11th Gen, Warm Light)",
        "author_or_creator": "Amazon",
        "category": "audio_device",
        "format": "device",
        "condition": "good",
        "owner_name": "Kenji M.",
        "owner_neighborhood": "Redwood City (Downtown)",
        "distance_miles": 2.1,
        "status": "available",
        "notes": "Spare Kindle with library Libby pre-configured, waterproof. Available for 2-week loan.",
        "borrowed_by": None,
        "due_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "item_id": "item_5",
        "title": "A Psalm for the Wild-Built",
        "author_or_creator": "Becky Chambers",
        "category": "physical_book",
        "format": "hardcover",
        "condition": "like_new",
        "owner_name": "David L.",
        "owner_neighborhood": "San Bruno (Center)",
        "distance_miles": 1.5,
        "status": "available",
        "notes": "Short cozy solarpunk novella. Perfect quick weekend read.",
        "borrowed_by": None,
        "due_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
]


def seed():
    print(f"Connecting to Firestore with hardcoded project ID: {PROJECT_ID}")
    db = firestore.Client(project=PROJECT_ID)
    col = db.collection(COLLECTION_NAME)

    for item in SEED_ITEMS:
        doc_ref = col.document(item["item_id"])
        doc_ref.set(item)
        print(f"  [+] Seeded {item['item_id']}: {item['title']} ({item['owner_neighborhood']})")

    print(f"\nSuccessfully seeded {len(SEED_ITEMS)} items into collection '{COLLECTION_NAME}' in project '{PROJECT_ID}'.")


if __name__ == "__main__":
    seed()
