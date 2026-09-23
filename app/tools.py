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

"""Tools for Thistle & Page: Library Search, Hold Optimizer, P2P Lending, and Reading Schedule."""

from datetime import datetime, timedelta, timezone
import inspect
import json
import math
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from google import genai
from google.genai import types

from app.data_store import (
    ACTIVE_SHELF,
    ActiveShelfItem,
    CommunityItem,
    LIBRARIES,
    SEED_BOOKS,
    SEED_COMMUNITY_ITEMS,
)
from app.firestore_service import (
    add_community_shelf_item,
    get_community_item,
    list_community_shelf_items,
    update_item_borrow_status,
)


def search_catalog_and_neighborhood(query: str, format_filter: Optional[str] = None) -> Dict[str, Any]:
    """Searches both San Mateo County digital library shelves and neighborhood P2P shelves in Firestore.

    Args:
        query: Search term for book title, author, or keyword (e.g., 'Tomorrow', 'Project Hail Mary', 'book light').
        format_filter: Optional filter ('ebook', 'audiobook', 'physical', 'gear').

    Returns:
        A dictionary with matches from both public libraries and neighborhood lending shelves.
    """
    q = query.lower()
    library_matches = []
    p2p_matches = []

    # 1. Search Library Books
    for book_id, book in SEED_BOOKS.items():
        if q in book.title.lower() or q in book.author.lower() or q in book.description.lower() or q in book.genre.lower():
            # Check availability across libraries
            avail_summary = []
            immediate_options = []
            for av in book.availabilities:
                lib_name = LIBRARIES.get(av.library_id, {}).get("name", av.library_id)
                # find edition format
                ed = next((e for e in book.editions if e.edition_id == av.edition_id), None)
                fmt = ed.format if ed else "digital"
                if format_filter and format_filter.lower() not in fmt.lower():
                    continue

                status_str = f"Available now ({av.copies_available} left)" if av.copies_available > 0 else f"{av.estimated_wait_days}d wait ({av.holds_count} holds)"
                avail_summary.append({
                    "library": lib_name,
                    "format": fmt,
                    "available": av.copies_available > 0,
                    "wait_days": av.estimated_wait_days,
                    "copies_available": av.copies_available,
                    "holds": av.holds_count,
                })
                if av.copies_available > 0:
                    immediate_options.append(f"{lib_name} ({fmt})")

            if avail_summary:
                library_matches.append({
                    "book_id": book.book_id,
                    "title": book.title,
                    "author": book.author,
                    "genre": book.genre,
                    "page_count": book.page_count,
                    "can_start_tonight": len(immediate_options) > 0,
                    "immediate_libraries": immediate_options,
                    "availability": avail_summary,
                })

    # 2. Search Neighborhood P2P Items (from Firestore backend, with in-memory fallback)
    try:
        firestore_items = list_community_shelf_items()
    except Exception:
        firestore_items = []

    if firestore_items:
        items_to_search = firestore_items
    else:
        items_to_search = [item.__dict__ for item in SEED_COMMUNITY_ITEMS.values()]

    for item in items_to_search:
        title = item.get("title", "")
        creator = item.get("author_or_creator", "")
        category = item.get("category", "")
        notes = item.get("notes", "")

        if (
            q in title.lower()
            or q in creator.lower()
            or q in category.lower()
            or q in notes.lower()
        ):
            if format_filter:
                f_low = format_filter.lower()
                if f_low in ["ebook", "audiobook"] and category != "audio_device":
                    continue

            p2p_matches.append({
                "item_id": item.get("item_id"),
                "title": title,
                "creator": creator,
                "category": category,
                "format": item.get("format"),
                "condition": item.get("condition"),
                "owner": item.get("owner_name"),
                "neighborhood": item.get("owner_neighborhood"),
                "distance_miles": item.get("distance_miles", 0.0),
                "status": item.get("status"),
                "notes": notes,
            })

    return {
        "query": query,
        "library_digital_results": library_matches,
        "neighborhood_p2p_results": p2p_matches,
        "summary": f"Found {len(library_matches)} library title(s) and {len(p2p_matches)} neighbor item(s)."
    }


