# indigoai_assignment

## Part 1: AI Assisted Coding

### 1. Current Workflow: How do you currently use AI tools (e.g., ChatGPT, Cursor, Claude, MCPs, Agents) to assist or generate code? Do you use them differently for AI-specific tasks (e.g., designing a RAG pipeline) versus general backend work?

AI tools haven’t quite reached the stage where they can work independently; they perform much better when given clear context. That said, they can still be very effective for brainstorming when provided with a specific task. The AI tools I use most for now are ChatGPT and GitHub Copilot, which I use within a custom pipeline I developed. This setup allows me to achieve results comparable to those using Claude, while consuming significantly fewer credits.

I regularly use AI to generate boilerplate code, suggest improvements, refactor and debug, and even analyze entire codebases. I also rely on AI for exploration and simulation—and, ultimately, to help generate income.

In general, tasks that rely purely on AI tend to require more validation and experimentation. In contrast, backend-related work benefits more from speed and the reuse of established patterns.

---

### 2. The Good & The Bad: Where do you see the biggest value in AI-assisted development? What are the current limitations or risks, especially when building systems that will themselves be consumed by AI agents?

I can focus more on architecture rather than remembering and writing everything by hand, and my debugging speed has improved dramatically; if I need to analyze an entire codebase, I can do that immediately. 

The biggest value AI provides is speed and leverage, reducing time spent on boilerplate and context switching, along with enabling rapid exploration of different approaches and amplifying knowledge when working across unfamiliar stacks. However, there are important limitations and risks: AI-generated code often has shallow correctness, appearing right while missing edge cases; it can lose broader system context; and there is a real risk of over-trusting outputs, especially when building systems for AI agents where small ambiguities can cascade into unpredictable behavior. 

Additionally, evaluating AI-driven systems like RAG pipelines or agents is still difficult due to their non-deterministic nature. As a result, when building systems consumed by AI, robustness, observability, and clear interfaces become more critical than simply producing working code.

---

### 3. The Future: How do you envision your role as an AI Solutions Engineer evolving over the next few years? What skills do you think will matter most as LLMs get better at writing code?

I see my role evolving from writing code to designing systems, with a stronger focus on orchestration, behavior definition, and how different components interact. This means shifting from implementation to orchestration and evaluation, from writing logic to defining behavior and guardrails, and from building features to designing reliable AI interactions. 

The most important skills will be system design—especially AI-native architectures like RAG and agents—along with prompt and interaction design, evaluation frameworks for LLM outputs, debugging non-deterministic systems, and strong fundamentals in data modeling, APIs, and performance. As LLMs continue to improve, the key differentiator will not be who writes code the fastest, but who can ask the right questions, critically validate outputs, and design systems that remain reliable under uncertainty.

---

## Part 2: App and System Design

### How to set up a Docker Compose configuration that spins up the entire stack locally with a single command?

```
docker compose down  
docker compose up --build
```

---

### How to expose the MCP server endpoint (remote or local) with authentication?

