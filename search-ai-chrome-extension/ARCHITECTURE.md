# Spark NZ RAG Chatbot — Architecture & Design Document

**Last updated:** April 2026  
**Status:** Demo-ready  
**Index:** `spark_products` · ES9 Serverless · Australia East (Azure)

---

## 1. Overview

A Chrome extension overlay that acts as **Tui** — a friendly Spark NZ virtual sales assistant. Tui provides intelligent product recommendations, plan comparisons, cross-sell probes, and proactive upsell greetings when customers browse Spark product pages.

The system is built on three layers:
- **Chrome Extension** (`overlay.js`, `overlay.css`) — injects the chat UI into any configured website
- **Flask API** (`server.py`) — orchestrates search, inference, and response generation
- **Elastic Stack** — `spark_products` index for product data, EIS (Elastic Inference Service) for all LLM calls

**No OpenAI dependency.** All LLM calls go through EIS using Anthropic Claude models hosted on Elastic's infrastructure.

---

## 2. Architecture

```
Browser (spark.co.nz)
  └── Chrome Extension
        ├── overlay.js        — UI, conversation history, API calls
        └── overlay.css       — Styling

        ↕ HTTP (localhost:5000)

Flask Server (server.py)
  ├── /query                  — Main chat endpoint
  ├── /lookup                 — Proactive product page greeting
  └── /status                 — Health check

        ↕ Elasticsearch Python Client (v9.x)

Elastic Cloud (ES9 Serverless)
  ├── spark_products index    — Product data, plans, specs
  └── EIS Inference Endpoints
        ├── .anthropic-claude-4.5-haiku-completion    — Intent extraction, summarisation, suggestions
        └── .anthropic-claude-4.6-sonnet-completion   — Response generation, greetings
```

---

## 3. Elasticsearch Index — `spark_products`

### Schema Design

One document per colour/storage variant. All plan, pricing, and spec data is denormalised into each document — no joins required at query time.

### Key Fields

| Field | Type | Description |
|---|---|---|
| `product_name` | `text` + `keyword` | Full product name |
| `brand` | `keyword` | Apple, Samsung, OPPO, etc. |
| `category` | `keyword` | See category taxonomy below |
| `color` | `keyword` | Colour name per variant |
| `storage` | `keyword` | 128GB, 256GB, etc. |
| `availability` | `keyword` | `in_stock` or `out_of_stock` |
| `features` | `keyword[]` | 5G, eSIM, satellite, dual sim |
| `use_case_tags` | `keyword[]` | premium, budget, camera, rugged, foldable, satellite |
| `pricing.upfront` | `float` | Full outright price |
| `pricing.net_after_credit` | `float` | Price after device credit |
| `pricing.device_credit` | `float` | Credit amount |
| `pricing.min_monthly` | `float` | Lowest IFP monthly across all terms |
| `payment_plans` | `nested` | IFP options — term, monthly amount, deposit |
| `mobile_plans` | `nested` | All compatible Spark plans with IFP pricing |
| `specs.*` | `object` | display_inches, battery_mah, rear_camera_mp, zoom_x, processor, ip_rating |
| `primary_image_url` | `keyword` | Full CDN URL — already absolute, no domain prepending needed |
| `gallery_urls` | `keyword[]` | All variant image URLs |
| `source_url` | `keyword` | Canonical Spark product page URL — used for `/lookup` slug matching |
| `search_text` | `semantic_text` | Denormalised NLP blob — ELSER auto-generates embeddings on ingest |
| `compatible_models` | `keyword[]` | For accessories — phone model names this accessory fits |
| `compatible_brands` | `keyword[]` | For accessories — compatible phone brands |
| `trade_in_eligible` | `boolean` | Whether device qualifies for trade-in |
| `insurable` | `boolean` | Whether Device Protect insurance is available |

### Category Taxonomy

```
handsets
accessories_cases_protection
accessories_cables_chargers
accessories_gaming
accessories_speakers
accessories_headphones
accessories_smart_home
accessories_security
accessories_tablets
accessories_wearables
accessories_laptop
accessories_memory
accessories_tonies
wearables
tablets
smart_tv
deals
data_devices
accessories_gift_cards
accessories_home_phones
```

### Known Plans

| Plan ID | Name | Price | Data | Satellite | Streaming |
|---|---|---|---|---|---|
| `mbundle070137` | $65 75GB Endless Plan | $65 | 75GB | No | — |
| `mbundle070138` | $75 150GB Endless Plan | $75 | 150GB | Yes | Spotify |
| `mbundle070139` | $40 150GB Endless Companion | $40 | 150GB | Yes | — |
| `mbundle070140` | $90 Unlimited Data Plan | $90 | Unlimited | Yes | — |
| `mbundle070141` | $45 Unlimited Data Companion | $45 | Unlimited | Yes | — |
| `mbundle070154` | $95 Unlimited Data Netflix Plan | $95 | Unlimited | Yes | Netflix |
| `mbundle052141` | Business Endless 150GB | $75 | 150GB | Yes | — |
| `mbundle052142` | Business Unlimited | $90 | Unlimited | Yes | AU Roaming |

