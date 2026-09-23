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

import uuid
from app.firestore_service import update_item_borrow_status
from app.tools import (
    calculate_neighborhood_distance,
    calculate_reading_pace,
    get_my_active_shelf,
    list_item_for_lending,
    lookup_book_metadata,
    optimize_library_holds,
    request_neighbor_borrow,
    search_catalog_and_neighborhood,
    search_open_library,
)


def test_search_catalog_and_neighborhood():
    res = search_catalog_and_neighborhood("Tomorrow")
    assert len(res["library_digital_results"]) > 0
    assert len(res["neighborhood_p2p_results"]) > 0

    lib_match = res["library_digital_results"][0]
    assert "Tomorrow, and Tomorrow, and Tomorrow" in lib_match["title"]

    p2p_match = res["neighborhood_p2p_results"][0]
    assert p2p_match["format"] == "hardcover"
    assert p2p_match["owner"] == "Elena R."


def test_optimize_library_holds():
    opt = optimize_library_holds("book_1")
    assert opt["title"] == "Tomorrow, and Tomorrow, and Tomorrow"
    assert opt["recommended_path"] is not None
    assert opt["recommended_path"]["wait_days"] == 0
    assert opt["can_start_tonight"] is True


def test_neighborhood_p2p_borrow_and_shelf():
    # Create a fresh item so test is idempotent against persistent Firestore
    unique_title = f"Test Borrow Book {uuid.uuid4().hex[:6]}"
    listed = list_item_for_lending(
        title=unique_title,
        author_or_creator="Test Author",
        category="physical_book",
        format="paperback",
        neighborhood="Burlingame",
        notes="Available for test borrow.",
    )
    assert listed["success"] is True
    item_id = listed["item_id"]

    shelf_before = get_my_active_shelf()
    count_before = shelf_before["total_active_items"]

    borrow_res = request_neighbor_borrow(item_id, duration_days=14, meetup_preference="porch_pickup")
    assert borrow_res.get("success") is True
    assert unique_title in borrow_res["title"]

    shelf_after = get_my_active_shelf()
    assert shelf_after["total_active_items"] == count_before + 1


def test_list_item_for_lending():
    unique_title = f"Unique Book {uuid.uuid4().hex[:8]}"
    res = list_item_for_lending(
        title=unique_title,
        author_or_creator="Shelby Van Pelt",
        category="physical_book",
        format="hardcover",
        neighborhood="San Mateo (Baywood)",
        notes="Book club pick, gently read.",
    )
    assert res["success"] is True
    assert unique_title in res["title"]

    search_res = search_catalog_and_neighborhood(unique_title)
    assert len(search_res["neighborhood_p2p_results"]) == 1
    assert search_res["neighborhood_p2p_results"][0]["title"] == unique_title


def test_calculate_reading_pace():
    pace_book = calculate_reading_pace(total_pages_or_minutes=400, days_remaining=10, is_audiobook=False)
    assert pace_book["daily_target_pages"] == 40
    assert pace_book["estimated_daily_time_minutes"] > 0

    pace_audio = calculate_reading_pace(total_pages_or_minutes=600, days_remaining=6, is_audiobook=True)
    assert pace_audio["daily_target_minutes"] == 100
    assert pace_audio["daily_target_at_1_25x"] == 80


def test_lookup_book_metadata():
    res = lookup_book_metadata("Project Hail Mary")
    # Google Books can occasionally rate-limit unauthenticated workshop environments with 429
    if "error" in res and "429" in res["error"]:
        return
    assert res.get("found") is True
    assert "Andy Weir" in res.get("authors", [])
    assert res.get("page_count") is not None
    assert res.get("page_count") > 400
    if res.get("cover_image_url"):
        assert res.get("cover_image_url").startswith("https://")


def test_calculate_neighborhood_distance():
    res = calculate_neighborhood_distance("San Mateo (Downtown)", "Burlingame (Broadway)")
    assert res["distance_miles"] > 0
    assert res["estimated_walk_minutes"] > 0
    assert res["estimated_drive_minutes"] > 0
    assert "miles away" in res["summary"]


def test_search_open_library():
    res = search_open_library("Tomorrow and Tomorrow and Tomorrow")
    # Open Library public API can occasionally reset connections under test runner concurrency
    if "error" in res and ("Connection reset" in res["error"] or "timed out" in res["error"]):
        return
    assert res.get("found") is True
    assert res.get("total_matches", 0) > 0
    books = res.get("books", [])
    assert len(books) > 0
    assert "Gabrielle Zevin" in books[0].get("authors", [])
    if books[0].get("cover_url"):
        assert "openlibrary.org" in books[0].get("cover_url")
import pytest
from app.tools import generate_item_image


class DummyToolContext:
    def __init__(self):
        self.artifacts = []

    async def save_artifact(self, filename, artifact):
        self.artifacts.append((filename, artifact))
        return 1


@pytest.mark.asyncio
async def test_generate_item_image():
    ctx = DummyToolContext()
    res = await generate_item_image(
        prompt="Vintage botanical bookplate illustration with fern leaves",
        item_title="Burlingame Community Bookmark",
        tool_context=ctx,
    )
    assert res.get("success") is True
    assert "public_url" in res
    assert res["public_url"].startswith("https://storage.googleapis.com/thistle-and-page-assets-9683cc/")
    assert len(ctx.artifacts) == 1
    filename, part = ctx.artifacts[0]
    assert "burlingame" in filename
    assert part is not None
