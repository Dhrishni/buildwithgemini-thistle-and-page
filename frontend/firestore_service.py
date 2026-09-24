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

"""Firestore client and data access service for Thistle & Page neighborhood P2P lending.

NOTE: PROJECT_ID is explicitly hardcoded as a string. On Agent Platform, reading from
google.auth.default() or GOOGLE_CLOUD_PROJECT can return the numeric project number,
which breaks Firestore operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-9683cc1b79ba"
COLLECTION_NAME = "community_shelf"


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore Client bound directly to the hardcoded GCP project ID."""
    return firestore.Client(project=PROJECT_ID)


def list_community_shelf_items(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches items from Firestore collection 'community_shelf'."""
    db = get_firestore_client()
    col = db.collection(COLLECTION_NAME)
    query = col
    if status:
        query = query.where("status", "==", status)
    docs = query.stream()
    items = []
    for doc in docs:
        d = doc.to_dict()
        d["item_id"] = doc.id
        items.append(d)
    return items


def get_community_item(item_id: str) -> Optional[Dict[str, Any]]:
    """Gets a specific item by item_id from Firestore."""
    db = get_firestore_client()
    doc = db.collection(COLLECTION_NAME).document(item_id).get()
    if doc.exists:
        data = doc.to_dict()
        data["item_id"] = doc.id
        return data
    return None


def add_community_shelf_item(
    title: str,
    author_or_creator: str,
    category: str,
    format: str,
    owner_neighborhood: str,
    condition: str = "good",
    notes: str = "",
    owner_name: str = "You (Current User)",
) -> Dict[str, Any]:
    """Adds a new physical book or reading gear item into Firestore."""
    db = get_firestore_client()
    col = db.collection(COLLECTION_NAME)
    item_id = f"item_{int(datetime.now(timezone.utc).timestamp())}"
    doc_data = {
        "item_id": item_id,
        "title": title,
        "author_or_creator": author_or_creator,
        "category": category,
        "format": format,
        "condition": condition,
        "owner_name": owner_name,
        "owner_neighborhood": owner_neighborhood,
        "distance_miles": 0.0,
        "status": "available",
        "notes": notes,
        "borrowed_by": None,
        "due_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    col.document(item_id).set(doc_data)
    return doc_data


def update_item_borrow_status(
    item_id: str,
    borrowed_by: str,
    due_date: str,
) -> bool:
    """Updates the borrow status of an item in Firestore."""
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(item_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False
    doc_ref.update({
        "status": "borrowed",
        "borrowed_by": borrowed_by,
        "due_date": due_date,
        "borrowed_at": datetime.now(timezone.utc).isoformat(),
    })
    return True


SHELF_COLLECTION_NAME = "user_active_shelves"


def get_user_active_shelf_from_db(user_id: str = "web-user") -> List[Dict[str, Any]]:
    """Fetches all active borrowed items and holds for a specific user from Firestore."""
    db = get_firestore_client()
    col = db.collection(SHELF_COLLECTION_NAME)
    docs = col.where("user_id", "==", user_id).stream()
    items = []
    for doc in docs:
        d = doc.to_dict()
        d["doc_id"] = doc.id
        items.append(d)
    return items


def add_item_to_user_shelf_in_db(
    user_id: str,
    shelf_id: str,
    title: str,
    source_type: str,
    source_name: str,
    item_format: str,
    state: str,
    due_or_available_date: str,
    details: str = "",
) -> Dict[str, Any]:
    """Persists a borrowed item or hold to the user's active shelf in Firestore."""
    db = get_firestore_client()
    col = db.collection(SHELF_COLLECTION_NAME)
    doc_data = {
        "user_id": user_id,
        "shelf_id": shelf_id,
        "title": title,
        "source_type": source_type,
        "source_name": source_name,
        "format": item_format,
        "state": state,
        "due_or_available_date": due_or_available_date,
        "details": details,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    col.document(shelf_id).set(doc_data)
    return doc_data


# --- Production User Directory (Email & Google SSO) ---
USERS_COLLECTION_NAME = "users"


import hashlib
import os
import secrets


def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with a unique random salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"


def verify_password(stored_hash: str, provided_password: str) -> bool:
    """Verifies a password against the stored PBKDF2 salt and hash."""
    try:
        salt, key_hex = stored_hash.split("$", 1)
        expected_key = hashlib.pbkdf2_hmac("sha256", provided_password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return secrets.compare_digest(expected_key.hex(), key_hex)
    except Exception:
        return False


def get_user_by_id_or_email(identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieves a user by user_id or email address from Firestore."""
    db = get_firestore_client()
    col = db.collection(USERS_COLLECTION_NAME)
    
    # 1. Try direct document ID lookup
    doc = col.document(identifier).get()
    if doc.exists:
        data = doc.to_dict()
        data["doc_id"] = doc.id
        return data
    
    # 2. Try query by email
    docs = col.where("email", "==", identifier.lower().strip()).limit(1).stream()
    for d in docs:
        data = d.to_dict()
        data["doc_id"] = d.id
        return data
    return None


def create_or_update_user(
    user_id: str,
    email: str,
    name: str,
    neighborhood: str = "San Mateo County",
    auth_provider: str = "email",
    password: Optional[str] = None,
    avatar: str = "👤",
) -> Dict[str, Any]:
    """Creates or updates a production user record in Firestore."""
    db = get_firestore_client()
    col = db.collection(USERS_COLLECTION_NAME)
    email_clean = email.lower().strip()
    
    user_data = {
        "user_id": user_id,
        "email": email_clean,
        "name": name,
        "neighborhood": neighborhood,
        "avatar": avatar,
        "auth_provider": auth_provider,
        "library_cards": ["San Mateo Main", "Burlingame Public Library"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    existing = get_user_by_id_or_email(email_clean) or get_user_by_id_or_email(user_id)
    if existing:
        doc_id = existing.get("doc_id", user_id)
        if password:
            user_data["password_hash"] = hash_password(password)
        col.document(doc_id).update(user_data)
        user_data["doc_id"] = doc_id
        return user_data
    else:
        user_data["created_at"] = datetime.now(timezone.utc).isoformat()
        if password:
            user_data["password_hash"] = hash_password(password)
        col.document(user_id).set(user_data)
        user_data["doc_id"] = user_id
        return user_data

