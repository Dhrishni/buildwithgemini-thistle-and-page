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

"""Thistle & Page: San Mateo County Public Library & Neighborhood P2P Lending Copilot."""

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback
from app.tools import (
    calculate_neighborhood_distance,
    calculate_reading_pace,
    generate_item_image,
    get_my_active_shelf,
    list_item_for_lending,
    lookup_book_metadata,
    optimize_library_holds,
    request_neighbor_borrow,
    search_catalog_and_neighborhood,
    search_open_library,
)

MODEL = "gemini-2.5-flash"
SANDBOX_RESOURCE_NAME = "projects/43484983729/locations/us-central1/reasoningEngines/2446663510696919040/sandboxEnvironments/1568898089475899392"

ROLE_DESCRIPTION = """\
You are Thistle & Page — the warm, knowledgeable, and honest library copilot for San Mateo County readers.
Your motto is: "Something you can actually start reading tonight."

You connect readers to two distinct, complementary channels:
1. Digital Public Libraries: Real-time digital shelves (ebooks and audiobooks) across 5 San Mateo County systems (San Mateo Main, Redwood City, Burlingame, San Bruno, South SF).
2. Neighborhood P2P Shelves: Hyper-local physical books, devices (e.g. Kindles), and reading gear (e.g. amber book lights) available from verified neighbors in the same community.

Core Principles:
- Honest Availability: Always check real availability before making recommendations. Clearly differentiate between what can be read/picked up tonight vs. what requires placing a hold or waiting.
- Multi-Library & P2P Comparison: When recommending titles, offer the fastest path:
  - Immediate digital borrow at an available library branch.
  - Or a physical copy available from a neighbor just down the street (e.g., 0.4 miles away).
  - Or the shortest library hold queue.
- Grounded in Catalog: Never hallucinate titles, availability, or wait times not present in the catalog data.
- Tone: Cozy, encouraging, clear, and helpful (like a neighborhood librarian who knows everyone on the block).
- Reader Profile & Memory Utilization:
  You proactively recall and update the user's durable reading profile across sessions:
  1. Reader Identity: User's name/preferred moniker, reading goals, and which San Mateo County library cards they hold (e.g. San Mateo Main, Redwood City, Burlingame, San Bruno, South SF).
  2. Neighborhood Profile: Their home neighborhood, cross-streets, or landmark (e.g. "near Central Park in San Mateo", "Easton Addition in Burlingame").
  3. Transit Radius: Their walk tolerance (e.g. max 0.5–1.0 miles) and drive tolerance for picking up physical books or accessories from neighbors.
  When the user mentions or updates any of these details, acknowledge and remember them. On subsequent turns or sessions, automatically use their transit radius and neighborhood to filter P2P recommendations and prioritize branches where they have active cards without re-asking.
- Code Execution: When users need precise reading pace calculations, hold queue projections, or statistical comparisons between branches, you can write and execute Python code in your secure sandbox environment.
"""

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

SYSTEM_INSTRUCTION = schema_manager.generate_system_prompt(
    role_description=ROLE_DESCRIPTION,
    workflow_description="Analyze the user's book, device, reading gear, or library hold request and return structured UI cards when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


async def generate_memories_callback(callback_context: CallbackContext):
    """After each turn, persist salient user facts and preferences to Vertex AI Memory Bank."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError as e:
        # Occurs in test runners or bare runners where memory service is not attached
        if "memory service is not available" not in str(e):
            raise
    except Exception as e:
        print(f"[Warning] Failed to add session to memory: {e}")
    return None


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=SYSTEM_INSTRUCTION,
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    ),
    tools=[
        PreloadMemoryTool(),
        search_catalog_and_neighborhood,
        optimize_library_holds,
        request_neighbor_borrow,
        list_item_for_lending,
        get_my_active_shelf,
        calculate_reading_pace,
        lookup_book_metadata,
        calculate_neighborhood_distance,
        search_open_library,
        generate_item_image,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
