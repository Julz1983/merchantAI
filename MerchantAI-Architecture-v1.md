# MerchantAI — Platform Architecture (v1.0)
**Status:** Draft for approval — no implementation until sign-off
**Prepared as:** CTO-level architecture package
**Scope:** Everything requested in the brief, plus explicit pushback where the brief's defaults would create technical debt

---

## 0. CTO Notes — Where I'm Pushing Back On The Brief

Before the architecture: four decisions in the brief I'm overriding or narrowing, because building them as-written either kills the 6–8 week MVP timeline or bakes in debt we'd pay for later.

| # | Brief says | Problem | Recommendation |
|---|---|---|---|
| 1 | Knowledge Graph as its own system alongside Postgres + Qdrant | A third database (Neo4j/graph DB) in a 6-8 week MVP is a scope killer — new ops burden, new query language, new failure mode, for a graph that's still small per tenant (thousands of nodes, not billions). | Model the KG as **typed edge tables in Postgres** (`kg_nodes`, `kg_edges`) with recursive CTEs for traversal. It's relationally correct, it's one database to operate, and it migrates cleanly to Neo4j/AGE later if a tenant's graph gets large enough that recursive CTEs become the bottleneck (Scaling section covers the trigger for that migration). |
| 2 | "Support CSV, Excel, XML, JSON" for product import in MVP | Four import formats plus validation/mapping UI per format is 3-4 weeks of work on its own. | MVP ships **CSV + XLSX only** (one parser, both are tabular) with a column-mapping UI. JSON/XML land in the module immediately after MVP — the import engine is built as a pluggable parser interface from day one so this is additive, not a rewrite. |
| 3 | Full Analytics Dashboard + Knowledge Graph Viewer as MVP dashboard features | Both are real product surfaces (graph visualization libraries, event pipelines, aggregation jobs) — each is 1-2 weeks alone. | MVP ships a **read-only KG viewer** (list + simple force-directed view of one product's neighborhood, not full-graph explorer) and a **minimal analytics view** (counts + a table, not charts/cohorts). Both are structured so the data model doesn't change when we build the "real" version later — we're only trimming UI polish, not the underlying event/graph schema. |
| 4 | "AI Prompt Settings" exposed per-merchant in MVP | Free-text system-prompt editing per tenant is a prompt-injection and brand-risk surface (a merchant could make the assistant say anything, including things that look like MerchantAI's own liability). | MVP exposes **structured tone/persona settings** (formal/casual, categories to emphasize, upsell aggressiveness) that get composed into a fixed, audited system-prompt template — not raw prompt text. Raw system-prompt override becomes an Enterprise-tier, reviewed feature later. |

Everything else in the brief is built as specified. The rest of this document assumes the four changes above.

---

## 1. Architecture Overview

MerchantAI is a multi-tenant SaaS composed of five logically separate engines behind one API, plus two frontends and an embeddable widget:

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Merchants' Websites                         │
│                    <script src="merchantai.js">                      │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │ (widget, apps/widget)
┌────────────────────────────────▼──────────────────────────────────────┐
│                         apps/dashboard (Next.js)     apps/widget (JS)  │
└────────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTPS / JWT / API key
┌────────────────────────────────▼──────────────────────────────────────┐
│                           apps/api (FastAPI)                          │
│  ┌───────────┐ ┌───────────┐ ┌────────────┐ ┌───────────┐ ┌────────┐ │
│  │   Auth &   │ │  Import   │ │ Knowledge  │ │    AI     │ │Analytics│ │
│  │  Tenancy   │ │  Engine   │ │  Engine    │ │  Engine   │ │ Engine  │ │
│  └───────────┘ └───────────┘ └────────────┘ └───────────┘ └────────┘ │
└──────┬──────────────┬──────────────┬──────────────┬──────────────┬───┘
       │              │              │              │              │
  ┌────▼────┐   ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐  ┌────▼────┐
  │Postgres │   │  Qdrant   │  │  Postgres │  │  OpenAI / │  │  Redis  │
  │(tenant  │   │ (vectors, │  │ (KG nodes │  │  Claude   │  │ (cache, │
  │ data)   │   │per-tenant │  │  & edges) │  │ (abstracted│  │ queues, │
  │         │   │collection)│  │           │  │  via LLM  │  │ sessions)│
  │         │   │           │  │           │  │  gateway) │  │         │
  └─────────┘   └───────────┘  └───────────┘  └───────────┘  └─────────┘
```

**Five engines, one API surface:**

- **Import Engine** — parses product/document files, normalizes into the catalogue schema, triggers embedding + KG extraction jobs.
- **Knowledge Engine** — owns the KG (nodes/edges) and the hybrid retrieval logic (vector + graph) that the AI Engine calls.
- **AI Engine** — RAG orchestration: takes a user question, calls Knowledge Engine for context, calls the LLM gateway, returns a cited, structured answer.
- **Analytics Engine** — ingests events (async, via Redis queue) and serves aggregates.
- **Auth & Tenancy** — issues JWTs, resolves API keys to `merchant_id`, enforces row-level isolation on every query.

Every engine is a Python package under `apps/api/engines/*`, imported by FastAPI routers — not separate services. This is a **modular monolith**, deliberately, for the reasons in the Deployment Strategy section (§12).

---

## 2. Monorepo Folder Structure

```
merchantai/
├── apps/
│   ├── dashboard/                 # Next.js merchant admin app
│   │   ├── src/
│   │   │   ├── app/               # App Router: /login, /products, /documents,
│   │   │   │                      #   /knowledge-graph, /analytics, /settings,
│   │   │   │                      #   /widget-settings, /api-keys
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── lib/               # api client, auth helpers
│   │   │   └── styles/
│   │   └── package.json
│   │
│   ├── widget/                    # Embeddable chat widget (vanilla TS, no framework
│   │   │                          #   runtime dependency — must be <50kb gzipped)
│   │   ├── src/
│   │   │   ├── init.ts            # MerchantAI.init({ apiKey })
│   │   │   ├── launcher/
│   │   │   ├── chat/
│   │   │   └── theme/             # reads merchant branding from /widget/config API
│   │   └── build/                 # outputs merchantai.js (single bundle, CDN-hosted)
│   │
│   └── api/                       # FastAPI backend
│       ├── main.py
│       ├── core/
│       │   ├── config.py
│       │   ├── security.py        # JWT, API key resolution, tenant context
│       │   └── db.py
│       ├── routers/               # thin — one file per REST resource (§6)
│       ├── engines/
│       │   ├── auth_tenancy/
│       │   ├── import_engine/
│       │   │   ├── parsers/       # csv.py, xlsx.py (json.py, xml.py post-MVP)
│       │   │   └── document_pipeline/  # extract -> chunk -> embed
│       │   ├── knowledge_engine/
│       │   │   ├── kg_repository.py
│       │   │   ├── kg_extraction.py    # LLM-assisted relationship extraction
│       │   │   └── hybrid_retrieval.py # vector + graph fusion
│       │   ├── ai_engine/
│       │   │   ├── llm_gateway.py      # provider abstraction (OpenAI/Claude)
│       │   │   ├── rag_pipeline.py
│       │   │   └── prompt_templates/
│       │   └── analytics_engine/
│       │       ├── event_ingest.py
│       │       └── aggregations.py
│       ├── models/                # SQLAlchemy models
│       ├── schemas/                # Pydantic request/response models
│       ├── migrations/            # Alembic
│       └── tests/
│
├── packages/
│   ├── shared/                    # cross-app TS utilities (formatting, constants)
│   ├── ui/                        # shared React component library (dashboard + future admin tools)
│   ├── types/                     # shared TS types generated from OpenAPI schema
│   └── knowledge-engine/          # TS types + client helpers for KG shape, shared
│                                   #   between dashboard's graph viewer and widget
│
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── nginx/
│
├── docs/
│   └── architecture/              # this document and its successors
│
└── .github/workflows/             # CI: lint, test, build per app
```

Key structural decision: **`packages/knowledge-engine` is TypeScript** (types + thin client) while the actual KG logic lives in `apps/api/engines/knowledge_engine` (Python). The package exists so the dashboard's graph viewer and the widget share one typed contract for node/edge shapes instead of hand-copying interfaces.

---

## 3. Database Schema

Single Postgres database, **shared schema, isolated by `merchant_id`** on every tenant-scoped table (see §14 for why not schema-per-tenant). All tenant tables carry `merchant_id UUID NOT NULL REFERENCES merchants(id)` and a Postgres Row-Level Security policy scoped to it.

```sql
-- ── Tenancy ──────────────────────────────────────────────
merchants (
  id UUID PK,
  name TEXT,
  slug TEXT UNIQUE,
  logo_url TEXT,
  brand_colors JSONB,           -- { primary, secondary, accent }
  ai_persona JSONB,             -- structured prompt settings, see §0.4
  status TEXT,                  -- trial | active | suspended
  created_at, updated_at
)

users (
  id UUID PK,
  merchant_id UUID FK,
  email TEXT,
  password_hash TEXT,
  role TEXT,                    -- owner | admin | editor | viewer
  created_at
)

api_keys (
  id UUID PK,
  merchant_id UUID FK,
  key_hash TEXT,                -- store hash, never plaintext
  label TEXT,
  scopes TEXT[],                -- widget | admin | analytics
  last_used_at, created_at, revoked_at
)

-- ── Catalogue ────────────────────────────────────────────
brands (id UUID PK, merchant_id FK, name TEXT)

categories (
  id UUID PK, merchant_id FK, name TEXT,
  parent_id UUID FK REFERENCES categories(id)   -- self-referential tree
)

products (
  id UUID PK,
  merchant_id UUID FK,
  sku TEXT,
  name TEXT,
  description TEXT,
  category_id UUID FK,
  brand_id UUID FK,
  price NUMERIC,
  currency TEXT,
  images JSONB,                 -- array of URLs
  product_url TEXT,
  specifications JSONB,         -- free-form key/value
  attributes JSONB,
  stock_status TEXT,
  embedding_id TEXT,            -- pointer to Qdrant point id
  created_at, updated_at,
  UNIQUE (merchant_id, sku)
)

-- ── Documents / RAG ──────────────────────────────────────
documents (
  id UUID PK, merchant_id FK,
  title TEXT, doc_type TEXT,    -- installation_guide | technical_sheet | manual | faq
  source_file_url TEXT,
  status TEXT,                  -- processing | ready | failed
  created_at
)

document_chunks (
  id UUID PK, document_id FK, merchant_id FK,
  chunk_index INT,
  content TEXT,
  embedding_id TEXT,            -- pointer to Qdrant point id
  metadata JSONB                -- page number, section heading
)

-- ── Knowledge Graph (Postgres-native, see §0 rationale) ──
kg_nodes (
  id UUID PK, merchant_id FK,
  node_type TEXT,                -- PRODUCT | CATEGORY | BRAND | DOCUMENT | PROJECT | ATTRIBUTE
  ref_id UUID,                   -- FK to products.id / documents.id / categories.id, nullable for abstract nodes
  label TEXT,
  metadata JSONB
)

kg_edges (
  id UUID PK, merchant_id FK,
  source_node_id UUID FK REFERENCES kg_nodes(id),
  target_node_id UUID FK REFERENCES kg_nodes(id),
  relationship_type TEXT,        -- REQUIRES | OPTIONAL | ALTERNATIVE | COMPATIBLE_WITH |
                                  -- NOT_COMPATIBLE_WITH | INSTALLED_WITH | PART_OF_PROJECT |
                                  -- USED_BY | CATEGORY | BRAND | DOCUMENT | ACCESSORY
  weight FLOAT DEFAULT 1.0,      -- confidence / relevance, used to rank traversal
  source TEXT,                   -- 'import' | 'llm_extracted' | 'manual'
  created_at
)
-- Index: (merchant_id, source_node_id, relationship_type), (merchant_id, target_node_id)

-- ── Chat / Conversations ─────────────────────────────────
chats (
  id UUID PK, merchant_id FK,
  session_id TEXT,               -- anonymous widget session, no PII required
  started_at, ended_at
)

chat_messages (
  id UUID PK, chat_id FK, merchant_id FK,
  role TEXT,                     -- user | assistant
  content TEXT,
  citations JSONB,               -- products/documents/kg-paths used to answer
  created_at
)

-- ── Analytics ─────────────────────────────────────────────
analytics_events (
  id UUID PK, merchant_id FK,
  event_type TEXT,               -- question | recommendation | click | product_found |
                                  -- product_missing | document_used | kg_path_used | conversion
  chat_id UUID FK NULL,
  payload JSONB,
  created_at
)
-- Partitioned by created_at (monthly) once volume warrants it — see §15

-- ── Settings ──────────────────────────────────────────────
widget_settings (
  merchant_id UUID PK FK,
  launcher_position TEXT,
  greeting_message TEXT,
  theme_overrides JSONB
)
```

**Why not a graph database for the KG:** see §0.1. The recursive-CTE approach handles multi-hop traversal (e.g., "decking → requires → joists → compatible_with → fixings") cleanly up to the depth this use case needs (3-4 hops). Indexes on `(merchant_id, source_node_id, relationship_type)` keep this fast per-tenant.

**Why Qdrant stores an `embedding_id` pointer rather than the vector itself in Postgres:** keeps Postgres small and fast for relational queries, keeps Qdrant doing what it's good at (ANN search), and each is independently scalable. One Qdrant **collection per merchant** (not one global collection with a `merchant_id` filter) — this is a deliberate isolation choice, covered in §14.

---

## 4. Knowledge Graph Design

**Node types:** `PRODUCT`, `CATEGORY`, `BRAND`, `DOCUMENT`, `PROJECT` (e.g., "Garden Projects", "Outdoor Living"), `ATTRIBUTE` (e.g., "Coastal Areas", "Children's Play Areas" — reusable tags, not free text, so they compose across products).

**Edge types and their semantics:**

| Relationship | Direction | Meaning | Example |
|---|---|---|---|
| `REQUIRES` | A→B | A cannot function without B | Decking → Joists |
| `OPTIONAL` | A→B | B enhances A but isn't required | Decking → Lighting |
| `ALTERNATIVE` | A↔B | B substitutes for A (symmetric) | Composite Decking ↔ Timber Decking |
| `COMPATIBLE_WITH` | A↔B | Confirmed to work together | Fixing Type X ↔ Joist Type Y |
| `NOT_COMPATIBLE_WITH` | A↔B | Explicitly incompatible — critical for avoiding bad recommendations | Certain sealants ↔ certain membranes |
| `INSTALLED_WITH` | A→B | Installation dependency, distinct from physical requirement | Decking → Fixing method |
| `PART_OF_PROJECT` | A→PROJECT | Groups products under a use-case | Decking → "Garden Projects" |
| `USED_BY` | PRODUCT→ATTRIBUTE | Suitability tagging | Decking → "Coastal Areas" |
| `CATEGORY` | PRODUCT→CATEGORY | Taxonomy membership | |
| `BRAND` | PRODUCT→BRAND | | |
| `DOCUMENT` | PRODUCT→DOCUMENT | Links a product to its installation/tech doc | |
| `ACCESSORY` | A→B | B is a recommended add-on for A | Decking → Edging |

**How the graph gets built (no manual graph-authoring required for MVP):**

1. **Deterministic edges from import data** — `CATEGORY`, `BRAND`, `DOCUMENT` edges are created automatically from the product import fields (zero LLM cost, zero error rate).
2. **LLM-assisted extraction for semantic edges** — `REQUIRES`, `ALTERNATIVE`, `ACCESSORY`, `COMPATIBLE_WITH` etc. are proposed by an extraction job that reads product descriptions/specs/attached documents and outputs candidate edges with a confidence `weight`. **These are queued for merchant review in the dashboard before going live** — this is the single highest-risk part of the system for hallucinated relationships (e.g., inventing a false `COMPATIBLE_WITH`), so nothing LLM-extracted is auto-published in MVP.
3. **Manual edges** — merchants can add/correct edges directly in the KG viewer.

**Hybrid retrieval (used by the AI Engine, §8):** for a query, the Knowledge Engine runs vector search (Qdrant) to find semantically relevant products/chunks, then expands each hit 1-2 hops through `kg_edges` to pull in requirements/accessories/alternatives that the raw text match wouldn't surface. Results are merged and re-ranked before being handed to the LLM as context.

---

## 5. Entity Relationship Diagram (textual)

```
merchants 1───∞ users
merchants 1───∞ api_keys
merchants 1───∞ categories (self-referential tree via parent_id)
merchants 1───∞ brands
merchants 1───∞ products ───∞ (category_id → categories, brand_id → brands)
merchants 1───∞ documents 1───∞ document_chunks
merchants 1───∞ kg_nodes ───∞ kg_edges (source_node_id, target_node_id → kg_nodes)
  kg_nodes.ref_id ─── (polymorphic) ───> products.id | documents.id | categories.id
merchants 1───∞ chats 1───∞ chat_messages
merchants 1───∞ analytics_events (chat_id → chats, nullable)
merchants 1───1 widget_settings
```

Every arrow starting at `merchants` is the tenant-isolation boundary enforced by Postgres RLS (§13).

---

## 6. REST API Specification

Base path: `/api/v1`. Auth: `Authorization: Bearer <JWT>` for dashboard, `X-API-Key` for widget (scoped, rate-limited, read+chat only).

**Auth**
- `POST /auth/login` `POST /auth/refresh` `POST /auth/logout`
- `GET /auth/me`

**Products**
- `GET /products` (paginated, filterable by category/brand/stock)
- `POST /products` `GET /products/{id}` `PATCH /products/{id}` `DELETE /products/{id}`
- `POST /products/import` — multipart upload, returns `import_job_id`
- `GET /products/import/{job_id}` — status/progress/error report

**Documents**
- `GET /documents` `POST /documents` (upload) `GET /documents/{id}` `DELETE /documents/{id}`
- `GET /documents/{id}/status` — processing pipeline status

**Knowledge Graph**
- `GET /kg/nodes/{node_id}` — node + immediate edges
- `GET /kg/nodes/{node_id}/neighborhood?depth=2`
- `GET /kg/edges/pending` — LLM-proposed edges awaiting review
- `POST /kg/edges/{id}/approve` `POST /kg/edges/{id}/reject`
- `POST /kg/edges` (manual create) `DELETE /kg/edges/{id}`

**Chat (widget-facing, API-key auth)**
- `POST /chat/message` — `{ session_id, message }` → `{ reply, citations[], suggested_products[] }`
- `GET /chat/{session_id}/history`

**Analytics**
- `GET /analytics/summary?range=`
- `GET /analytics/events?type=&range=`

**Widget**
- `GET /widget/config` — API-key scoped, returns branding + settings (public-safe fields only)

**Settings**
- `GET/PATCH /settings/merchant`
- `GET/PATCH /settings/ai-persona`
- `GET/PATCH /settings/widget`

**API Keys**
- `GET /api-keys` `POST /api-keys` `DELETE /api-keys/{id}`

Every response envelope: `{ data, meta: { request_id }, error: null }` — consistent shape simplifies the shared TS client in `packages/types`.

---

## 7. Widget Architecture

- **Delivery:** one script tag, one bundled file (`merchantai.js`), CDN-hosted, versioned (`merchantai.js?v=1.2.0`) with a rolling deprecation window so merchants aren't broken by pushes.
- **No framework runtime shipped to the host page** — vanilla TS compiled to a small IIFE, to avoid React-version collisions with the merchant's own site and to hit the <50kb budget.
- **Isolation:** renders inside a Shadow DOM root so merchant site CSS can't leak in/out.
- **Init flow:** `MerchantAI.init({ apiKey })` → widget calls `GET /widget/config` → renders launcher with merchant branding → on open, establishes a `session_id` (stored in-memory + `sessionStorage` on the *merchant's* domain, not ours) → messages go through `POST /chat/message`.
- **Fallback/resilience:** if `/widget/config` fails, the widget renders a minimal default-branded launcher rather than not rendering at all — a merchant's site should never break because MerchantAI is down.
- **Streaming:** chat responses stream via SSE for perceived latency; citations arrive as a final structured block once the stream closes.

---

## 8. AI Architecture

```
User message
   │
   ▼
RAG Pipeline (ai_engine/rag_pipeline.py)
   │
   ├─► Knowledge Engine: hybrid_retrieval(query, merchant_id)
   │      ├─ Qdrant vector search (products + document_chunks, tenant collection)
   │      └─ KG expansion (1-2 hop traversal from top vector hits via kg_edges)
   │      └─► merged, re-ranked context set (products, chunks, kg paths)
   │
   ├─► Prompt assembly: system template (persona settings, §0.4) + retrieved context
   │      + explicit instruction: "only state what's in the provided context; if
   │      information isn't present, say so and offer to connect the customer with
   │      the merchant — never invent a product, spec, or compatibility claim"
   │
   ├─► LLM Gateway (provider-agnostic interface: generate(messages, tools) )
   │      — OpenAI GPT for MVP, same interface swaps to Claude without touching
   │        rag_pipeline.py or prompt_templates
   │
   └─► Response parsing: extract cited product IDs / document IDs / kg-edge IDs
          → validated against what was actually retrieved (reject/strip any
            citation the model invents that wasn't in the context set)
          → structured response: { reply, citations[], suggested_products[],
            shopping_list_delta[] }
```

**Grounding enforcement is structural, not just prompted:** every citation the model emits is checked against the retrieved-context set server-side before the response leaves the API. A citation that doesn't map to a real retrieved item is dropped rather than shown — this is the concrete implementation of "never hallucinate" from the brief, rather than relying on the model to police itself.

**LLM Gateway abstraction (`llm_gateway.py`):** single interface `generate(system, messages, tools=None) -> LLMResponse`, with `OpenAIProvider` and `AnthropicProvider` implementations. Provider selection is a per-merchant config value (future: merchants on Enterprise tier could choose), defaulting to OpenAI GPT for MVP per the brief.

**Embeddings:** `text-embedding-3-large`, chunked at ~500 tokens with 15% overlap for documents; products embed a composed string of `name + description + category + attributes` (not raw JSON) so semantic search matches how customers actually phrase questions.

---

## 9. User Journeys

**Journey A — Merchant onboarding (dashboard, first-time admin)**
1. Sign up → merchant record created, trial status.
2. Branding step: logo, colors → widget preview updates live.
3. Product import: upload CSV/XLSX → column mapping UI → validation report → confirm → import job runs async, progress bar.
4. Document import: upload PDFs → auto-processing (extract/chunk/embed) status shown per file.
5. KG auto-build runs in background; dashboard shows "Knowledge Graph: 340 relationships found, 12 pending your review."
6. Merchant reviews pending edges (approve/reject in bulk or individually).
7. Widget settings: position, greeting, get embed snippet.
8. Copy snippet → paste into their site → live.

**Journey B — End customer (widget, on merchant's site)**
1. Sees floating launcher, branded to the merchant.
2. Opens, asks: *"I want to build a raised deck."*
3. Assistant streams a grounded answer: recommends decking products (with why), flags required accessories (joists, fixings, membrane) via KG `REQUIRES` edges, offers `ALTERNATIVE` materials, links the manufacturer installation guide (RAG doc hit).
4. Customer clicks a suggested product → `click` + `product_found` analytics events fire → customer lands on the merchant's actual product page.
5. Assistant offers to build a shopping list from the conversation (data model supports this now — full "Basket Builder" UI is a post-MVP module per the roadmap, brief §"Future modules").

**Journey C — Merchant reviewing analytics**
1. Dashboard → Analytics: sees question volume, top "product missing" queries (i.e., demand signal for products they don't stock — a genuine merchandising insight), documents most cited, conversion events.

---

## 10. UI Wireframes (textual layout — Stripe/Linear/Vercel/Notion-inspired: generous whitespace, single accent color, no decorative chrome)

**Dashboard shell**
```
┌──────────────────────────────────────────────────────────┐
│ [Logo]  Merchant Name                    [Avatar ▾]      │
├───────────┬────────────────────────────────────────────────┤
│ Overview  │                                                │
│ Products  │              Main content area                 │
│ Documents │                                                │
│ Knowledge │                                                │
│  Graph    │                                                │
│ Analytics │                                                │
│ Widget    │                                                │
│ API Keys  │                                                │
│ Settings  │                                                │
└───────────┴────────────────────────────────────────────────┘
```

**Product import screen** — dropzone → column-mapping table (source column → target field, dropdown per row) → validation summary (X rows valid, Y warnings, Z errors with reasons) → confirm button.

**KG review screen** — card list, one per pending edge: `[Product A] --REQUIRES--> [Product B]` with confidence %, source snippet that justified it, Approve/Reject/Edit buttons.

**Widget (customer-facing)**
```
                                            ┌───────────────────┐
                                            │ Merchant Name   ✕ │
                                            ├───────────────────┤
                                            │ Assistant message  │
                                            │ [product card]     │
                                            │ [product card]     │
                                            │                     │
                                            │ You: ...            │
                                            ├───────────────────┤
                                            │ [type a message] ➤│
                                            └───────────────────┘
                                                        ⬤ ← launcher
```

---

## 11. Development Roadmap (6–8 weeks to demo)

| Week | Focus | Exit criteria |
|---|---|---|
| 1 | Foundations: monorepo scaffold, Postgres schema + migrations, auth/tenancy, Docker Compose local env | Can log in, JWT-authed, empty dashboard shell deployed |
| 2 | Product import (CSV/XLSX) + catalogue CRUD + dashboard product list/detail | Merchant can import a real catalogue and see it in the dashboard |
| 3 | Document import pipeline (extract → chunk → embed → Qdrant) | Uploaded PDF is searchable via a test vector query |
| 4 | Knowledge Graph: schema, deterministic edge generation, LLM extraction job, review UI | Importing a catalogue produces a reviewable graph |
| 5 | AI Engine: hybrid retrieval + RAG pipeline + LLM gateway + citation validation | API can answer a grounded question with real citations via Postman |
| 6 | Widget: build, branding, embed snippet, SSE streaming chat, connect to real API | Widget embedded on a test static site, working end-to-end |
| 7 | Analytics (event capture + minimal dashboard view), widget settings, API keys UI | Full loop demonstrable: import → graph → ask → click → see it in analytics |
| 8 | Hardening: RLS audit, rate limiting, error states, demo polish, seed data for JP Corry-style demo catalogue | Demo-ready with one seeded merchant, deployed to staging |

This assumes one small team (2-3 engineers) working full-time; it's tight, and week 8 is explicitly buffer/hardening rather than new features — if week 4 or 5 slips, the first thing to cut is the analytics dashboard (ship raw event counts via API only, no UI) rather than compressing the KG or RAG work, since those are the actual product differentiators.

---

## 12. Deployment Strategy

**MVP/staging:** Docker Compose, single host (or small managed VM cluster) — `api`, `dashboard`, `postgres`, `qdrant`, `redis`, `nginx` as reverse proxy/TLS terminator. This matches the brief's "Docker Compose" infra requirement and is the right level of complexity for a pre-revenue MVP.

**Why a modular monolith, not microservices, for MVP:** five "engines" as described in §1 map to team mental model, not to five deployable services. Splitting them into separate services now would mean five sets of CI/CD, five sets of inter-service auth, network latency between engines that currently call each other as plain function calls — all cost, no benefit, at this scale. The engines are built as clean internal Python packages specifically so that **any one of them can be extracted into its own service later without a rewrite**, if and when its resource profile diverges enough to justify it (most likely candidate: the Import Engine's document processing, which is CPU/IO-bound in bursts — see §15).

**CI/CD:** GitHub Actions — lint/typecheck/test on PR, build+push Docker images on merge to `main`, deploy to staging automatically, production deploy is a manual promotion step.

**Environments:** local (Compose) → staging → production. Same Compose-based topology for staging and initial production; production migrates to managed services (RDS/Cloud SQL for Postgres, managed Qdrant Cloud, managed Redis) as soon as there's paying-customer uptime pressure — swapping a connection string, not an architecture change, because nothing above the DB layer knows or cares whether Postgres is self-hosted or managed.

---

## 13. Security Model

- **Tenant isolation:** Postgres Row-Level Security policy on every tenant table (`USING (merchant_id = current_setting('app.current_merchant_id')::uuid)`), set per-request from the resolved JWT/API key — isolation enforced at the database layer, not just in application query filters, so a missed `WHERE merchant_id = ...` in application code can't leak cross-tenant data.
- **Auth:** JWT (short-lived access token + refresh token) for dashboard users; separate scoped API keys (hashed at rest, never logged in plaintext) for widget/public-facing calls, with per-key rate limiting.
- **Widget API keys are read/chat-scoped only** — they can never write, import, or read another merchant's config; they resolve to exactly one `merchant_id` server-side.
- **Secrets:** environment-injected, never committed; separate secrets per environment.
- **Prompt-injection surface:** the widget accepts arbitrary customer text into the RAG pipeline — the system prompt and retrieval-grounding/citation-validation (§8) are the primary defense; additionally, LLM output is never used to construct SQL, file paths, or executed as code.
- **File upload safety:** product/document imports are size-limited, type-validated, scanned before processing; document text extraction runs in a sandboxed worker, not inline in the request path.
- **Transport:** TLS everywhere, HSTS, widget served only over HTTPS.
- **Audit trail:** KG edge approve/reject and settings changes are logged with `user_id` + timestamp for accountability (a merchant's AI recommending an incompatible product is a real liability question — we need to know who approved the edge that caused it).

---

## 14. Multi-Tenant Strategy

- **Database:** shared schema + `merchant_id` column + RLS, not schema-per-tenant or database-per-tenant. At "thousands of merchants," schema-per-tenant means thousands of schemas to migrate on every deploy — an operational tax with no isolation benefit RLS doesn't already provide. Database-per-tenant is reserved for a future Enterprise/dedicated tier if a specific customer contractually requires physical data isolation.
- **Vectors:** one Qdrant **collection per merchant** — unlike Postgres, Qdrant collections are cheap to create and this gives us per-tenant delete/export/resize without touching anyone else's data, and avoids one tenant's catalogue size affecting another's query latency.
- **Branding/config:** fully data-driven from `merchants`/`widget_settings` — nothing merchant-specific in code, per the brief's explicit requirement.
- **AI persona:** structured settings composed into a shared prompt template (§0.4) — every merchant gets the same guardrails, differing only in tone/emphasis, not in whether grounding/citation rules apply.
- **Rate limiting & quotas:** per-`merchant_id` and per-API-key, enforced in Redis, so one merchant's traffic spike can't degrade another's widget response time.
- **Onboarding is self-serve from day one** — the schema and import pipeline never assume "we set this merchant up manually," even though the first four customers (JP Corry, Haldane Fisher, Murdock, MacBlair) will likely get white-glove onboarding help in practice.

---

## 15. Future Scaling Strategy

Trigger-based, not speculative — each of these is a response to a specific signal, not built preemptively:

| Signal | Response |
|---|---|
| A tenant's KG traversal queries (recursive CTEs) show up in slow-query logs / p95 latency degrades | Migrate that tenant's KG to a dedicated graph engine (Apache AGE extension on Postgres first — same DB, graph query language — before considering a separate Neo4j deployment) |
| Document processing (extract/chunk/embed) becomes a bottleneck under import bursts | Extract Import Engine's document pipeline into its own worker service with its own queue (Redis/Celery already in place, just add horizontal workers) |
| `analytics_events` table grows past comfortable single-table size | Time-based partitioning (already planned in schema comments, §3) then move cold partitions to cheaper storage / a warehouse (e.g., ClickHouse) for historical analytics, keep hot data in Postgres |
| Read load on Postgres grows beyond one primary | Read replicas for dashboard/analytics read paths; writes stay on primary |
| A large enterprise customer requires physical data isolation | Database-per-tenant available as an Enterprise-tier deployment option, using the same schema/migrations — this is why we never denormalize around "shared DB" assumptions in application code |
| Widget traffic grows globally | CDN edge caching for `/widget/config` (public-safe, cacheable), multi-region API deployment behind a global load balancer |
| Need for the roadmap's future modules (Basket Builder, Quote Builder, Branch Stock Lookup, ERP integrations, plugins) | Each is additive on top of the existing engine boundaries — e.g., Basket Builder reads `chat_messages`/`kg_edges` data that already exists; ERP/Magento/Shopify integrations become new Import Engine parsers plus new webhook-receiving routers, not new architecture |

The through-line: nothing above requires re-architecting the core (schema, engine boundaries, tenancy model). Every scaling step is "add a component" or "swap an implementation behind an existing interface," never "rewrite."

---

## Sign-off Needed On

1. The four pushbacks in §0 (KG-in-Postgres, CSV/XLSX-only import, trimmed analytics/KG-viewer UI, structured AI persona instead of raw prompt editing).
2. The 8-week roadmap and its stated cut-order if a week slips.
3. Modular-monolith deployment approach (vs. microservices) for MVP.

Once confirmed, implementation proceeds one feature at a time per the roadmap in §11, starting with Week 1 (foundations).
