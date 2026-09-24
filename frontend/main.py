"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TransportProtocol,
)
try:
    from a2a.types import FilePart, TextPart
except ImportError:
    TextPart = None
    FilePart = None
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import json
from pathlib import Path

_metadata_path = Path(__file__).resolve().parent.parent / "deployment_metadata.json"
_default_resource = ""
if _metadata_path.exists():
    try:
        with open(_metadata_path) as _f:
            _default_resource = json.load(_f).get("remote_agent_runtime_id", "")
    except Exception:
        pass

RESOURCE = os.environ.get("AGENT_ENGINE_RESOURCE_NAME", _default_resource)
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


import base64
import hashlib
import hmac
import time

AUTH_SECRET = os.environ.get("AUTH_SECRET", "thistle-and-page-san-mateo-secret-2026")

DEFAULT_PROFILES = [
    {
        "user_id": "elena_baywood",
        "name": "Elena R.",
        "neighborhood": "Baywood, San Mateo",
        "avatar": "🌿",
        "bio": "Avid reader near Central Park; loves cozy solarpunk & audiobooks.",
    },
    {
        "user_id": "marcus_hillsdale",
        "name": "Marcus T.",
        "neighborhood": "Hillsdale, San Mateo",
        "avatar": "📖",
        "bio": "Hard sci-fi enthusiast; shares reading lamps & hardcover space operas.",
    },
    {
        "user_id": "sarah_burlingame",
        "name": "Sarah K.",
        "neighborhood": "Easton Addition, Burlingame",
        "avatar": "☕",
        "bio": "Local librarian & tea lover; has Burlingame & San Mateo library cards.",
    },
]


def create_reader_token(user_id: str, name: str, neighborhood: str) -> str:
    payload = f"{user_id}:{name}:{neighborhood}:{int(time.time())}"
    sig = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_reader_token(token: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        parts = raw.split(":")
        if len(parts) != 5:
            return None
        user_id, name, neighborhood, ts, sig = parts
        expected_payload = f"{user_id}:{name}:{neighborhood}:{ts}"
        expected_sig = hmac.new(AUTH_SECRET.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return {"user_id": user_id, "name": name, "neighborhood": neighborhood}
    except Exception:
        pass
    return None


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI.

    Text parts pass through as {"kind": "text"}. A2UI data parts (tagged
    application/json+a2ui) become {"kind": "a2ui", "data": <message>} so the UI
    renders the card; each data part is one A2UI message (beginRendering or
    surfaceUpdate).
    """
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        text_val = getattr(root, "text", None)
        if text_val:
            out.append({"kind": "text", "text": text_val})
        elif getattr(root, "data", None) is not None:
            data_val = root.data
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else getattr(meta, "mime_type", None)
            
            # 1. Direct A2UI data part
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": data_val})
            # 2. Nested A2UI data part (wrapped inside dict: {'data': {...}, 'metadata': {'mimeType': '...'}})
            elif isinstance(data_val, dict):
                inner_meta = data_val.get("metadata") or {}
                inner_mime = inner_meta.get("mimeType") if isinstance(inner_meta, dict) else getattr(inner_meta, "mime_type", None)
                if inner_mime == _A2UI_MIME and "data" in data_val:
                    out.append({"kind": "a2ui", "data": data_val["data"]})
                elif "surfaceUpdate" in data_val or "beginRendering" in data_val:
                    out.append({"kind": "a2ui", "data": data_val})
        elif FilePart and isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.get("/api/auth/profiles")
async def get_profiles():
    """Lists community reader profiles available for quick-switch testing."""
    return JSONResponse({"profiles": DEFAULT_PROFILES})


@app.post("/api/auth/login")
async def login(req: Request):
    """Logs in or registers a lightweight reader identity and issues an HMAC-signed token."""
    body = await req.json()
    user_id = (body.get("user_id") or "").strip().lower()
    name = (body.get("name") or "").strip()
    neighborhood = (body.get("neighborhood") or "").strip()

    if not user_id:
        user_id = f"reader_{uuid.uuid4().hex[:6]}"
    if not name:
        # Match from default profile or generate friendly name
        p = next((x for x in DEFAULT_PROFILES if x["user_id"] == user_id), None)
        name = p["name"] if p else f"Reader {user_id[-4:]}"
    if not neighborhood:
        p = next((x for x in DEFAULT_PROFILES if x["user_id"] == user_id), None)
        neighborhood = p["neighborhood"] if p else "San Mateo County"

    token = create_reader_token(user_id=user_id, name=name, neighborhood=neighborhood)
    return JSONResponse({
        "token": token,
        "user_id": user_id,
        "name": name,
        "neighborhood": neighborhood,
    })


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    
    # 1. Resolve Reader Identity from Token or Payload
    auth_header = req.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif body.get("token"):
        token = body.get("token")

    verified_user = verify_reader_token(token) if token else None
    if verified_user:
        user_id = verified_user["user_id"]
        reader_name = verified_user["name"]
        reader_neighborhood = verified_user["neighborhood"]
    else:
        # Default or fallback profile
        user_id = (body.get("user_id") or "elena_baywood").strip().lower()
        p = next((x for x in DEFAULT_PROFILES if x["user_id"] == user_id), None)
        reader_name = p["name"] if p else "Elena R."
        reader_neighborhood = p["neighborhood"] if p else "Baywood, San Mateo"

    # Enrich prompt with authenticated reader identity for tool scoping & conversational warmth
    scoped_prompt = (
        f"[Authenticated Reader: {reader_name} (id: {user_id}, neighborhood: {reader_neighborhood})]\n"
        f"{message}"
    )

    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=scoped_prompt))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            if not isinstance(event, tuple):
                continue
            task, update = event
            if task is not None:
                last_task = task
                if getattr(task, "context_id", None):
                    _contexts[user_id] = task.context_id
            if isinstance(update, TaskArtifactUpdateEvent):
                got_artifact_update = True
                parts.extend(_extract_parts(update.artifact.parts))

        # Non-streaming fallback: pull parts from the final task's artifacts.
        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({
        "parts": parts,
        "reader": {
            "user_id": user_id,
            "name": reader_name,
            "neighborhood": reader_neighborhood,
        }
    })


# Serve the chat UI (keep this mount last so /chat wins).
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
