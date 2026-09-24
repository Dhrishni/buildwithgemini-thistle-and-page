# 🌿 Thistle & Page — System Architecture & Design

**Unified San Mateo County Library & Neighborhood Peer-to-Peer Lending Copilot**

- **Live Application (Google Cloud Run)**: [https://thistle-and-page-frontend-43484983729.us-central1.run.app](https://thistle-and-page-frontend-43484983729.us-central1.run.app)
- **Agent Platform Runtime**: `projects/43484983729/locations/us-central1/reasoningEngines/2746715835870478336`
- **GitHub Repository**: [https://github.com/Dhrishni/buildwithgemini-thistle-and-page](https://github.com/Dhrishni/buildwithgemini-thistle-and-page)

---

## 1. System Architecture Diagram

```mermaid
flowchart TD
    subgraph Client["Frontend Client (Browser)"]
        UI["Web Chat UI (Mobile / Desktop)"]
        AUTH_UI["Identity Center Modal\n(Email/Password, Google SSO, Personas)"]
        RENDERER["A2UI v0.8 Mini-Renderer\n(Cards, Images, Action Buttons)"]
        STORAGE["Local Session Storage\n(Bearer HMAC Token & Profile)"]
    end

    subgraph CloudRun["FastAPI Gateway Proxy (Google Cloud Run)"]
        AUTH_ROUTER["Production Auth Controller\n- /api/auth/register (PBKDF2-SHA256)\n- /api/auth/login\n- /api/auth/google (Google OIDC ID Token)"]
        PROXY["A2A Proxy Gateway (/chat)"]
        CTX_MGR["Per-User Context & Prompt Scoping"]
    end

    subgraph AgentPlatform["Vertex AI Agent Platform (Agent Runtime)"]
        ROOT_AGENT["ADK Root Agent (Gemini 2.5 Flash)"]
        A2UI_CB["A2UI v0.8 Callback & Schema Validator"]
        MEM_CB["Memory Callback (Vertex AI Memory Bank)"]
        CODE_BOX["Agent Engine Secure Code Sandbox"]
    end

    subgraph Services["GCP Cloud Services & Data Stores"]
        FIRESTORE_USERS[("Cloud Firestore: users\n(Durable user directory)")]
        FIRESTORE_SHELVES[("Cloud Firestore: user_active_shelves\n(Per-user loans & holds)")]
        FIRESTORE_COMMUNITY[("Cloud Firestore: community_shelf\n(Neighborhood catalog)")]
        VERTEX_EMBED["Vertex AI Embeddings\n(text-embedding-005)"]
        VERTEX_IMAGE["Imagen 3 / Flash-Lite-Image\n(gemini-3.1-flash-lite-image)"]
        GCS_BUCKET[("Cloud Storage Public Assets\ngs://thistle-and-page-assets-9683cc")]
        MEMORY_BANK["Vertex AI Memory Bank\n(Cross-session user profile)"]
    end

    %% Client flows
    AUTH_UI <-->|Register / Login / Google SSO| AUTH_ROUTER
    UI -->|POST /chat with Bearer Token| PROXY
    AUTH_ROUTER <-->|Read / Write Profiles| FIRESTORE_USERS
    PROXY --> CTX_MGR
    CTX_MGR -->|A2A Protocol / gRPC| ROOT_AGENT

    %% Agent platform flows
    ROOT_AGENT --> A2UI_CB
    ROOT_AGENT --> MEM_CB
    MEM_CB --> MEMORY_BANK

    ROOT_AGENT -->|Persist loans, holds| FIRESTORE_SHELVES
    ROOT_AGENT -->|Query book inventory| FIRESTORE_COMMUNITY
    ROOT_AGENT -->|Vibe semantic search| VERTEX_EMBED
    ROOT_AGENT -->|Bookmark & cover art| VERTEX_IMAGE
    VERTEX_IMAGE -->|Public media URLs| GCS_BUCKET
    ROOT_AGENT -->|Reading pace math| CODE_BOX

    A2UI_CB -->|Structured A2UI JSON| PROXY
    PROXY -->|SSE / JSON Parts| RENDERER
    GCS_BUCKET -.->|Public HTTPS Image Stream| RENDERER
```

---

## 2. Core Subsystems & Components

### A. Client & User Identity Tier (Browser / Frontend)
- **Header Reader Badge**: Displays active user profile (`Maya H. (Hillsdale)`, `Elena R. (Baywood)`), or prompts Sign In.
- **Tabbed Authentication Center**:
  1. **Email & Password**: In-app registration and sign-in with client and server validation.
  2. **Google Sign-In / SSO**: One-click authentication with Google Identity Services (`gsi/client`).
  3. **Community Personas**: 1-click test personas for quick evaluator demos.
- **Session Persistence**: HMAC-SHA256 bearer tokens stored in browser `localStorage`, passed in `Authorization: Bearer <token>` on all `/chat` turns.
- **A2UI v0.8 Native Engine**: Renders interactive cards with zero boilerplate, live action buttons (`.a2btn`), material icons, and inline public image assets without HTML injection vulnerabilities.

### B. Gateway & Proxy Tier (Cloud Run)
- **Service**: `thistle-and-page-frontend` running FastAPI and Uvicorn.
- **Password Security**: Salted PBKDF2-HMAC-SHA256 (100,000 iterations) with cryptographic comparison.
- **Google SSO Verification**: Server-side verification of Google OIDC ID tokens via `google.oauth2.id_token.verify_oauth2_token`.
- **Identity Scoping**: Resolves incoming bearer tokens, extracts `user_id`, and enriches agent prompts:
  `[Authenticated Reader: Name (id: user_id, neighborhood: neighborhood)]`.
- **A2A Client**: Manages isolated conversation contexts (`context_id`) mapped per user to ensure independent conversation history across 100+ concurrent readers.

### C. Agent Reasoning & Tool Tier (Vertex AI Agent Engine)
- **Core LLM**: `gemini-2.5-flash` orchestrated via Google ADK (Agent Development Kit).
- **Tools**:
  1. `get_my_active_shelf`: Reads user-specific borrowed books and holds from Cloud Firestore scoped strictly to `user_id`.
  2. `request_neighbor_borrow`: Creates a peer loan between borrower and lender, recording due dates in Firestore.
  3. `search_catalog_and_neighborhood`: Multi-modal search matching exact titles and semantic reading vibes with distance filtering.
  4. `generate_item_image`: Generates custom bookmark artwork and cover imagery using `gemini-3.1-flash-lite-image` and uploads directly to public GCS.
  5. `calculate_reading_pace`: Assesses due-date feasibility and reading pace.
  6. `AgentEngineSandboxCodeExecutor`: Secure cloud execution sandbox for complex queue simulations and date calculations.

### D. Data & Storage Tier
1. **Google Cloud Firestore**:
   - `users`: Production user directory storing emails, hashed credentials, Google identity IDs, names, neighborhoods, and library card numbers.
   - `user_active_shelves`: Per-user active loans, library holds, due dates, and handoff instructions.
   - `community_shelf`: Catalog of physical books and reading accessories offered by neighbors in San Mateo County.
2. **Vertex AI Embeddings (`text-embedding-005`)**:
   - 768-dimensional dense vector embeddings providing cosine-similarity semantic search across books and mood vibes.
3. **Google Cloud Storage (GCS)**:
   - Bucket `gs://thistle-and-page-assets-9683cc` hosting generated book illustrations and bookmarks with public HTTPS endpoints.
4. **Vertex AI Memory Bank**:
   - Durable long-term memory capturing reader pace, active library cards, and walking/driving transit tolerances.

---

## 3. Data Flow & Security Model

1. **Zero GCP Credentials in Browser**: The browser speaks standard HTTPS/JSON with bearer tokens only to the Cloud Run proxy.
2. **Application Default Credentials (ADC)**: The Cloud Run proxy authenticates to Vertex AI Agent Platform using service account tokens refreshed per request.
3. **Session & Shelf Scoping**: No user can mutate or inspect another reader's active holds or borrowing schedule without explicit user ID matching in Firestore.