def optimize_library_holds(book_id: str, preferred_format: Optional[str] = None) -> Dict[str, Any]:
    """Compares all San Mateo County library copies for a book to determine the fastest path to read/listen.

    Args:
        book_id: The ID of the book (e.g. 'book_1', 'book_2', 'book_3').
        preferred_format: Optional preference ('ebook' or 'audiobook').

    Returns:
        Fastest options ranked by wait time, identifying instant borrow vs shortest queue.
    """
    book = SEED_BOOKS.get(book_id)
    if not book:
        return {"error": f"Book with ID {book_id} not found."}

    options = []
    for av in book.availabilities:
        ed = next((e for e in book.editions if e.edition_id == av.edition_id), None)
        fmt = ed.format if ed else "digital"
        if preferred_format and preferred_format.lower() != fmt.lower():
            continue

        lib_info = LIBRARIES.get(av.library_id, {"name": av.library_id})
        options.append({
            "library_id": av.library_id,
            "library_name": lib_info["name"],
            "format": fmt,
            "copies_available": av.copies_available,
            "holds_count": av.holds_count,
            "wait_days": av.estimated_wait_days,
            "action": "Borrow Now" if av.copies_available > 0 else f"Place Hold ({av.estimated_wait_days}d wait)",
        })

    # Sort options by wait_days ascending
    options.sort(key=lambda x: (x["wait_days"], x["holds_count"]))

    best_option = options[0] if options else None
    return {
        "title": book.title,
        "author": book.author,
        "recommended_path": best_option,
        "all_branches_ranked": options,
        "can_start_tonight": best_option["wait_days"] == 0 if best_option else False,
    }


def request_neighbor_borrow(item_id: str, duration_days: int = 14, meetup_preference: str = "porch_pickup") -> Dict[str, Any]:
    """Sends a request to borrow a physical book or reading gear from a neighbor.

    Args:
        item_id: ID of the community item (e.g., 'item_1', 'item_2', 'item_3', 'item_4').
        duration_days: Requested loan duration in days (default 14 days).
        meetup_preference: Preferred handoff method ('porch_pickup', 'library_meetup', 'coffee_shop').

    Returns:
        Confirmation and instructions for coordinating with the neighbor.
    """
    due_date = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d")

    # Try Firestore first
    item = None
    try:
        item = get_community_item(item_id)
    except Exception:
        pass

    if item:
        if item.get("status") != "available":
            return {"error": f"Item '{item.get('title')}' is currently marked as {item.get('status')}."}

        # Update in Firestore
        try:
            update_item_borrow_status(item_id, borrowed_by="default_reader", due_date=due_date)
        except Exception:
            pass

        title = item.get("title")
        owner_name = item.get("owner_name")
        owner_neighborhood = item.get("owner_neighborhood")
        item_format = item.get("format")
    else:
        # Fallback to in-memory
        mem_item = SEED_COMMUNITY_ITEMS.get(item_id)
        if not mem_item:
            return {"error": f"Item '{item_id}' not found in neighborhood catalog."}
        if mem_item.status != "available":
            return {"error": f"Item '{mem_item.title}' is currently marked as {mem_item.status}."}
        mem_item.status = "borrowed"
        mem_item.due_date = due_date
        mem_item.borrowed_by = "default_reader"

        title = mem_item.title
        owner_name = mem_item.owner_name
        owner_neighborhood = mem_item.owner_neighborhood
        item_format = mem_item.format

    ACTIVE_SHELF.append(ActiveShelfItem(
        shelf_id=f"shelf_p2p_{len(ACTIVE_SHELF) + 1}",
        user_id="default_reader",
        title=title,
        source_type="neighbor_p2p",
        source_name=f"{owner_name} ({owner_neighborhood})",
        format=item_format,
        state="borrowed",
        due_or_available_date=due_date,
        details=f"Meetup: {meetup_preference}. Contact neighbor {owner_name} to coordinate."
    ))

    return {
        "success": True,
        "title": title,
        "owner": owner_name,
        "neighborhood": owner_neighborhood,
        "due_date": due_date,
        "meetup_preference": meetup_preference,
        "message": f"Successfully requested '{title}' from {owner_name} in {owner_neighborhood}! Added to your active shelf (due {due_date})."
    }