**Note:** Two plans (`mbundle070136` $50 6GB, `mbundle052140` Business 6GB) have incomplete data in the index — missing `monthly_price`, `data_type`, etc. Known transformer bug, not a code issue.

---

## 4. EIS Configuration

### Inference Endpoints in Use

| Endpoint ID | Model | Used For |
|---|---|---|
| `.anthropic-claude-4.5-haiku-completion` | Claude Haiku 4.5 | Intent extraction, history summarisation, suggestions fallback, slug parsing |
| `.anthropic-claude-4.6-sonnet-completion` | Claude Sonnet 4.6 | Response generation, lookup greetings |

### API Key Permissions Required

The Elasticsearch API key must have the `monitor_inference` cluster privilege:

```json
PUT /_security/role/write-only-role
{
  "cluster": ["monitor_inference"],
  "indices": [
    {
      "names": ["*"],
      "privileges": ["write", "create_index", "read"]
    }
  ]
}
```

### Important: Use `completion` not `chat_completion`

EIS `chat_completion` endpoints require streaming (`_stream` API). For synchronous calls use the `completion` endpoint IDs:
- ✅ `.anthropic-claude-4.6-sonnet-completion`
- ❌ `.anthropic-claude-4.6-sonnet-chat_completion` (streaming only)

Python client call:
```python
raw = es_client.inference.completion(
    inference_id=EIS_SONNET,
    input=prompt,
    task_settings={"max_tokens": 500}
)
result = raw["completion"][0]["result"]
```

---

## 5. Server Architecture (`server.py`)

### Environment Variables

```bash
ELASTIC_CLOUD_ID=your_cloud_id        # Required
ELASTIC_API_KEY=your_api_key          # Required
SEARCH_INDEX=spark_products           # Default: spark_products
DEBUG_BAR=false                       # Set true to show debug bar in UI
```

No OpenAI key required — all LLM calls go through EIS.

### Request Flow — `/query`

```
POST /query { text, history[] }
  │
  ├─ 1. summarise_history()
  │      If history > 8 turns:
  │        Haiku compresses turns 1..n-4 → summary string
  │        Keep last 4 turns raw
  │      Else: pass history as-is
  │
  ├─ 2. extract_intent()  [Haiku]
  │      Returns: { intent_type, category, brand, max_upfront,
  │                 max_monthly, features, use_case_tags,
  │                 min_battery, min_camera_mp, ambiguous }
  │
  ├─ 3. Route by intent_type:
  │      "informational" → generate_response() with no ES search
  │      "ambiguous"     → return clarification pills, no search
  │      "product_search" → continue to step 4
  │
  ├─ 4. search_products()
  │      Semantic query on search_text field
  │      + hard filters: in_stock, category, brand, features,
  │        use_case_tags, max_upfront, max_monthly (nested),
  │        min_battery, min_camera_mp
  │      If 0 results: retry with category-only fallback
  │      If price filter caused 0 results: set price_constraint_failed flag
  │
  ├─ 5. extract_products() + create_context()
  │      Maps _source fields to UI product shape
  │      Builds LLM context string with pricing, plans, specs
  │      If price_constraint_failed: prepend honest note to context
  │
  ├─ 6. generate_response()  [Sonnet]
  │      Prompt = system_prompt + cross_sell_catalogue (if history≥2)
  │               + summary + recent_history + context + question
  │      Parses response blocks:
  │        <products>   → ranked product indices for carousel order
  │        <suggestions>→ follow-up pills
  │        <followup>   → highlighted question block (purple)
  │        <probe>      → cross-sell question block (amber)
  │
  ├─ 7. Reorder products by Tui's ranked_indices
  │
  └─ 8. Return JSON response
```

### Request Flow — `/lookup`

Triggered when user opens chat bubble on a Spark product page.

```
POST /lookup { url }
  │
  ├─ 1. Extract slug from URL
  │      /products/samsung-galaxy-s26-ultra-5g → "samsung-galaxy-s26-ultra-5g"
  │
  ├─ 2. ES query: wildcard on source_url matching slug
  │      Returns all in-stock variants (colours/storage)
  │
  ├─ 3. Build plan upsell context
  │      Sort mobile_plans by monthly_price DESC (most expensive first)
  │      Extract perks: Netflix, Spotify, Satellite, AU Roaming, Team Up
  │
  ├─ 4. Accessories query  [Haiku slug parsing]
  │      Haiku extracts model keywords from slug:
  │        "samsung-galaxy-s26-ultra-5g" → ["Galaxy S26 Ultra", "S26 Ultra", "S26"]
  │      ES query: compatible_models term match (should, minimum_should_match: 1)
  │      Categories: all accessories (cases, chargers, gaming, speakers)
  │
  ├─ 5. generate greeting  [Sonnet]
  │      Upsell-first: lead with most expensive plan + standout perk
  │      Never describe specs (customer is on the product page)
  │      Max 3 sentences
  │
  └─ 6. Return: { matched, response, accessories, suggestions, insurable }
         Note: products array intentionally omitted (redundant on product page)
```

