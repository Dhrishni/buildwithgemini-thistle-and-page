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
def update_user_shelf_state(
    user_id: str,
    shelf_id: str,
    new_state: str,
    details: Optional[str] = None,
    due_or_available_date: Optional[str] = None,
) -> bool:
    """Updates the state and details of a user's shelf item in Firestore."""
    db = get_firestore_client()
    col = db.collection(SHELF_COLLECTION_NAME)
    doc_ref = col.document(shelf_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False
    update_data: Dict[str, Any] = {"state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}
    if details is not None:
        update_data["details"] = details
    if due_or_available_date is not None:
        update_data["due_or_available_date"] = due_or_available_date
    doc_ref.update(update_data)
    return True


def remove_item_from_user_shelf(shelf_id: str) -> bool:
    """Removes a returned item from the active shelf."""
    db = get_firestore_client()
    doc_ref = db.collection(SHELF_COLLECTION_NAME).document(shelf_id)
    if doc_ref.get().exists:
        doc_ref.delete()
        return True
    return False


# --- Production Peer-to-Peer Loaning Escrow Collection ---
LOANS_COLLECTION_NAME = "p2p_loans"


def create_p2p_loan(
    loan_id: str,
    item_id: str,
    title: str,
    lender_id: str,
    lender_name: str,
    lender_neighborhood: str,
    borrower_id: str,
    borrower_name: str,
    duration_days: int,
    meetup_preference: str,
    pickup_code: str,
) -> Dict[str, Any]:
    """Creates a new P2P loan record in escrow state 'requested' with a 4-digit pickup code."""
    db = get_firestore_client()
    col = db.collection(LOANS_COLLECTION_NAME)
    now_iso = datetime.now(timezone.utc).isoformat()
    loan_data = {
        "loan_id": loan_id,
        "item_id": item_id,
        "title": title,
        "lender_id": lender_id,
        "lender_name": lender_name,
        "lender_neighborhood": lender_neighborhood,
        "borrower_id": borrower_id,
        "borrower_name": borrower_name,
        "duration_days": duration_days,
        "meetup_preference": meetup_preference,
        "pickup_code": pickup_code,
        "status": "requested",  # requested -> approved -> borrowed -> returned
        "created_at": now_iso,
        "approved_at": None,
        "borrowed_at": None,
        "returned_at": None,
        "due_date": None,
    }
    col.document(loan_id).set(loan_data)
    return loan_data


def get_p2p_loan(loan_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a loan document by loan_id."""
    db = get_firestore_client()
    doc = db.collection(LOANS_COLLECTION_NAME).document(loan_id).get()
    if doc.exists:
        data = doc.to_dict()
        data["loan_id"] = doc.id
        return data
    return None


def get_user_loans(user_id: str) -> List[Dict[str, Any]]:
    """Retrieves all loans where the user is either the borrower or lender."""
    db = get_firestore_client()
    col = db.collection(LOANS_COLLECTION_NAME)
    loans = []
    # Borrower loans
    for doc in col.where("borrower_id", "==", user_id).stream():
        d = doc.to_dict()
        d["loan_id"] = doc.id
        loans.append(d)
    # Lender loans
    for doc in col.where("lender_id", "==", user_id).stream():
        d = doc.to_dict()
        d["loan_id"] = doc.id
        if not any(x["loan_id"] == doc.id for x in loans):
            loans.append(d)
    return loans


def confirm_p2p_pickup(
    loan_id: str,
    pickup_code: str,
    user_id: str,
) -> Dict[str, Any]:
    """Validates the 4-digit pickup code and transitions the loan from requested/approved to borrowed."""
    db = get_firestore_client()
    doc_ref = db.collection(LOANS_COLLECTION_NAME).document(loan_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"success": False, "error": f"Loan record '{loan_id}' not found."}
    
    loan = doc.to_dict()
    if loan.get("status") == "borrowed":
        return {"success": False, "error": f"This loan is already active and marked as borrowed (due {loan.get('due_date')})."}
    if loan.get("status") == "returned":
        return {"success": False, "error": "This loan has already been returned and closed."}
    
    stored_code = str(loan.get("pickup_code", "")).strip()
    provided_code = str(pickup_code).strip()
    if stored_code != provided_code:
        return {"success": False, "error": f"Invalid 4-digit pickup code '{pickup_code}'. Please check the code provided by your neighbor."}
    
    duration = loan.get("duration_days", 14)
    from datetime import timedelta
    due_date = (datetime.now() + timedelta(days=duration)).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()
    
    doc_ref.update({
        "status": "borrowed",
        "due_date": due_date,
        "borrowed_at": now_iso,
    })
    
    # Update community item status to borrowed
    update_item_borrow_status(
        item_id=loan["item_id"],
        borrowed_by=loan.get("borrower_name", user_id),
        due_date=due_date,
    )
    
    # Update user active shelf
    shelf_id = f"shelf_p2p_{loan_id}"
    update_user_shelf_state(
        user_id=loan["borrower_id"],
        shelf_id=shelf_id,
        new_state="borrowed",
        details=f"In physical possession! Due back to neighbor {loan.get('lender_name')} on {due_date}.",
        due_or_available_date=due_date,
    )
    
    return {
        "success": True,
        "loan_id": loan_id,
        "title": loan["title"],
        "due_date": due_date,
        "message": f"Handshake verified! Physical possession confirmed for '{loan['title']}'. Due back to {loan.get('lender_name')} on {due_date}.",
    }


def return_p2p_loan(loan_id: str, user_id: str) -> Dict[str, Any]:
    """Closes a P2P loan, marks status as returned, and restores the community item to available."""
    db = get_firestore_client()
    doc_ref = db.collection(LOANS_COLLECTION_NAME).document(loan_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"success": False, "error": f"Loan record '{loan_id}' not found."}
    
    loan = doc.to_dict()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    doc_ref.update({
        "status": "returned",
        "returned_at": now_iso,
    })
    
    # Restore item in community shelf collection
    item_ref = db.collection(COLLECTION_NAME).document(loan["item_id"])
    if item_ref.get().exists:
        item_ref.update({
            "status": "available",
            "borrowed_by": None,
            "due_date": None,
        })
    
    # Update or remove borrower shelf
    shelf_id = f"shelf_p2p_{loan_id}"
    update_user_shelf_state(
        user_id=loan["borrower_id"],
        shelf_id=shelf_id,
        new_state="returned",
        details=f"Returned to {loan.get('lender_name')} on {datetime.now().strftime('%Y-%m-%d')}.",
    )
    
    return {
        "success": True,
        "loan_id": loan_id,
        "title": loan["title"],
        "message": f"'{loan['title']}' has been successfully returned to {loan.get('lender_name')} and restored to the neighborhood shelf!",
    }