def list_item_for_lending(
    title: str,
    author_or_creator: str,
    category: str,
    format: str,
    neighborhood: str,
    notes: str = ""
) -> Dict[str, Any]:
    """Lists a physical book, reader, or reading accessory on the neighborhood community shelf in Firestore.

    Args:
        title: Title of the book or name of the item.
        author_or_creator: Author or manufacturer.
        category: Category ('physical_book', 'audio_device', 'reading_gear').
        format: Format/type ('hardcover', 'paperback', 'device', 'accessory').
        neighborhood: San Mateo County neighborhood (e.g. 'San Mateo - Baywood', 'Burlingame').
        notes: Condition details or handoff notes (e.g. 'Like new, porch pickup available').

    Returns:
        Details of the newly published community listing.
    """
    item_id = None
    try:
        new_doc = add_community_shelf_item(
            title=title,
            author_or_creator=author_or_creator,
            category=category,
            format=format,
            owner_neighborhood=neighborhood,
            condition="good",
            notes=notes,
            owner_name="You (Current User)",
        )
        item_id = new_doc.get("item_id")
    except Exception:
        # Fallback to in-memory
        item_id = f"item_{len(SEED_COMMUNITY_ITEMS) + 1}"
        new_item = CommunityItem(
            item_id=item_id,
            title=title,
            author_or_creator=author_or_creator,
            category=category,
            format=format,
            condition="good",
            owner_name="You (Current User)",
            owner_neighborhood=neighborhood,
            distance_miles=0.0,
            status="available",
            notes=notes,
        )
        SEED_COMMUNITY_ITEMS[item_id] = new_item

    return {
        "success": True,
        "item_id": item_id,
        "title": title,
        "neighborhood": neighborhood,
        "message": f"'{title}' is now listed on the {neighborhood} community shelf in Firestore for neighbors to borrow!"
    }


def get_my_active_shelf() -> Dict[str, Any]:
    """Retrieves all active items on the user's shelf (public library digital loans + neighbor physical loans).

    Returns:
        A list of borrowed items with due dates and any active holds.
    """
    items = []
    for item in ACTIVE_SHELF:
        items.append({
            "shelf_id": item.shelf_id,
            "title": item.title,
            "source_type": item.source_type,
            "source": item.source_name,
            "format": item.format,
            "state": item.state,
            "due_date": item.due_or_available_date,
            "details": item.details,
        })
    return {
        "total_active_items": len(items),
        "items": items,
    }


def calculate_reading_pace(total_pages_or_minutes: int, days_remaining: int, is_audiobook: bool = False) -> Dict[str, Any]:
    """Calculates daily target pacing to finish a borrowed book before its return deadline.

    Args:
        total_pages_or_minutes: Total page count for ebooks/physical books, or audio minutes for audiobooks.
        days_remaining: Number of days left until the item must be returned.
        is_audiobook: Set to True if calculating for an audiobook (minutes), False for pages.

    Returns:
        Pacing calculations including daily goals, estimated daily time commitment, and finish projection.
    """
    if days_remaining <= 0:
        return {"error": "Days remaining must be greater than 0."}

    daily_units = math.ceil(total_pages_or_minutes / days_remaining)

    if is_audiobook:
        daily_mins_1x = daily_units
        daily_mins_1_25x = math.ceil(daily_units / 1.25)
        return {
            "type": "audiobook",
            "total_minutes": total_pages_or_minutes,
            "days_remaining": days_remaining,
            "daily_target_minutes": daily_mins_1x,
            "daily_target_at_1_25x": daily_mins_1_25x,
            "recommendation": f"Listen to {daily_mins_1x} mins/day ({daily_mins_1_25x} mins/day at 1.25x speed) to finish on time."
        }
    else:
        est_minutes_per_day = math.ceil(daily_units * 1.8)
        return {
            "type": "book",
            "total_pages": total_pages_or_minutes,
            "days_remaining": days_remaining,
            "daily_target_pages": daily_units,
            "estimated_daily_time_minutes": est_minutes_per_day,
            "recommendation": f"Read {daily_units} pages/day (~{est_minutes_per_day} minutes/day) to comfortably finish before the due date."
        }