### Intent Types

| `intent_type` | Behaviour | ES Search |
|---|---|---|
| `product_search` | Normal search pipeline | Yes |
| `informational` | Tui answers from knowledge | No |
| `ambiguous` | Returns category clarification pills | No |

### Conversation History & Summarisation

- History is maintained **client-side** in `overlay.js` as `conversationHistory[]`
- Persisted in `chrome.storage.session` under key `tui_conversation_history`
- Survives page navigation within the same browser session
- Cleared automatically when browser closes
- Restored from session storage on page load via `restoreSession()` — replays messages into DOM with a "↑ Previous conversation" indicator
- Sent with every `/query` request as `history` array
- Server summarises when `len(history) > 8` using Haiku
- Summary replaces old turns, last 4 turns kept raw
- Closing the bubble (minimise button or bubble click) just hides the overlay — does NOT reset history

**Permission required:** `storage` in `manifest.json` covers both sync and session storage in Manifest V3.

### Cross-sell Catalogue

- Loaded on Flask startup via `schedule_catalogue_refresh()`
- Background thread refreshes every 60 minutes
- Queries ES for all in-stock non-handset categories with brand counts
- Formatted and injected into Sonnet prompt when `len(history) >= 2`
- Tui uses this to generate contextual `<probe>` questions

---

## 6. Tui Response Format

Every Sonnet response must include these structured blocks appended after the prose:

```
[prose response here]

<products>["1","3","2"]</products>
<suggestions>["Samsung", "Apple", "Show budget options"]</suggestions>

Optional — pick ONE or neither:
<followup>Which ecosystem do you prefer — Samsung or Apple?</followup>
<probe>category:accessories_gaming|question:Are you a gamer by any chance?|pills:["Yes, big gamer", "Casual gaming", "Not really"]</probe>
```

### Block Parsing in `generate_response()`

All blocks are stripped from prose before returning. The regex patterns:

```python
re.search(r'<products>(.*?)</products>', full_text, re.DOTALL)
re.search(r'<suggestions>(.*?)</suggestions>', full_text, re.DOTALL)
re.search(r'<followup>(.*?)</followup>', full_text, re.DOTALL)
re.search(r'<probe>(.*?)</probe>', full_text, re.DOTALL)
```

Probe format parsing:
```python
probe_parts = dict(part.split(":", 1) for part in probe_raw.split("|") if ":" in part)
# → { "category": "accessories_gaming", "question": "...", "pills": "[...]" }
```

### Probe Timing Rules

The probe block is intentionally rare. Sonnet decides when to fire based on these rules:

**Good moments:**
- Customer has chosen a product
- Customer asked about plans
- Customer seems happy
- Customer just committed to an add-on (peak engagement — perfect for a different-category probe)

**Bad moments:**
- Customer is comparing prices
- Customer asked a direct question
- Customer seems unsure
- Customer has already initiated category expansion themselves ("show me accessories", "what else do you have") — probe would be redundant

**Probe never fires alongside `<followup>`** — they're mutually exclusive. Sonnet picks one or neither.

---

## 7. Chrome Extension Architecture

### Files

| File | Purpose |
|---|---|
| `manifest.json` | Extension metadata, permissions, content script injection |
| `background.js` | Service worker — initialises default website list (`spark.co.nz`) |
| `overlay.js` | Main content script — UI creation, conversation history, API calls |
| `overlay.css` | All styling — bubble, overlay, cards, tables, pills, debug bar |
| `popup.html/js` | Configuration UI — add/remove websites where overlay appears |

### Conversation History

```javascript
let conversationHistory = [];  // Reset on bubble close

// On send:
conversationHistory.push({ role: 'user', content: message });

// On response:
conversationHistory.push({ role: 'assistant', content: data.response });

// Sent with every request:
body: JSON.stringify({
  text: message,
  history: conversationHistory.slice(0, -1)  // exclude current turn
})
```

### UI Component Render Order

```
[scroll anchor — invisible marker for "scroll to start of response"]
addMessage('bot', response, true)          — prose response (markdown)
addProductCards(products)                  — horizontal scroll carousel
addSectionLabel('Compatible accessories')  — divider (lookup only)
addProductCards(accessories)               — accessories carousel (lookup only)
addMessage('bot', device protect nudge)    — if insurable (lookup only)
addFollowupQuestion(followup)              — purple highlighted block
addProbe(probe)                            — amber block with answer pills
addSuggestionsSection(suggestions)         — purple pill row
addDebugBar(debugBar)                      — dark monospace strip (DEBUG_BAR=true only)
```

