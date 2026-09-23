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

from app.firestore_service import (
    PROJECT_ID,
    COLLECTION_NAME,
    get_firestore_client,
    list_community_shelf_items,
    get_community_item,
    add_community_shelf_item,
    update_item_borrow_status,
)


def test_hardcoded_project_id():
    assert PROJECT_ID == "qwiklabs-gcp-03-9683cc1b79ba"
    assert isinstance(PROJECT_ID, str)
    client = get_firestore_client()
    assert client.project == "qwiklabs-gcp-03-9683cc1b79ba"


def test_firestore_seeded_read():
    items = list_community_shelf_items()
    assert len(items) >= 5
    titles = [item["title"] for item in items]
    assert "Tomorrow, and Tomorrow, and Tomorrow" in titles
    assert "Project Hail Mary" in titles
    assert "Glocusent Amber Rechargeable Book Light" in titles


def test_firestore_write_and_update():
    new_doc = add_community_shelf_item(
        title="The Midnight Library",
        author_or_creator="Matt Haig",
        category="physical_book",
        format="hardcover",
        owner_neighborhood="San Mateo (Downtown)",
        notes="Heartwarming magical realism.",
        owner_name="Test Neighbor",
    )
    assert new_doc["item_id"] is not None
    assert new_doc["title"] == "The Midnight Library"

    # Verify read back
    fetched = get_community_item(new_doc["item_id"])
    assert fetched is not None
    assert fetched["status"] == "available"

    # Verify borrow update
    updated = update_item_borrow_status(new_doc["item_id"], borrowed_by="reader_abc", due_date="2026-10-15")
    assert updated is True

    fetched_updated = get_community_item(new_doc["item_id"])
    assert fetched_updated["status"] == "borrowed"
    assert fetched_updated["borrowed_by"] == "reader_abc"