# ---------------------------------------------------------------------------
# Real Data / Action Tools: Google Books Lookup & Neighborhood Distance
# ---------------------------------------------------------------------------

import urllib.parse
import urllib.request
import json

SAN_MATEO_COORDINATES = {
    "san mateo (downtown)": (37.5630, -122.3255),
    "san mateo (central park)": (37.5605, -122.3218),
    "san mateo (hillsdale)": (37.5401, -122.2989),
    "san mateo (baywood)": (37.5582, -122.3385),
    "burlingame (broadway)": (37.5857, -122.3642),
    "burlingame (downtown)": (37.5778, -122.3481),
    "redwood city (downtown)": (37.4852, -122.2364),
    "san bruno (center)": (37.6305, -122.4111),
    "south san francisco": (37.6547, -122.4077),
}


def lookup_book_metadata(title_or_isbn: str) -> Dict[str, Any]:
    """Fetches real book metadata and cover art from the Google Books API.

    Args:
        title_or_isbn: Book title, author name, or ISBN (e.g. 'Tomorrow, and Tomorrow, and Tomorrow', 'Project Hail Mary').

    Returns:
        Verified book metadata including subtitle, author, publisher, publication date, page count, description, categories, average rating, and cover image URL.
    """
    query = urllib.parse.quote(title_or_isbn)
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ThistleAndPage/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                return {"error": f"Google Books API returned status {response.status}"}
            data = json.loads(response.read().decode())
            
        items = data.get("items", [])
        if not items:
            return {"found": False, "message": f"No book matches found for '{title_or_isbn}'"}
            
        volume_info = items[0].get("volumeInfo", {})
        
        # Ensure image URL is HTTPS to avoid mixed-content issues
        image_links = volume_info.get("imageLinks", {})
        thumbnail = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if thumbnail and thumbnail.startswith("http://"):
            thumbnail = "https://" + thumbnail[7:]
            
        return {
            "found": True,
            "title": volume_info.get("title"),
            "subtitle": volume_info.get("subtitle"),
            "authors": volume_info.get("authors", []),
            "publisher": volume_info.get("publisher"),
            "published_date": volume_info.get("publishedDate"),
            "description": volume_info.get("description", "")[:400] + ("..." if len(volume_info.get("description", "")) > 400 else ""),
            "page_count": volume_info.get("pageCount"),
            "categories": volume_info.get("categories", []),
            "average_rating": volume_info.get("averageRating"),
            "ratings_count": volume_info.get("ratingsCount"),
            "cover_image_url": thumbnail,
            "info_link": volume_info.get("infoLink"),
        }
    except Exception as e:
        return {"error": f"Failed to fetch book metadata: {str(e)}"}


def calculate_neighborhood_distance(user_location: str, neighbor_location: str) -> Dict[str, Any]:
    """Calculates real distance and estimated walking/driving time between two San Mateo County locations.

    Args:
        user_location: User's neighborhood or address (e.g. 'San Mateo (Downtown)', 'Hillsdale').
        neighbor_location: Neighbor's neighborhood or branch (e.g. 'Burlingame (Broadway)', 'Redwood City (Downtown)').

    Returns:
        Calculated distance in miles, estimated walking minutes, and driving minutes.
    """
    def _find_coords(loc: str):
        l_norm = loc.lower().strip()
        for key, coords in SAN_MATEO_COORDINATES.items():
            if key in l_norm or l_norm in key:
                return coords
        # Default coordinates around central San Mateo County if unknown
        return (37.5630, -122.3255)

    lat1, lon1 = _find_coords(user_location)
    lat2, lon2 = _find_coords(neighbor_location)

    # Haversine distance formula
    r_miles = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_miles = round(r_miles * c, 2)

    # Walking speed ~ 3.0 mph (20 mins/mile); Driving speed in city ~ 20 mph (3 mins/mile)
    walk_minutes = max(1, math.ceil(distance_miles * 20))
    drive_minutes = max(1, math.ceil(distance_miles * 3) + 2)

    return {
        "from": user_location,
        "to": neighbor_location,
        "distance_miles": distance_miles,
        "estimated_walk_minutes": walk_minutes,
        "estimated_drive_minutes": drive_minutes,
        "pickup_friendly": distance_miles <= 1.5,
        "summary": f"{distance_miles} miles away (~{walk_minutes} min walk or ~{drive_minutes} min drive).",
    }