The MCP server is exposed via a streamable HTTP endpoint (e.g., http://localhost:8000/mcp/mcp) and secured using Bearer token authentication.

Clients connect using MultiServerMCPClient, passing the token in the Authorization header:

```python
headers = {
    "Authorization": "Bearer <token>"
}
```

For local use, the server runs on localhost. For remote access, it could be deployed behind HTTPS (e.g., https://your-domain.com/mcp/mcp) with a reverse proxy.

---

### What does the overall architecture look like?

Overall, it’s a 3-tier local full-stack app:

#### Frontend (React + Vite)

A single-page UI lets users:

* upload PDF/TXT files with tags
* browse documents and tags
* run semantic search
* ask an AI question against the knowledge base

The frontend talks only to the backend over HTTP at http://localhost:8000.

#### Backend (FastAPI)

The FastAPI app is the central orchestrator. It exposes:

* /api/documents for upload/list/delete/download
* /api/tags for tag discovery
* /api/search for retrieval
* /api/agent/ask for grounded AI Q&A

It also mounts an MCP server under /mcp, so the agent can use the knowledge base as tools.

#### Database (Postgres + pgvector)

Postgres stores:

* document metadata
* chunk records
* vector embeddings for each chunk

pgvector is enabled so semantic similarity can be computed over stored embeddings.

#### Data flow

1. User uploads a PDF/TXT in the frontend.
2. Backend saves the file, parses it, splits it into chunks, generates embeddings with OpenAI, and stores both metadata and chunk vectors in Postgres.
3. Search requests hit the backend, which runs vector, BM25, or hybrid (RRF fusion) retrieval over stored chunks.
4. “Ask AI” calls the backend agent, which uses MCP-exposed tools like list_documents, search, search_by_tag, and search_by_document to answer with grounded sources.

---

### What stack choices were made, and what is the rationale behind each decision?

#### Vector store: Postgres + pgvector

The app stores chunk embeddings directly in Postgres using pgvector, with the backend enabling the vector extension at startup. That’s a pragmatic choice for an assignment: one database handles both metadata and embeddings, which keeps deployment and local development simple instead of adding a separate vector DB.

#### Embedding model: text-embedding-3-small

The configured embedding model is OpenAI’s text-embedding-3-small, and chunk vectors are stored at dimension 1536, which matches that model. The rationale is because it's strong enough for semantic search, but lighter and cheaper than a larger embedding model.

#### LLM for answer generation: gpt-4o via LangChain

The agent is created with ChatOpenAI(... "gpt-4o") and wrapped with LangChain tools. 

#### Chunking strategy: fixed-size sliding window (800 chars, 120 overlap)

Documents are chunked with chunk_size=800 and chunk_overlap=120. Chunks are small enough for precise retrieval, while overlap helps avoid losing meaning when important context sits across chunk boundaries.

#### Parsing strategy: lightweight native parsing

TXT files are decoded directly, and PDFs are parsed with pypdf. 

#### Retrieval strategy: hybrid search (vector + BM25) with RRF fusion

The search layer supports vector, bm25, and hybrid, and hybrid combines semantic ranking with keyword ranking using Reciprocal Rank Fusion (RRF_K = 60). That is a solid default because semantic search helps with meaning, while BM25 catches exact terms, acronyms, and policy wording.

#### MCP transport: streamable-http

The MCP server runs with transport="streamable-http", and the agent connects through streamablehttp_client to mcp_url. The rationale is clean service separation: the agent does not query the DB directly, but consumes the knowledge base through MCP tools.

#### API/backend stack: FastAPI + SQLAlchemy

FastAPI exposes the upload, search, tags, and agent routes, while SQLAlchemy handles persistence. This is just for fast prototyping: typed request/response models, simple routing, and straightforward DB integration. Also, you use Python in indigo.

#### Infra/dev stack: Docker Compose with 3 services

The compose setup uses separate frontend, backend, and postgres services. The rationale is reproducibility: the whole system can be run locally with predictable ports and environment variables, which is ideal for an engineering assignment demo.

---

### How were the MCP tools designed, and why were specific tools, names, and parameters chosen?

The MCP layer was designed as a thin, task-oriented wrapper around the knowledge base, not as a generic database interface. Instead of exposing low-level CRUD operations, it exposes a small set of tools that match how an LLM actually reasons: first discover what exists, then search broadly, then narrow by tag or document.

#### Tool set

- `list_documents`
- `list_tags`
- `search`
- `search_by_tag`
- `search_by_document`

#### Why these specific tools

- **`list_documents`**  
  Exists so the agent can first discover document IDs, filenames, tags, file types, and upload dates before attempting a filtered search.  
  Accepts `limit`, `offset`, and optional `tag_filter`: enough metadata browsing to support selection, without exposing unnecessary internals.

- **`list_tags`**  
  Exists because tags are user-facing categories and the agent may not know the exact allowed values in advance.  
  Returning the current unique tags helps the model avoid hallucinating tag names and improves precision before calling tag-restricted search.

- **`search`**  
  The default general-purpose retrieval tool.  
  Only requires `query`, `top_k`, and `retrieval_mode`, keeping it simple for the most common case: *search the whole knowledge base*.

- **`search_by_tag`**  
  Split out instead of overloading `search` with optional filters.  
  Makes intent explicit: use only when category-limited search is needed.  
  The required `tags` parameter prevents ambiguous calls.

- **`search_by_document`**  
  Handles cases where the user refers to a specific file.  
  Supports both `document_ids` and `document_names`, bridging the gap between user language (filenames) and backend needs (IDs).  
  Resolves names to IDs internally so the agent doesn’t need to manage that mapping.

#### Why the names were chosen

The naming is deliberately plain and self-descriptive.

`list_documents`, `list_tags`, `search`, `search_by_tag`, and `search_by_document` are easy for both humans and LLMs to interpret correctly.  
The names encode intent directly, reducing tool-selection errors.

This is reinforced by:
- MCP server instructions
- LangChain agent system prompt

Both explicitly guide the model on when to use each tool.

#### Why the parameters were chosen

The parameters are minimal and aligned to retrieval behavior:

- **`query`**: always required for search tools (natural-language driven retrieval)
- **`top_k`**: controls result size and keeps outputs bounded
- **`retrieval_mode`**: supports `vector`, `bm25`, or `hybrid` without separate tools
- **`tags`**: required only for `search_by_tag`
- **`document_ids` / `document_names`**: used only for `search_by_document`
- **`limit` / `offset`**: used only for `list_documents` (pagination for browsing)

#### Design takeaway

Each tool does one thing clearly.

This separation keeps schemas small, explicit, and hard to misuse, making it much easier for an LLM to:
1. choose the correct tool
2. pass the right parameters
3. produce grounded, reliable results

---

### How can someone run the project locally step by step?

#### 1. Clone the project

Clone the project and open the root folder.  
You need the fullstack structure so Docker can see:

- docker-compose.yml  
- frontend/  
- backend/  

```bash
git clone <repo>
cd indigoai_assignment
```

#### 2. Set environment variables

The backend expects at least:

- OPENAI_API_KEY  
- MCP_BEARER_TOKEN (optional, for MCP authentication)

```bash
set OPENAI_API_KEY=your_key
set MCP_BEARER_TOKEN=change-me
```

The compose file passes these into the backend container.

#### 3. Ensure Docker is installed

Make sure **Docker** and **Docker Compose** are installed.

The system runs as 3 services:
- postgres  
- backend  
- frontend  

#### 4. Run the stack

```bash
docker compose up --build
```

#### 5. Wait for services

The system includes health checks:

- Postgres waits until DB is ready  
- Backend waits for: http://localhost:8000/health  
- Frontend starts after backend is healthy  

#### 6. Access the application

Open in browser:

- Frontend → http://localhost:8001  
- Backend → http://localhost:8000  
- MCP → http://localhost:8000/mcp  

#### 7. Use the app

- Upload a `.pdf` or `.txt` file  
- Add tags  
- Run search  
- Ask grounded AI questions  

#### 8. Backend endpoints (manual check)

- Health:  
  http://localhost:8000/health  

- API:  
  /api/documents  
  /api/tags  
  /api/search  
  /api/agent/ask  

- MCP:  
  http://localhost:8000/mcp  

---

### How can an MCP-compatible client connect to the server?

Refer to `agent_test.py` (used in the demo) for a working example client.

In general:
- Connect to: http://localhost:8000/mcp  
- Use `streamable-http` transport  
- Pass Authorization header if required  

---

### What are the known limitations of the system, and what improvements would be made with more time?

#### Known limitations

- **Limited file support**  
  The system only accepts PDF and TXT uploads.

- **Basic PDF parsing**  
  Uses `pypdf`, which struggles with scanned documents, tables, and complex layouts. No OCR is implemented.

- **Naive chunking strategy**  
  Fixed sliding window (800 chars with 120 overlap), without awareness of document structure.

- **Retrieval runs in application memory**  
  Hybrid search is computed in Python, which does not scale well for large datasets.

- **No reranking stage**  
  Results are returned directly from vector/BM25/RRF without refinement.

- **Agent source grounding is basic**  
  Sources are extracted via string parsing, which is not robust.

- **Weak authentication for production**  
  Only basic bearer token auth is implemented; no multi-tenant security.

- **Duplicate handling is limited**  
  Based only on file hash; does not handle versioning or near-duplicates.

- **No async ingestion pipeline**  
  Upload, parsing, embedding, and storage are synchronous.

- **Minimal observability**  
  No evaluation pipeline, tracing, or retrieval benchmarking.

#### Improvements with more time

- **Support more formats**  
  Add DOCX, PPTX, HTML, Markdown, and email ingestion.

- **Improve parsing**  
  Add OCR and structure-aware extraction for headings, sections, and tables.

- **Upgrade chunking**  
  Use semantic or structure-based chunking.

- **Optimize retrieval**  
  Move vector similarity and filtering into the database (pgvector queries).

- **Add reranking**  
  Introduce a cross-encoder or LLM-based reranker.

- **Improve citations**  
  Return chunk-level provenance (page numbers, exact spans).

- **Add background processing**  
  Use async workers for ingestion and embedding.

- **Production hardening**  
  Add authentication, authorization, and cloud storage (e.g., S3).

- **Evaluation & monitoring**  
  Add metrics for retrieval quality, latency, and correctness.

- **Enhance MCP tools**  
  Expand toolset and return richer structured outputs for better agent interaction.