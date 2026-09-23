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

"""In-memory data store for San Mateo County libraries & neighborhood P2P lending."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


LIBRARIES = {
    "san_mateo_city": {"name": "San Mateo Public Library (Main)", "city": "San Mateo", "card_color": "#2C4A3E"},
    "redwood_city": {"name": "Redwood City Public Library", "city": "Redwood City", "card_color": "#8C3B2B"},
    "burlingame": {"name": "Burlingame Public Library", "city": "Burlingame", "card_color": "#D48B38"},
    "san_bruno": {"name": "San Bruno Public Library", "city": "San Bruno", "card_color": "#4A5568"},
    "south_sf": {"name": "South San Francisco Public Library", "city": "South San Francisco", "card_color": "#3182CE"},
}


@dataclass
class LibraryEdition:
    edition_id: str
    book_id: str
    format: str  # 'ebook' or 'audiobook'
    duration_minutes: Optional[int] = None
    narrator: Optional[str] = None


@dataclass
class LibraryAvailability:
    library_id: str
    edition_id: str
    copies_total: int
    copies_available: int
    holds_count: int
    estimated_wait_days: int


@dataclass
class LibraryBook:
    book_id: str
    title: str
    author: str
    genre: str
    mood: str
    page_count: int
    description: str
    editions: List[LibraryEdition] = field(default_factory=list)
    availabilities: List[LibraryAvailability] = field(default_factory=list)


@dataclass
class CommunityItem:
    item_id: str
    title: str
    author_or_creator: str
    category: str  # 'physical_book', 'audio_device', 'reading_gear'
    format: str  # 'hardcover', 'paperback', 'device', 'accessory'
    condition: str  # 'like_new', 'good', 'well_read'
    owner_name: str
    owner_neighborhood: str
    distance_miles: float
    status: str  # 'available', 'borrowed'
    notes: str
    due_date: Optional[str] = None
    borrowed_by: Optional[str] = None


@dataclass
class ActiveShelfItem:
    shelf_id: str
    user_id: str
    title: str
    source_type: str  # 'public_library' or 'neighbor_p2p'
    source_name: str  # e.g., "San Mateo Public Library" or "Neighbor Sarah (0.4 mi)"
    format: str
    state: str  # 'borrowed' or 'hold'
    due_or_available_date: str
    details: str


# Seed Books in Library Catalog
SEED_BOOKS: Dict[str, LibraryBook] = {
    "book_1": LibraryBook(
        book_id="book_1",
        title="Tomorrow, and Tomorrow, and Tomorrow",
        author="Gabrielle Zevin",
        genre="Literary Fiction",
        mood="Bittersweet, Nostalgic, Creative",
        page_count=416,
        description="A multi-decade story of identity, creativity, and video games between two childhood friends.",
        editions=[
            LibraryEdition(edition_id="ed_1_ebook", book_id="book_1", format="ebook"),
            LibraryEdition(edition_id="ed_1_audio", book_id="book_1", format="audiobook", duration_minutes=840, narrator="Jennifer Kim"),
        ],
        availabilities=[
            LibraryAvailability("san_mateo_city", "ed_1_ebook", copies_total=5, copies_available=0, holds_count=4, estimated_wait_days=14),
            LibraryAvailability("redwood_city", "ed_1_ebook", copies_total=3, copies_available=1, holds_count=0, estimated_wait_days=0),
            LibraryAvailability("burlingame", "ed_1_audio", copies_total=4, copies_available=0, holds_count=6, estimated_wait_days=21),
            LibraryAvailability("san_bruno", "ed_1_audio", copies_total=2, copies_available=0, holds_count=2, estimated_wait_days=7),
            LibraryAvailability("south_sf", "ed_1_ebook", copies_total=3, copies_available=0, holds_count=1, estimated_wait_days=5),
        ],
    ),
    "book_2": LibraryBook(
        book_id="book_2",
        title="Project Hail Mary",
        author="Andy Weir",
        genre="Science Fiction",
        mood="Optimistic, Gripping, Nerdy",
        page_count=496,
        description="Ryland Grace is the sole survivor on a desperate last-chance mission to save humanity from an extinction event.",
        editions=[
            LibraryEdition(edition_id="ed_2_ebook", book_id="book_2", format="ebook"),
            LibraryEdition(edition_id="ed_2_audio", book_id="book_2", format="audiobook", duration_minutes=970, narrator="Ray Porter"),
        ],
        availabilities=[
            LibraryAvailability("san_mateo_city", "ed_2_ebook", copies_total=6, copies_available=2, holds_count=0, estimated_wait_days=0),
            LibraryAvailability("redwood_city", "ed_2_audio", copies_total=8, copies_available=0, holds_count=5, estimated_wait_days=10),
            LibraryAvailability("burlingame", "ed_2_ebook", copies_total=4, copies_available=0, holds_count=3, estimated_wait_days=12),
        ],
    ),
    "book_3": LibraryBook(
        book_id="book_3",
        title="A Psalm for the Wild-Built",
        author="Becky Chambers",
        genre="Sci-Fi / Cozy",
        mood="Gentle, Philosophical, Comforting",
        page_count=160,
        description="A tea monk and a wild robot ponder what humans really need in a hopeful solarpunk future.",
        editions=[
            LibraryEdition(edition_id="ed_3_ebook", book_id="book_3", format="ebook"),
            LibraryEdition(edition_id="ed_3_audio", book_id="book_3", format="audiobook", duration_minutes=240, narrator="Emmett Grosland"),
        ],
        availabilities=[
            LibraryAvailability("san_mateo_city", "ed_3_ebook", copies_total=4, copies_available=1, holds_count=0, estimated_wait_days=0),
            LibraryAvailability("burlingame", "ed_3_audio", copies_total=3, copies_available=2, holds_count=0, estimated_wait_days=0),
        ],
    ),
}

# Seed Neighborhood P2P Community Shelf (San Mateo County neighborhoods)
SEED_COMMUNITY_ITEMS: Dict[str, CommunityItem] = {
    "item_1": CommunityItem(
        item_id="item_1",
        title="Tomorrow, and Tomorrow, and Tomorrow",
        author_or_creator="Gabrielle Zevin",
        category="physical_book",
        format="hardcover",
        condition="like_new",
        owner_name="Elena R.",
        owner_neighborhood="San Mateo (Downtown / Central Park)",
        distance_miles=0.4,
        status="available",
        notes="First edition hardcover, clean pages. Happy to leave in porch drop-box!",
    ),
    "item_2": CommunityItem(
        item_id="item_2",
        title="Project Hail Mary",
        author_or_creator="Andy Weir",
        category="physical_book",
        format="paperback",
        condition="good",
        owner_name="Marcus T.",
        owner_neighborhood="Burlingame (Broadway)",
        distance_miles=1.2,
        status="available",
        notes="Great beach-read condition. Includes built-in ribbon bookmark.",
    ),
    "item_3": CommunityItem(
        item_id="item_3",
        title="Glocusent Amber Rechargeable Book Light",
        author_or_creator="Glocusent",
        category="reading_gear",
        format="accessory",
        condition="like_new",
        owner_name="Sarah K.",
        owner_neighborhood="San Mateo (Hillsdale)",
        distance_miles=0.8,
        status="available",
        notes="Warm 1800K eye-friendly neck reading light. Great for nighttime reading in bed without waking your partner.",
    ),
    "item_4": CommunityItem(
        item_id="item_4",
        title="Kindle Paperwhite (11th Gen, Warm Light)",
        author_or_creator="Amazon",
        category="audio_device",
        format="device",
        condition="good",
        owner_name="Kenji M.",
        owner_neighborhood="Redwood City (Downtown)",
        distance_miles=2.1,
        status="available",
        notes="Spare Kindle with library Libby pre-configured, waterproof. Available for 2-week loan.",
    ),
}

# Active User Shelf
ACTIVE_SHELF: List[ActiveShelfItem] = [
    ActiveShelfItem(
        shelf_id="shelf_1",
        user_id="default_reader",
        title="A Psalm for the Wild-Built",
        source_type="public_library",
        source_name="San Mateo Public Library (Main)",
        format="ebook",
        state="borrowed",
        due_or_available_date=(datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
        details="Due in 14 days (Auto-returns)",
    ),
    ActiveShelfItem(
        shelf_id="shelf_2",
        user_id="default_reader",
        title="Glocusent Amber Rechargeable Book Light",
        source_type="neighbor_p2p",
        source_name="Neighbor Sarah K. (Hillsdale)",
        format="accessory",
        state="borrowed",
        due_or_available_date=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        details="Due in 7 days (Contact Sarah via in-app message for porch return)",
    ),
]