def search_open_library(query: str) -> Dict[str, Any]:
    """Searches the free public Open Library API (Internet Archive) for real book editions, ISBNs, and cover IDs.

    Args:
        query: Book title, author, or subject (e.g. 'Tomorrow and Tomorrow and Tomorrow', 'Andy Weir').

    Returns:
        Real book details from Open Library including title, author names, first publish year, edition count, Open Library Work key, and direct cover image URL.
    """
    encoded_q = urllib.parse.quote(query)
    url = f"https://openlibrary.org/search.json?q={encoded_q}&limit=3"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ThistleAndPageLibraryAgent/1.0 (https://openlibrary.org)"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status != 200:
                return {"error": f"Open Library API returned status {response.status}"}
            data = json.loads(response.read().decode())

        docs = data.get("docs", [])
        if not docs:
            return {"found": False, "message": f"No Open Library entries found for '{query}'"}

        results = []
        for doc in docs:
            cover_id = doc.get("cover_i")
            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None
            results.append({
                "title": doc.get("title"),
                "authors": doc.get("author_name", []),
                "first_publish_year": doc.get("first_publish_year"),
                "edition_count": doc.get("edition_count"),
                "work_key": doc.get("key"),
                "isbn_sample": doc.get("isbn", [])[:3] if doc.get("isbn") else [],
                "cover_url": cover_url,
            })

        return {
            "found": True,
            "query": query,
            "total_matches": data.get("num_found", len(results)),
            "books": results,
        }
    except Exception as e:
        return {"error": f"Open Library lookup failed: {str(e)}"}

# ---------------------------------------------------------------------------
# Image Generation & Public GCS Upload Tool
# ---------------------------------------------------------------------------

from google.adk.tools import ToolContext
from google.cloud import storage
import inspect

GCS_BUCKET_NAME = "thistle-and-page-assets-9683cc"
GCP_PROJECT_ID = "qwiklabs-gcp-03-9683cc1b79ba"


async def generate_item_image(
    prompt: str,
    item_title: str,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """Generates an illustration, book cover, or item photo for a book or community listing.

    Uses the gemini-3.1-flash-lite-image model in the global region, saves the image
    as a session artifact, and uploads it to the public Cloud Storage bucket.

    Args:
        prompt: Description of the visual to generate (e.g. 'Vintage illustrated book cover for Project Hail Mary with starry cosmos', 'Cozy botanical bookmark with pressed flowers').
        item_title: Title of the book or item being illustrated.

    Returns:
        A dictionary containing the public Cloud Storage HTTPS URL and status.
    """
    try:
        # Initialize Google GenAI client in global region
        genai_client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT_ID,
            location="global",
        )

        full_prompt = f"Book cover illustration or reading community visual: {prompt}. High quality, cottagecore / vintage paper aesthetic, title: {item_title}."
        
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE]
            ),
        )

        image_bytes = None
        mime_type = "image/png"
        for candidate in response.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if getattr(part, "inline_data", None):
                        image_bytes = part.inline_data.data
                        mime_type = getattr(part.inline_data, "mime_type", "image/png") or "image/png"
                        break

        if not image_bytes:
            return {"error": "No image was generated by the model."}

        # Clean filename
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", item_title.lower())[:30]
        timestamp = int(datetime.now(timezone.utc).timestamp())
        ext = "png" if "png" in mime_type else "jpg"
        filename = f"{slug}_{timestamp}.{ext}"

        # 1. Save with tool_context.save_artifact if available
        if tool_context and hasattr(tool_context, "save_artifact"):
            try:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
                if inspect.isawaitable(res):
                    await res
            except Exception as e:
                print(f"[Warning] Failed to save artifact in tool_context: {e}")

        # 2. Upload same bytes directly to public Cloud Storage bucket
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "success": True,
            "item_title": item_title,
            "filename": filename,
            "public_url": public_url,
            "message": f"Generated image for '{item_title}' and uploaded to public Cloud Storage: {public_url}",
        }
    except Exception as e:
        return {"error": f"Failed to generate and upload image: {str(e)}"}