After all elements render, the view scrolls to the **start of the response** (not the bottom), so the customer sees Tui's prose first and can scroll down to explore.

### Product Card Fields

The overlay expects this shape from the server:

```javascript
{
  product_name:      string,
  brand:             string,
  category:          string,
  color:             string,
  storage:           string,       // "NA" is filtered from badge display
  availability:      string,
  features:          string[],     // rendered as tags, max 3
  pricing: {
    upfront:         float,        // displayed as primary price
    min_monthly:     float,        // displayed as "or $X/mo"
    device_credit:   float,
    net_after_credit: float
  },
  payment_plans: [{                // rendered as plan table, sorted longest term first
    term_months:     int,
    monthly_amount:  float,
    min_deposit:     float
  }],
  primary_image_url: string,       // full CDN URL, no domain prepending needed
  url:               string        // source_url — View Details button target
}
```

### URL Detection (Product Page Lookup)

```javascript
const SPARK_PRODUCT_PATTERN = /spark\.co\.nz\/online\/shop\/products\/([^/?#]+)/;
const currentSlug = (window.location.href.match(SPARK_PRODUCT_PATTERN) || [])[1] || null;

// On bubble open, if slug found and history empty:
setTimeout(() => triggerProductLookup(), 2000);
```

---

## 8. Markdown Rendering

`overlay.js` includes a custom `parseMarkdown()` function. Key behaviour:

- **Tables** parsed first (before newline conversion) using line-by-line scanner looking for `|` rows + separator row
- Renders as `<table class="md-table">` styled in CSS
- `\n\n` → `<br>` (single line break, not paragraph gap — prevents LLM double-spacing)
- Standard bold, italic, code, links, headers, lists supported

---

## 9. Debug Bar

Enabled via `DEBUG_BAR=true` in `.env`. Shows in the chat as a dark monospace strip:

```
spark_products · 5 hits · semantic + 3 intent filters · 6 turns (summarised)
[semantic] [in_stock] [~847ms]
```

Fields returned in `debugBar` payload:
- `index` — index name
- `hits` — number of ES results
- `latency_ms` — total request time
- `query_type` — describes active filters
- `history_turns` — conversation depth
- `summarised` — whether history was compressed

---

## 10. Known Issues & Future Work

### Known Data Issues (Transformer bugs — not code issues)

| Issue | Detail |
|---|---|
| Camera MP values wrong | `specs.rear_camera_mp` shows summed values (2001MP) instead of primary lens MP |
| `compatible_models` inconsistent | Some accessories store their own name instead of the compatible phone model — accessory queries return 0 results for affected products |
| Two incomplete plans | `mbundle070136` and `mbundle052140` missing most fields |

### Deferred Work (post-demo)

| Feature | Notes |
|---|---|
| Accessories transformer fix | Ensure `compatible_models` stores phone model names not accessory names |
| Camera MP transformer fix | Use primary rear camera MP not sum |
| Production CORS hardening | `CORS(app)` allows all origins — restrict to `spark.co.nz` for production |
| Cross-window history sharing | `chrome.storage.session` is per-tab-process — does not sync between separate browser windows |

---

## 11. Demo Query Sequence

Tested and verified working:

| Query | What it demonstrates |
|---|---|
| `What's the best camera phone right now?` | Pure semantic — ELSER understanding intent without keywords |
| `Samsung is my preference` | Conversational follow-up — history resolves brand context |
| `5G phones under $50 a month` | Intent extraction — nested payment_plans filter |
| `Which phones come with a $600 device credit?` | Plan-aware — mobile_plans data |
| `Show me cases for the iPhone 16 Pro` | Cross-category accessories |
| `What is device credit?` | Informational intent — no ES search, Tui answers from knowledge |
| `Any trade-in deals?` | Trade-in eligible flag + upsell |
| `Compare iPhone vs Samsung camera specs` | Table rendering, multi-product comparison |
| Navigate to product page → open bubble | `/lookup` proactive upsell greeting |

---

## 12. File Checklist

```
server.py           — Flask API (all logic)
overlay.js          — Chrome extension content script
overlay.css         — All UI styling
manifest.json       — Extension config (unchanged)
background.js       — Extension service worker (unchanged)
popup.html          — Extension settings UI (unchanged)
popup.js            — Extension settings logic (unchanged)
requirements.txt    — Python deps (elasticsearch>=9.0.0, no openai)
.env                — ELASTIC_CLOUD_ID, ELASTIC_API_KEY, SEARCH_INDEX, DEBUG_BAR
```
