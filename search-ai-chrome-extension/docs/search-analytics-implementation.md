# Search Analytics & Observability Implementation

Summary of work completed implementing OpenTelemetry-based search analytics and chat observability for the Spark TUI Chrome extension, based on the elastic/search-analytics-otel-reference blog series (Posts 1–3).

---

## Overview

The implementation adds end-to-end observability across the full query lifecycle — from user input in the Chrome extension through intent extraction, Elasticsearch search, and LLM response generation — with all telemetry flowing into Elastic APM via OTLP.

---

## Files Changed

| File | Changes |
|---|---|
| `server.py` | OTel SDK setup, 4 named spans, `/click` endpoint, `search_products` tuple return |
| `overlay.js` | Session ID, click reporting, storage fix, lookup trigger rewrite, reset button |
| `overlay.css` | Reset button styles |
| `requirements.txt` | Replaced `elastic-apm` with direct OTel SDK packages |

---

## 1. OpenTelemetry Setup (`server.py`)

Replaced `elastic-apm` with direct OTel SDK initialisation. Key decisions:

- **`elastic-opentelemetry` package dropped** — `ElasticOpenTelemetryDistro().configure()` only sets env vars and leaves a `ProxyTracerProvider` (all-zero trace IDs). Direct SDK setup required.
- **`ElasticsearchInstrumentor` dropped** — ES client v9 has native OTel support, self-instruments when a `TracerProvider` is configured. Separate instrumentor causes a warning.
- **`FlaskInstrumentor().instrument_app(app)`** called after `app = Flask(__name__)` — calling before app creation means nothing is patched and ES client spans become orphaned roots with no Flask parent.

**Required `.env` variables:**
```
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-apm.elastic.cloud:443
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer your-token
OTEL_SERVICE_NAME=spark-tui
```

**`requirements.txt` packages:**
```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
opentelemetry-instrumentation-flask==0.61b0
```

---

## 2. Trace Hierarchy

```
POST /query                          ← Flask root (auto-instrumented)
│   chat.history_turns
│   chat.summary_used
│   chat.session_id
│
├── search                           ← named span
│   search.action = "search"
│   search.user_query
│   search.query_id (= trace_id hex)
│   search.result_count
│   search.took_ms
│   ├── search  (ES client — primary)
│   └── search  (ES client — fallback)
│
├── intent_extraction                ← named span
│   intent.type
│   intent.category
│   intent.brand
│   intent.ambiguous
│   intent.fallback_triggered
│   intent.filter_count
│
└── response_generation              ← named span
    llm.model
    llm.prompt_tokens
    llm.completion_tokens
    llm.total_tokens
    llm.grounded
    llm.grounded_product_count
    response.product_count
    response.has_followup
    response.has_probe
    response.price_constraint_failed
    response.used_tui_suggestions

POST /click                          ← Flask root (auto-instrumented)
    search.action = "click"
    search.result_click_id
    search.result_click_position
    search.result_click_type
    search.query_id
    search.user_query
    search.first_click
```

---

## 3. Click Tracking (`/click` endpoint)

New endpoint records product card "View Details" clicks as OTel spans, enabling CTR and MRR calculation via ES|QL.

- `search.query_id` links click spans back to their originating search span
- `search.first_click` is set server-side using a thread-safe in-memory Set — avoids deduplication complexity in ES|QL
- Fire-and-forget `fetch` in `overlay.js` — never blocks UI or product page navigation

**CTR formula:** `queries with search.first_click = true / total search spans`

**MRR formula:** `AVG(1 / search.result_click_position)` across all click spans

---

## 4. ES|QL Queries (Kibana)

**Zero-results rate:**
```sql
FROM traces-generic.otel-*
| WHERE span.name == "search"
| EVAL zero_result = numeric_labels.search_result_count == 0
| STATS zero_results = COUNT(*[WHERE zero_result]), total = COUNT(*)
| EVAL zero_results_rate = ROUND(zero_results / total * 100, 1)
```

**Top queries by volume:**
```sql
FROM traces-generic.otel-*
| WHERE span.name == "search"
| STATS count = COUNT(*) BY labels.search_user_query
| SORT count DESC
| LIMIT 20
```

**CTR:**
```sql
FROM traces-generic.otel-*
| WHERE span.name == "search" OR (span.name == "POST /click" AND labels.search_first_click == "true")
| STATS searches = COUNT(*[WHERE span.name == "search"]),
        clicks   = COUNT(*[WHERE labels.search_first_click == "true"])
| EVAL ctr = ROUND(clicks / searches * 100, 1)
```

**MRR:**
```sql
FROM traces-generic.otel-*
| WHERE labels.search_action == "click"
| EVAL reciprocal_rank = 1.0 / numeric_labels.search_result_click_position
| STATS mrr = AVG(reciprocal_rank)
```

---

## 5. `overlay.js` Changes

### Storage fix
`chrome.storage.session` is blocked in content script context on third-party pages. All storage replaced with `chrome.storage.local`.

### Session ID
`crypto.randomUUID()` generated once per overlay init, sent as `X-Session-Id` header on every `/query` request. Maps to `chat.session_id` in APM for grouping conversation traces.

### Click reporting
"View Details" button fires `fetch` to `/click` with `object_id` (product URL), `position` (1-indexed), `query_id`, and `user_query` before opening the product page.

### Lookup trigger rewrite
Previous condition `conversationHistory.length === 0` replaced with three proper guards:

```javascript
const alreadyGreetedThisProduct = conversationHistory
  .some(t => t.role === 'assistant' && t.content.includes(currentSlug));

if (currentSlug && !lookupFired && !alreadyGreetedThisProduct) {
  setTimeout(() => triggerProductLookup(), 2000);
}
```

| Flag | Purpose |
|---|---|
| `lookupFired` | Fires lookup once per session only (Scenario 2) |
| `alreadyGreetedThisProduct` | Skips re-greeting same product page (Scenario 3) |
| `lookupInFlight` + `lookupController` | Aborts lookup cleanly if user types first (Scenario 7) |

Lookup response now **appends** to existing conversation — `messagesContainer.innerHTML = ''` removed (Scenarios 1 + 6).

### Demo reset button
`⟳` button in chat header resets all state for clean demo runs:
- Clears `chrome.storage.local`
- Wipes messages container
- Resets all lookup flags
- Re-shows welcome message
- Re-triggers lookup if on a product page

---

## 6. Known Gaps / Future Work

| Area | Notes |
|---|---|
| PII detection | Agreed to use Haiku inference (not regex) — deferred |
| Conversion tracking | Post 4 of series — requires owning destination pages |
| Suggestion click tracking | High signal, fires more than product clicks — not yet tracked |
| `chat.session_id` grouping | Wired and sending but no Kibana dashboard built yet |
| LLM grounding check | Simple name-match heuristic — not semantic |
| Token counts | Depends on `raw["meta"]["usage"]` path from EIS — verify on first run |

---

## 7. Lookup Trigger Edge Cases

See `lookup-trigger-edge-cases.md` for full scenario analysis and decisions.

| # | Scenario | Decision |
|---|---|---|
| 1 | Mid-conversation → product page | Append |
| 2 | Navigate between product pages | Once per session |
| 3 | Return to same product page | No action |
| 4 | Server down | Acceptable |
| 5 | Slug not in index | Acceptable |
| 6 | Long conversation → product page | Append |
| 7 | User types before lookup completes | `lookupInFlight` abort |
