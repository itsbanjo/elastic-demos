import os
import json
import time
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from elasticsearch import Elasticsearch
import logging
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# OpenTelemetry — direct SDK setup (reads OTEL_* vars from .env)
# Must run before Flask app is created so Flask + ES client are instrumented.
# ---------------------------------------------------------------------------
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.flask import FlaskInstrumentor

_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
if _otel_endpoint:
    _resource  = Resource.create({SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "spark-tui")})
    _provider  = TracerProvider(resource=_resource)
    _exporter  = OTLPSpanExporter()   # reads OTEL_EXPORTER_OTLP_ENDPOINT + OTEL_EXPORTER_OTLP_HEADERS from env
    _provider.add_span_processor(BatchSpanProcessor(_exporter))
    trace.set_tracer_provider(_provider)
    # ES client v9 has native OTel support — self-instruments when it detects
    # a configured TracerProvider, no separate instrumentor needed.
    # FlaskInstrumentor is applied after app = Flask(__name__) below.
    logging.getLogger(__name__).info(f"OTel enabled → {_otel_endpoint}")
else:
    logging.getLogger(__name__).warning("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing disabled")

_tracer = trace.get_tracer("spark-search-api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Instrument Flask now that the app instance exists.
# Must happen after app = Flask(...) — calling instrument() before the app
# is created means there is nothing to patch, so no Flask parent spans are
# generated and ES client spans become orphaned roots.
if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    FlaskInstrumentor().instrument_app(app)

# ---------------------------------------------------------------------------
# Single client — everything goes through Elastic
# ---------------------------------------------------------------------------
es_client = Elasticsearch(
    cloud_id=os.environ.get("ELASTIC_CLOUD_ID"),
    api_key=os.environ.get("ELASTIC_API_KEY")
)

# Configuration
SEARCH_INDEX    = os.environ.get("SEARCH_INDEX", "spark_products")
DEBUG_BAR       = os.environ.get("DEBUG_BAR", "false").lower() == "true"

# EIS inference endpoint IDs
EIS_HAIKU  = ".anthropic-claude-4.5-haiku-completion"   # intent + suggestions + summarisation
EIS_SONNET = ".anthropic-claude-4.6-sonnet-completion"  # response generation

# Conversation history thresholds
HISTORY_RAW_LIMIT   = 8   # turns kept as raw history (4 exchanges)
HISTORY_SUMMARISE_AT = 8  # summarise when history exceeds this

# ---------------------------------------------------------------------------
# Cross-sell catalogue — cached on startup, refreshed hourly
# ---------------------------------------------------------------------------
import threading

CROSS_SELL_CATALOGUE = {}
CROSS_SELL_LOCK      = threading.Lock()

def refresh_cross_sell_catalogue():
    """
    Fetch available non-handset categories and their top brands from ES.
    Excludes categories that aren't meaningful cross-sell (gift cards, deals).
    Runs on startup and every 60 minutes in a background thread.
    """
    EXCLUDED = {
        "handsets", "accessories_gift_cards", "deals",
        "data_devices", "accessories_home_phones"
    }
    try:
        result = es_client.search(index=SEARCH_INDEX, body={
            "size": 0,
            "query": {"term": {"availability": "in_stock"}},
            "aggs": {
                "by_category": {
                    "terms": {"field": "category", "size": 30},
                    "aggs": {
                        "top_brands": {
                            "terms": {"field": "brand", "size": 4}
                        },
                        "sample_products": {
                            "terms": {"field": "product_name.keyword", "size": 3}
                        }
                    }
                }
            }
        })

        catalogue = {}
        for bucket in result["aggregations"]["by_category"]["buckets"]:
            cat = bucket["key"]
            if cat in EXCLUDED or bucket["doc_count"] < 2:
                continue
            brands   = [b["key"] for b in bucket["top_brands"]["buckets"]]
            products = [p["key"] for p in bucket["sample_products"]["buckets"]]
            catalogue[cat] = {
                "count":    bucket["doc_count"],
                "brands":   brands,
                "examples": products
            }

        with CROSS_SELL_LOCK:
            CROSS_SELL_CATALOGUE.clear()
            CROSS_SELL_CATALOGUE.update(catalogue)

        logger.info(f"Cross-sell catalogue refreshed: {len(catalogue)} categories")

    except Exception as e:
        logger.warning(f"Cross-sell catalogue refresh failed: {e}")

def schedule_catalogue_refresh():
    """Refresh catalogue every 60 minutes in background."""
    refresh_cross_sell_catalogue()
    t = threading.Timer(3600, schedule_catalogue_refresh)
    t.daemon = True
    t.start()

def format_cross_sell_catalogue():
    """Format catalogue for inclusion in LLM prompt."""
    with CROSS_SELL_LOCK:
        if not CROSS_SELL_CATALOGUE:
            return ""
        lines = []
        for cat, info in CROSS_SELL_CATALOGUE.items():
            readable = cat.replace("accessories_", "").replace("_", " ").title()
            brands   = ", ".join(info["brands"][:3]) if info["brands"] else "Various"
            examples = ", ".join(info["examples"][:2]) if info["examples"] else ""
            example_str = f" (e.g. {examples})" if examples else ""
            lines.append(f"- {readable}: {brands}{example_str} — {info['count']} products")
        return "\n".join(lines)

# ---------------------------------------------------------------------------
# Category affinity map — defines natural cross-sell pairs for non-handset probing
# ---------------------------------------------------------------------------
CATEGORY_AFFINITY = {
    "smart_tv":               ["accessories_gaming", "accessories_speakers", "accessories_headphones"],
    "tablets":                ["accessories_headphones", "accessories_speakers", "accessories_laptop"],
    "accessories_gaming":     ["accessories_headphones", "accessories_speakers"],
    "accessories_speakers":   ["accessories_headphones", "accessories_gaming"],
    "accessories_headphones": ["accessories_speakers", "accessories_gaming"],
    "accessories_laptop":     ["accessories_wearables", "accessories_memory"],
    "accessories_wearables":  ["wearables", "accessories_laptop"],
    "wearables":              ["accessories_wearables", "handsets"],
    "accessories_smart_home": ["accessories_security"],
    "accessories_security":   ["accessories_smart_home"],
    "accessories_tonies":     ["accessories_tonies"],
    "data_devices":           ["accessories_laptop", "accessories_wearables"],
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are Tui, a friendly Spark NZ sales assistant helping customers find the perfect phone, plan, and accessories.

You have access to real-time Spark product data including pricing, payment plans, and specs.

## Your personality
- Warm, helpful, and conversational — like a knowledgeable Spark store rep
- Keep responses concise and scannable — no walls of text
- Use plain NZ English (not American English)
- Never make up products or prices — only reference what's in the context

## Language rules
- Never use "IFP" — say "interest-free payments" or "pay monthly" instead
- Never use "IFP options" — say "payment options" or "pay over time"
- Say "$X/mo over 24 months" not "24-month IFP"

## How to answer
- Lead with the most relevant product(s) for the question
- Always mention the monthly price alongside upfront — customers think in monthly terms
- When mentioning plans, combine device monthly + plan cost into a total (e.g. "$1/mo device + $75/mo plan = $76/mo total")
- If a product has device credit, mention it — it's a key selling point
- When a product has multiple colour or storage variants, mention them naturally — e.g. "available in Black, White and Titanium" or "comes in 256GB and 512GB"
- For spec questions, answer directly without listing every spec
- If nothing in the context matches the question, say so honestly
- Use conversation history to understand follow-up questions and references to previous products

## What to avoid
- Never discuss competitor products or pricing
- Never guarantee pricing — always say "prices may vary, check spark.co.nz"
- Never answer billing, account, or store location questions — direct to 0800 800 123
- Never recommend out of stock products

## Response format
- Use markdown for bold and links only — avoid excessive bullet points
- When you do use a bullet list, use single newlines between items — never blank lines between bullets
- Keep responses under 100 words where possible
- Cite products using [1], [2] etc. matching the context numbers

## REQUIRED: End every response with a ranked product list AND suggestions
After your prose response, always append BOTH blocks — no exceptions:
<products>["1","2","3"]</products>
<suggestions>["Samsung", "Apple", "Show me budget options"]</suggestions>

Rules for the products block:
- List ONLY the context numbers you actually recommended in your response
- Order them best-first for the customer's specific query
- Exclude any context numbers you didn't mention or that aren't relevant
- Use string numbers matching the [N] citations above
- Return <products>[]</products> when the question is informational and no specific product recommendation was made — e.g. "What is device credit?", "How do trade-ins work?", "What plans are available?", "What does 5G mean?"
- Only populate products when you are actively recommending specific products to the customer

Rules for the suggestions block:
- Generate 3-4 short follow-up options (under 8 words each)
- If your response ends with a direct question (e.g. "Samsung or Apple?"), the first suggestions MUST directly answer that question (e.g. "Samsung", "Apple")
- Otherwise suggest the most useful next questions for the customer's journey
- Keep them specific to the conversation context — never generic
- Examples: ["Samsung", "Apple"], ["Show me cases for this", "What's included in the $75 plan?", "Any trade-in deals?"]

## REQUIRED: Also append a followup question block
If you want to ask the customer a clarifying or engaging question, put it here instead of in your prose:
<followup>Which ecosystem do you prefer — Samsung or Apple?</followup>

Rules for the followup block:
- One short question only — under 12 words
- Only include if genuinely useful for the conversation
- If no follow-up is needed, omit the block entirely — do not include an empty tag
- Never end your prose with a question — put it here instead
- Never use both <followup> and <probe> in the same response — pick one

## OPTIONAL: Cross-sell probe
When the customer seems engaged (not their first message) and you spot a natural opportunity to introduce a different product category, append a probe:
<probe>category:accessories_gaming|question:This pairs well with gaming gear — are you a gamer by any chance?|pills:["Yes, big gamer", "Casual gaming", "Not really"]</probe>

Rules for the probe block:
- Only include after at least 2 turns of conversation — never on the first response
- Never include alongside <followup> — pick one or neither
- The question must feel natural and human — never salesy or forced
- Match the category to what makes sense for the product being discussed
- Pills must directly answer the question — they submit as queries when clicked
- Omit entirely if the conversation doesn't warrant it — most responses should NOT have a probe
- Good moments: customer has chosen a product, customer asked about plans, customer seems happy, customer just committed to an add-on (peak engagement — perfect for a different-category probe)
- Bad moments: customer is comparing prices, customer asked a direct question, customer seems unsure
- AVOID probing when the customer has already initiated category expansion themselves (e.g. "show me accessories", "what else do you have"). Probes are for surprise discovery, not redundant when intent is already clear
- AFTER a successful add-on commitment, probing a NEW category is welcome — that's the peak engagement moment when the customer is enjoying the upsell journey. Pick a category they haven't explored yet
"""

# ---------------------------------------------------------------------------
# EIS helper
# ---------------------------------------------------------------------------
def call_eis(inference_id, input_text, max_tokens=500):
    response = es_client.inference.completion(
        inference_id=inference_id,
        input=input_text,
        task_settings={"max_tokens": max_tokens}
    )
    return response["completion"][0]["result"]

# ---------------------------------------------------------------------------
# Conversation summarisation — Haiku compresses old turns
# ---------------------------------------------------------------------------
def summarise_history(history):
    """
    When conversation history exceeds HISTORY_SUMMARISE_AT turns:
    - Summarise everything except the last 4 turns using Haiku
    - Return (summary_string, recent_turns_list)

    If history is within limit, return (None, full_history)
    """
    if len(history) <= HISTORY_SUMMARISE_AT:
        return None, history

    turns_to_summarise = history[:-4]
    recent_turns       = history[-4:]

    conversation_text = ""
    for turn in turns_to_summarise:
        role    = "Customer" if turn["role"] == "user" else "Tui"
        content = turn["content"]
        # Strip any <products> blocks from assistant turns before summarising
        content = re.sub(r'<products>.*?</products>', '', content, flags=re.DOTALL).strip()
        conversation_text += f"{role}: {content}\n"

    prompt = f"""Summarise this Spark NZ sales conversation concisely. Focus on:
- Which products the customer showed interest in (names, colours, storage)
- Budget or plan preferences mentioned
- Questions asked and answers given
- Any decisions or preferences expressed

Keep the summary under 100 words. Plain text only, no bullet points.

Conversation:
{conversation_text}"""

    try:
        summary = call_eis(EIS_HAIKU, prompt, max_tokens=200)
        logger.info(f"History summarised: {len(turns_to_summarise)} turns → summary")
        logger.info(f"Summary: {summary}")
        return summary.strip(), recent_turns
    except Exception as e:
        logger.warning(f"Summarisation failed, using full history: {e}")
        return None, history

# ---------------------------------------------------------------------------
# Intent extraction
# ---------------------------------------------------------------------------
def extract_intent(query, history=None):
    """
    Use Haiku to extract structured search filters.
    Passes last 2 turns of history so follow-up queries resolve correctly.
    e.g. "what colours does it come in?" after discussing S26 Ultra
         correctly extracts brand: Samsung
    """
    history_context = ""
    if history and len(history) >= 2:
        last_turns = history[-2:]
        for turn in last_turns:
            role = "Customer" if turn["role"] == "user" else "Tui"
            content = re.sub(r'<products>.*?</products>', '', turn["content"], flags=re.DOTALL).strip()
            history_context += f"{role}: {content}\n"
        history_context = f"\nRecent conversation context:\n{history_context}\n"

    # Build live category list from the cross-sell catalogue so Haiku
    # only picks from categories that actually exist in the index
    with CROSS_SELL_LOCK:
        valid_categories = ["handsets"] + sorted(CROSS_SELL_CATALOGUE.keys())
    valid_categories_str = ", ".join(f'"{c}"' for c in valid_categories)

    prompt = f"""Extract search filters from this Spark NZ product query. Return ONLY valid JSON, no explanation.

Current user query: "{query}"

{f'Recent conversation (for context only — do NOT extract prices or specs from Tui responses below):\n{history_context}' if history_context else ''}

CRITICAL: Extract filters ONLY from the current user query above. Never extract max_upfront, max_monthly, min_battery, min_camera_mp from anything Tui said in the conversation history — those are Tui's responses, not the customer's budget or requirements.

CATEGORY MUST BE ONE OF THESE EXACT VALUES (or null):
{valid_categories_str}

Do NOT invent category names. If the customer's intent doesn't match any category in the list above, set category to null.

Category mapping guide — be opinionated:
- "handsets" when query mentions: phone, mobile, handset, iPhone, Samsung, OPPO, Motorola, 5G phone, cheapest phone, fastest phone, latest phone, budget phone, or any price/speed/spec query with no other category signal
- "accessories_cases_protection" when query mentions: case, cover, screen protector, glass, protection
- "accessories_cables_chargers" when query mentions: charger, cable, charging, USB, power
- "accessories_gaming" when query mentions: gaming, controller, game console
- "accessories_speakers" when query mentions: speaker, audio, sound
- "accessories_headphones" when query mentions: headphones, earbuds, earphones, AirPods
- "accessories_smart_home" when query mentions: smart home, security camera, doorbell
- "accessories_laptop" when query mentions: laptop accessories, laptop bag, laptop charger
- "accessories_tablets" when query mentions: tablet accessories, iPad accessories, stylus, keyboard
- "accessories_wearables" when query mentions: watch band, watch strap, watch case
- "wearables" when query mentions: watch, smartwatch, fitness tracker, Apple Watch, Galaxy Watch
- "tablets" when query mentions: tablet, iPad, Galaxy Tab
- "smart_tv" when query mentions: TV, television, smart TV
- Set ambiguous=true ONLY when the query is genuinely category-neutral with no clear product signal
- Default to "handsets" for any price/budget/speed/spec query when category is unclear — do not set ambiguous
- Use conversation context ONLY to resolve brand/product references in follow-up queries (e.g. "what colours?" after discussing S26 Ultra → brand: Samsung)
- IMPORTANT: If the customer asks about a product type NOT in the valid categories list above (e.g. they ask about laptops but laptops isn't a category), set category to null — do NOT make up a category name

Other rules:
- brand: only set if explicitly named in the current query or clearly referenced from context
- max_monthly: ONLY extract if the current user query contains a monthly budget (e.g. "under $60/mo")
- max_upfront: ONLY extract if the current user query contains an upfront budget (e.g. "under $500")
- features: only include if explicitly mentioned in the current query ("5G", "eSIM", "satellite")
- min_battery/min_camera_mp: extract ONLY from spec requirements in the current query
- use_case_tags: infer from intent ("best camera" → ["camera"], "cheap/budget" → ["budget"], "top of the line/premium/flagship" → ["premium"], "latest/newest" → ["premium"], "fastest" → ["premium"])

Return format:
{{
  "intent_type": "product_search",
  "category": "handsets",
  "brand": null,
  "max_upfront": null,
  "max_monthly": null,
  "features": [],
  "min_battery": null,
  "min_camera_mp": null,
  "min_storage_gb": null,
  "use_case_tags": [],
  "ambiguous": false,
  "purchase_ready": false
}}

purchase_ready rules:
- Set purchase_ready=true ONLY when the customer clearly signals they want to proceed with a purchase
- Trigger phrases: "I'll take it", "I'll get it", "that's the one", "I want that", "add to cart", "let's do it", "perfect I'll take it", "I'm done", "show me the summary", "yes that one", "sold", "I'll buy it", "order that"
- Never set purchase_ready=true on first message or when comparing products

intent_type rules:
- "informational" — question about concepts, policies, or how things work. Examples: "What is device credit?", "How do trade-ins work?", "What does 5G mean?", "What plans do you have?", "How does interest-free work?", "What is eSIM?"
- "product_search" — customer wants to find, compare, or buy a product
- "ambiguous" — genuinely unclear product search with no category signal (e.g. "show me everything under $50", "what do you sell")
- When intent_type is "informational", set ambiguous=false and category=null"""

    try:
        raw  = es_client.inference.completion(
            inference_id=EIS_HAIKU,
            input=prompt,
            task_settings={"max_tokens": 300}
        )
        text = raw["completion"][0]["result"].strip()
        logger.info(f"Intent extraction raw: {text}")
        text   = text.replace("```json", "").replace("```", "").strip()
        intent = json.loads(text)
        logger.info(f"Extracted intent: {intent}")
        return intent

    except Exception as e:
        logger.warning(f"Intent extraction failed, defaulting to handsets: {e}")
        return {
            "intent_type": "product_search",
            "category": "handsets", "brand": None,
            "max_upfront": None, "max_monthly": None,
            "features": [], "min_battery": None,
            "min_camera_mp": None, "min_storage_gb": None,
            "use_case_tags": [], "ambiguous": False
        }

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search_products(query, intent):
    filters = [{"term": {"availability": "in_stock"}}]

    if intent.get("category"):
        filters.append({"term": {"category": intent["category"]}})
    if intent.get("brand"):
        filters.append({"term": {"brand": intent["brand"]}})
    for feature in intent.get("features", []):
        filters.append({"term": {"features": feature}})
    for tag in intent.get("use_case_tags", []):
        filters.append({"term": {"use_case_tags": tag}})
    if intent.get("max_upfront"):
        filters.append({"range": {"pricing.upfront": {"lte": intent["max_upfront"]}}})
    if intent.get("max_monthly"):
        filters.append({
            "nested": {
                "path": "payment_plans",
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"payment_plans.monthly_amount": {"lte": intent["max_monthly"]}}},
                            {"exists": {"field": "payment_plans.monthly_amount"}}
                        ]
                    }
                }
            }
        })
    if intent.get("min_battery"):
        filters.append({"range": {"specs.battery_mah": {"gte": intent["min_battery"]}}})
    if intent.get("min_camera_mp"):
        filters.append({"range": {"specs.rear_camera_mp": {"gte": intent["min_camera_mp"]}}})

    es_query = {
        "query": {
            "bool": {
                "must":   {"semantic": {"field": "search_text", "query": query}},
                "filter": filters
            }
        },
        "collapse": {
            "field": "product_name.keyword",
            "inner_hits": {
                "name": "variants",
                "size": 20,
                "_source": ["color", "storage", "pricing", "payment_plans", "availability"]
            }
        },
        "size": 5,
        "_source": [
            "product_name", "brand", "category", "color", "storage",
            "availability", "features", "use_case_tags", "pricing",
            "payment_plans", "mobile_plans", "primary_image_url",
            "gallery_urls", "source_url", "specs",
            "trade_in_eligible", "insurable"
        ]
    }

    logger.info(f"Searching: {SEARCH_INDEX} | filters: {len(filters)}")
    logger.info(f"ES query: {json.dumps(es_query, indent=2)}")
    result = es_client.search(index=SEARCH_INDEX, body=es_query)
    hits   = result["hits"]["hits"]
    took   = result.get("took", 0)
    logger.info(f"Found {len(hits)} results")
    return hits, took

# ---------------------------------------------------------------------------
# Extract products for the UI
# ---------------------------------------------------------------------------
def extract_products(results):
    products = []
    for hit in results:
        source = hit["_source"]
        name   = source.get('product_name')
        if not name:
            continue
        inner = hit.get("inner_hits", {}).get("variants", {}).get("hits", {}).get("hits", [])
        seen_v, variants = set(), []
        for vh in inner:
            vs = vh["_source"]
            if vs.get("availability") != "in_stock":
                continue
            key = (vs.get("color", ""), vs.get("storage", ""))
            if key not in seen_v:
                seen_v.add(key)
                variants.append({
                    "color":         vs.get("color"),
                    "storage":       vs.get("storage"),
                    "pricing":       vs.get("pricing", {}),
                    "payment_plans": vs.get("payment_plans", [])
                })

        products.append({
            "product_name":      name,
            "brand":             source.get('brand'),
            "category":          source.get('category'),
            "color":             source.get('color'),
            "storage":           source.get('storage'),
            "availability":      source.get('availability'),
            "features":          source.get('features', []),
            "use_case_tags":     source.get('use_case_tags', []),
            "pricing":           source.get('pricing', {}),
            "payment_plans":     source.get('payment_plans', []),
            "mobile_plans":      source.get('mobile_plans', []),
            "primary_image_url": source.get('primary_image_url'),
            "gallery_urls":      source.get('gallery_urls', []),
            "url":               source.get('source_url'),
            "specs":             source.get('specs', {}),
            "trade_in_eligible": source.get('trade_in_eligible', False),
            "insurable":         source.get('insurable', False),
            "variants":          variants
        })
        logger.info(f"Product: {name} | {source.get('color')} | {source.get('storage')}")
    return products

# ---------------------------------------------------------------------------
# Build LLM context
# ---------------------------------------------------------------------------
def create_context(results):
    context = ""
    for i, hit in enumerate(results, 1):
        source = hit["_source"]
        parts  = []

        label = " ".join(filter(None, [
            source.get('product_name', ''),
            source.get('color', ''),
            source.get('storage', '')
        ]))
        parts.append(f"Product: {label}")
        if source.get('brand'):
            parts.append(f"Brand: {source['brand']}")

        pricing = source.get('pricing', {})
        if pricing.get('upfront'):        parts.append(f"Upfront: ${pricing['upfront']}")
        if pricing.get('net_after_credit'): parts.append(f"After credit: ${pricing['net_after_credit']}")
        if pricing.get('device_credit'):  parts.append(f"Device credit: ${pricing['device_credit']}")
        if pricing.get('min_monthly'):    parts.append(f"From: ${pricing['min_monthly']}/mo")

        plans = source.get('payment_plans', [])
        if plans:
            plan_lines = [
                f"{p['term_months']}mo @ ${p['monthly_amount']}/mo (deposit ${p['min_deposit']})"
                for p in plans
            ]
            parts.append(f"Payment options: {' | '.join(plan_lines)}")

        mobile_plans = source.get('mobile_plans', [])
        if mobile_plans:
            consumer = [
                p for p in mobile_plans
                if p.get('plan_id', '').startswith('mbundle07') and p.get('monthly_price')
            ][:3]
            for p in consumer:
                mo36   = p.get('ifp_monthly', {}).get('months_36', '')
                credit = p.get('credit_amount', '')
                parts.append(f"Plan: {p['name']} — device ${mo36}/mo on 36mo | credit ${credit}")

        specs = source.get('specs', {})
        spec_parts = []
        if specs.get('display_inches'):  spec_parts.append(f"{specs['display_inches']}\" display")
        if specs.get('battery_mah'):     spec_parts.append(f"{specs['battery_mah']}mAh")
        if specs.get('rear_camera_mp'):  spec_parts.append(f"{specs['rear_camera_mp']}MP camera")
        if specs.get('zoom_x'):          spec_parts.append(f"{specs['zoom_x']}x zoom")
        if specs.get('processor'):       spec_parts.append(specs['processor'])
        if specs.get('ip_rating'):       spec_parts.append(specs['ip_rating'])
        if spec_parts:
            parts.append(f"Specs: {', '.join(spec_parts)}")

        inner = hit.get("inner_hits", {}).get("variants", {}).get("hits", {}).get("hits", [])
        colors, storages, seen_v = [], [], set()
        for vh in inner:
            vs = vh["_source"]
            if vs.get("availability") != "in_stock":
                continue
            key = (vs.get("color", ""), vs.get("storage", ""))
            if key not in seen_v:
                seen_v.add(key)
                c, s = vs.get("color"), vs.get("storage")
                if c and c not in colors:
                    colors.append(c)
                if s and s not in storages:
                    storages.append(s)
        if len(colors) > 1:
            parts.append(f"Available colours: {', '.join(colors)}")
        if len(storages) > 1:
            parts.append(f"Available storage: {', '.join(storages)}")

        if source.get('features'):      parts.append(f"Features: {', '.join(source['features'])}")
        if source.get('use_case_tags'): parts.append(f"Best for: {', '.join(source['use_case_tags'])}")
        if source.get('trade_in_eligible'): parts.append("Trade-in eligible")
        if source.get('insurable'):         parts.append("Device Protect available")
        if source.get('source_url'):        parts.append(f"URL: {source['source_url']}")

        context += f"[{i}] " + " | ".join(parts) + "\n\n"

    return context

# ---------------------------------------------------------------------------
# Generate response — Sonnet via EIS with conversation history
# ---------------------------------------------------------------------------
def generate_response(context, question, history=None, summary=None, cross_sell_context=""):
    """
    Builds the full prompt including:
      - System prompt
      - Cross-sell catalogue (when history >= 2 turns)
      - Conversation summary (if history was compressed)
      - Recent raw history turns
      - Current product context
      - Current question
    """
    prompt_parts = [SYSTEM_PROMPT]

    # Inject cross-sell catalogue only when conversation has some depth
    if cross_sell_context and history and len(history) >= 2:
        prompt_parts.append(f"\n## Available cross-sell categories at Spark\nUse these to inform probe questions:\n{cross_sell_context}")

    if summary:
        prompt_parts.append(f"\n## Previous conversation summary\n{summary}")

    if history:
        prompt_parts.append("\n## Recent conversation")
        for turn in history:
            role    = "Customer" if turn["role"] == "user" else "Tui"
            content = re.sub(r'<products>.*?</products>', '', turn["content"], flags=re.DOTALL).strip()
            content = re.sub(r'<probe>.*?</probe>', '', content, flags=re.DOTALL).strip()
            prompt_parts.append(f"{role}: {content}")

    prompt_parts.append(f"\n## Current product context\n{context}")
    prompt_parts.append(f"\nCustomer: {question}")

    prompt = "\n".join(prompt_parts)

    try:
        raw = es_client.inference.completion(
            inference_id=EIS_SONNET,
            input=prompt,
            task_settings={"max_tokens": 600}
        )
        full_text = raw["completion"][0]["result"]

        # Parse <products> ranking block
        ranked_indices  = []
        tui_suggestions = []
        tui_followup    = None
        tui_probe       = None
        prose           = full_text

        match_p = re.search(r'<products>(.*?)</products>', full_text, re.DOTALL)
        if match_p:
            try:
                ranked_indices = json.loads(match_p.group(1).strip())
                ranked_indices = [str(i) for i in ranked_indices]
            except Exception:
                pass

        match_s = re.search(r'<suggestions>(.*?)</suggestions>', full_text, re.DOTALL)
        if match_s:
            try:
                tui_suggestions = json.loads(match_s.group(1).strip())
                tui_suggestions = [str(s).strip() for s in tui_suggestions if s]
            except Exception:
                pass

        match_f = re.search(r'<followup>(.*?)</followup>', full_text, re.DOTALL)
        if match_f:
            tui_followup = match_f.group(1).strip()

        # Parse <probe> block — format: category:X|question:Y|pills:["A","B","C"]
        match_pb = re.search(r'<probe>(.*?)</probe>', full_text, re.DOTALL)
        if match_pb:
            try:
                probe_raw = match_pb.group(1).strip()
                probe_parts = dict(
                    part.split(":", 1) for part in probe_raw.split("|") if ":" in part
                )
                tui_probe = {
                    "category": probe_parts.get("category", "").strip(),
                    "question": probe_parts.get("question", "").strip(),
                    "pills":    json.loads(probe_parts.get("pills", "[]"))
                }
            except Exception as e:
                logger.warning(f"Probe parse failed: {e}")

        # Strip all blocks from prose
        prose = re.sub(r'<products>.*?</products>', '', full_text, flags=re.DOTALL)
        prose = re.sub(r'<suggestions>.*?</suggestions>', '', prose, flags=re.DOTALL)
        prose = re.sub(r'<followup>.*?</followup>', '', prose, flags=re.DOTALL)
        prose = re.sub(r'<probe>.*?</probe>', '', prose, flags=re.DOTALL)
        prose = prose.strip()

        logger.info(f"Tui ranked product indices: {ranked_indices}")
        logger.info(f"Tui suggestions: {tui_suggestions}")
        logger.info(f"Tui followup: {tui_followup}")
        logger.info(f"Tui probe: {tui_probe}")
        # Token counts — EIS returns them on the raw response object
        usage            = raw.get("meta", {}).get("usage", {})
        prompt_tokens    = usage.get("prompt_token_count",     0)
        completion_tokens = usage.get("response_token_count",  0)

        return prose, ranked_indices, tui_suggestions, tui_followup, tui_probe, prompt_tokens, completion_tokens

    except Exception as e:
        logger.error(f"EIS response generation error: {e}")
        raise

# ---------------------------------------------------------------------------
# Generate suggestions
# ---------------------------------------------------------------------------
def generate_smart_suggestions(context, user_question, ai_response, products):
    brands   = list({p.get('brand') for p in products if p.get('brand')})
    upfronts = [p['pricing']['upfront'] for p in products if p.get('pricing', {}).get('upfront')]
    price_range = f"${min(upfronts):.0f}–${max(upfronts):.0f}" if upfronts else "varied"

    prompt = f"""Generate 4 short follow-up questions for a Spark NZ product conversation.

Customer asked: "{user_question}"
Products shown: brands={brands}, price range={price_range}

Rules:
- Never start with "Would you", "What are your", "Do you", "Are you"
- Product-focused and actionable only
- Under 8 words each
- Specific to Spark NZ products and plans

Return ONLY a JSON array of 4 strings.
Example: ["Compare S26 Ultra vs iPhone 17", "Show Samsung cases", "Best plan for heavy data use?", "Any trade-in deals?"]"""

    try:
        raw  = es_client.inference.completion(
            inference_id=EIS_HAIKU,
            input=prompt,
            task_settings={"max_tokens": 200}
        )
        text = raw["completion"][0]["result"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        suggestions = json.loads(text)
        if isinstance(suggestions, list) and suggestions:
            return [str(s).strip() for s in suggestions[:4] if s]
    except Exception as e:
        logger.warning(f"Suggestions generation failed: {e}")

    return ["Show available colours", "Compare similar phones", "What plans are available?", "Any accessories for this?"]

# ---------------------------------------------------------------------------
# Extract source details
# ---------------------------------------------------------------------------
def extract_source_details(results):
    source_details = []
    for i, hit in enumerate(results, 1):
        source = hit["_source"]
        source_details.append({
            'index': i,
            'title': source.get('product_name') or f"Product {i}",
            'url':   source.get('source_url', ''),
            'host':  'spark.co.nz'
        })
    return source_details

# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------
@app.route('/query', methods=['POST'])
def query_products():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        query          = data.get('text', '').strip()
        history        = data.get('history', [])  # conversation history from overlay.js
        click_source   = data.get('click_source')   # "suggestion" | "probe" | "followup" | None
        probe_category = data.get('probe_category')  # e.g. "accessories_gaming" (probe only)

        if not query:
            return jsonify({"error": "No query provided"}), 400

        logger.info(f"Query: '{query}' | History turns: {len(history)}" + (f" | source={click_source}" if click_source else ""))
        start_time = time.time()

        # 1. Summarise history if needed — keeps payload lean for long conversations
        summary, recent_history = summarise_history(history)
        if summary:
            logger.info(f"Using summarised history + {len(recent_history)} recent turns")

        # 2. Extract intent — passes recent history for follow-up resolution
        intent = extract_intent(query, recent_history)

        # 3. Informational query — answer from knowledge, skip ES search
        if intent.get("intent_type") == "informational":
            logger.info("Informational query — skipping ES search, answering from knowledge")
            info_context = "The customer is asking a general question about Spark NZ products, plans, or policies. Answer from your knowledge as Tui. Do not make up specific prices or product names."
            ai_response, _, tui_suggestions, tui_followup, tui_probe, _pt, _ct = generate_response(
                info_context, query, recent_history, summary,
                cross_sell_context=format_cross_sell_catalogue()
            )
            suggestions = tui_suggestions or ["Show me phones", "What plans are available?", "How does trade-in work?", "Any current deals?"]
            return jsonify({
                "response":      ai_response,
                "sources":       0,
                "products":      [],
                "sourceDetails": [],
                "suggestions":   suggestions,
                "followup":      tui_followup,
                "probe":         tui_probe,
                "intent":        intent
            })

        # 4. Ambiguous query — clarification flow
        # Skip when history exists: Sonnet can resolve the query from conversation context
        if intent.get("ambiguous") and not summary and not recent_history:
            logger.info("Ambiguous query — returning clarification response")
            return jsonify({
                "response":      "I can help with that! What are you looking for?",
                "sources":       0,
                "products":      [],
                "sourceDetails": [],
                "suggestions":   [
                    "📱 Show me phones",
                    "🛡️ Show me cases and protection",
                    "🔌 Show me chargers and cables",
                    "🎮 Show me accessories"
                ],
                "intent": intent
            })

        # 5. Purchase ready — summarise from history, skip ES entirely
        if intent.get("purchase_ready"):
            logger.info("Purchase ready — generating order summary from conversation history")
            purchase_context = (
                "The customer has finished browsing and is ready to buy. "
                "Using the conversation history, write a brief order summary listing "
                "what they chose with prices. Keep it under 60 words. "
                "End with: 'To complete your order, visit spark.co.nz or call 0800 800 123.'"
            )
            ai_response, _, tui_suggestions, tui_followup, _probe, _pt, _ct = generate_response(
                purchase_context, query, recent_history, summary, cross_sell_context=""
            )
            return jsonify({
                "response":      ai_response,
                "sources":       0,
                "products":      [],
                "sourceDetails": [],
                "suggestions":   tui_suggestions or ["Visit spark.co.nz", "Call 0800 800 123", "Start a new search"],
                "followup":      tui_followup,
                "probe":         None,
                "intent":        intent,
                "show_cart":     True,
                "cart_product":  None
            })

        # 6. Search with semantic + hard filters
        # Create a named "search" span — search.* attributes live here as a
        # child of the Flask request span. Matches the hierarchy described in
        # https://github.com/elastic/search-analytics-otel-reference
        with _tracer.start_as_current_span("search") as span:
            query_id = format(span.get_span_context().trace_id, "032x")
            span.set_attribute("search.action",      "search")
            span.set_attribute("search.user_query",  query.strip().lower())
            span.set_attribute("search.application", "spark-tui")
            span.set_attribute("search.query_id",    query_id)
            if click_source:
                span.set_attribute("search.click_source",   click_source)
            if probe_category:
                span.set_attribute("search.probe_category", probe_category)

            results, took_ms = search_products(query, intent)
            price_constraint_failed = False

            if not results:
                logger.info("No results with full filters, retrying with category only")
                fallback_intent = {"category": intent.get("category"), "ambiguous": False}
                results, took_ms = search_products(query, fallback_intent)
                if results and (intent.get("max_upfront") or intent.get("max_monthly")):
                    price_constraint_failed = True
                    logger.info(f"Price constraint failed — max_upfront={intent.get('max_upfront')} max_monthly={intent.get('max_monthly')}")

            # Set after fallback so count reflects what the user actually saw
            span.set_attribute("search.result_count", len(results))
            span.set_attribute("search.took_ms",      took_ms)

        if not results:
            return jsonify({
                "response":      "I couldn't find any matching in-stock products. Try different keywords or ask me something else!",
                "sources":       0,
                "products":      [],
                "sourceDetails": [],
                "query_id":      query_id,
                "suggestions":   ["Show all phones", "Cheapest 5G phone", "Show me accessories", "What plans are available?"]
            })

        # 5. Build response
        products = extract_products(results)
        context  = create_context(results)

        # Tell Tui if the price filter failed
        if price_constraint_failed:
            if intent.get("max_upfront"):
                context = f"IMPORTANT: The customer asked for products under ${intent['max_upfront']} upfront but no products exist at that price. Show them the cheapest available options and be upfront about it.\n\n{context}"
            elif intent.get("max_monthly"):
                context = f"IMPORTANT: The customer asked for products under ${intent['max_monthly']}/mo but no products exist at that monthly price. Show them the cheapest available options and be upfront about it.\n\n{context}"

        # ── (3) Intent quality span ─────────────────────────────────────────
        with _tracer.start_as_current_span("intent_extraction") as intent_span:
            intent_span.set_attribute("intent.type",              intent.get("intent_type", "unknown"))
            intent_span.set_attribute("intent.category",          intent.get("category") or "none")
            intent_span.set_attribute("intent.brand",             intent.get("brand") or "none")
            intent_span.set_attribute("intent.ambiguous",         bool(intent.get("ambiguous")))
            intent_span.set_attribute("intent.fallback_triggered", price_constraint_failed)
            intent_span.set_attribute("intent.filter_count",      len([v for v in intent.values() if v and v not in [[], None, False]]))

        # ── (4) Conversation context — on the Flask root span ────────────────
        root_span = trace.get_current_span()
        root_span.set_attribute("chat.history_turns",  len(history))
        root_span.set_attribute("chat.summary_used",   summary is not None)
        root_span.set_attribute("chat.session_id",     request.headers.get("X-Session-Id", "unknown"))

        # ── (1) LLM response generation span ────────────────────────────────
        with _tracer.start_as_current_span("response_generation") as llm_span:
            llm_span.set_attribute("llm.model",         EIS_SONNET)
            llm_span.set_attribute("llm.max_tokens",    600)

            ai_response, ranked_indices, tui_suggestions, tui_followup, tui_probe, prompt_tokens, completion_tokens = generate_response(
                context, query, recent_history, summary,
                cross_sell_context=format_cross_sell_catalogue()
            )

            # Token visibility
            llm_span.set_attribute("llm.prompt_tokens",     prompt_tokens)
            llm_span.set_attribute("llm.completion_tokens", completion_tokens)
            llm_span.set_attribute("llm.total_tokens",      prompt_tokens + completion_tokens)

            # Grounding check — did Tui mention products that were actually in context?
            context_product_names = [p.get("product_name", "").lower() for p in products]
            mentioned = [name for name in context_product_names if name and name in ai_response.lower()]
            llm_span.set_attribute("llm.grounded",           len(mentioned) > 0)
            llm_span.set_attribute("llm.grounded_product_count", len(mentioned))

            # ── (5) Response quality signals ────────────────────────────────
            llm_span.set_attribute("response.product_count",         len(products))
            llm_span.set_attribute("response.has_followup",          tui_followup is not None)
            llm_span.set_attribute("response.has_probe",             tui_probe is not None)
            llm_span.set_attribute("response.price_constraint_failed", price_constraint_failed)
            llm_span.set_attribute("response.used_tui_suggestions",  len(tui_suggestions) > 0)

        source_details = extract_source_details(results)

        # Use Tui's own suggestions — fall back to Haiku only if empty
        if tui_suggestions:
            suggestions = tui_suggestions
            logger.info(f"Using Tui suggestions: {suggestions}")
        else:
            suggestions = generate_smart_suggestions(context, query, ai_response, products)
            logger.info(f"Using Haiku suggestions: {suggestions}")

        # Reorder carousel by Tui's ranking
        if ranked_indices:
            index_map        = {str(i + 1): products[i] for i in range(len(products))}
            ordered_products = [index_map[i] for i in ranked_indices if i in index_map]
        else:
            ordered_products = products

        latency_ms = round((time.time() - start_time) * 1000)

        response_data = {
            "response":      ai_response,
            "sources":       len(results),
            "products":      ordered_products,
            "sourceDetails": source_details,
            "suggestions":   suggestions,
            "followup":      tui_followup,
            "probe":         tui_probe,
            "intent":        intent,
            "query_id":      query_id,
            "show_cart":     bool(intent.get("purchase_ready")),
            "cart_product":  ordered_products[0] if intent.get("purchase_ready") and ordered_products else None
        }

        if DEBUG_BAR:
            active_filters = [k for k, v in intent.items() if v and v not in [[], None, False]]
            response_data["debugBar"] = {
                "index":        SEARCH_INDEX,
                "hits":         len(results),
                "latency_ms":   latency_ms,
                "query_type":   f"semantic + {len(active_filters)} intent filters",
                "history_turns": len(history),
                "summarised":   summary is not None
            }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        return jsonify({
            "error":   "Something went wrong. Please try again.",
            "details": str(e) if app.debug else None
        }), 500

# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Lookup endpoint — matches a Spark product page URL to index documents
# and returns a proactive Tui greeting for that product
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Lookup endpoint — proactive upsell greeting for product pages
# ---------------------------------------------------------------------------
@app.route('/lookup', methods=['POST'])
def lookup_product():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"matched": False}), 400

        page_url = data.get('url', '').strip()
        if not page_url:
            return jsonify({"matched": False}), 400

        logger.info(f"Lookup: {page_url}")

        slug_match = re.search(r'/products/([^/?#]+)', page_url)
        if not slug_match:
            return jsonify({"matched": False})

        slug = slug_match.group(1)
        logger.info(f"Lookup slug: {slug}")

        # --- Query 1: Find all in-stock variants for this product page ---
        result = es_client.search(index=SEARCH_INDEX, body={
            "query": {
                "bool": {
                    "must": [
                        {"term":     {"availability": "in_stock"}},
                        {"wildcard": {"source_url": f"*{slug}*"}}
                    ]
                }
            },
            "size": 5,
            "_source": [
                "product_name", "brand", "category", "color", "storage",
                "availability", "features", "use_case_tags", "pricing",
                "payment_plans", "mobile_plans", "primary_image_url",
                "gallery_urls", "source_url", "specs",
                "trade_in_eligible", "insurable"
            ]
        })
        hits = result["hits"]["hits"]

        if not hits:
            logger.info(f"Lookup: no match for '{slug}'")
            return jsonify({"matched": False})

        logger.info(f"Lookup: {len(hits)} variants for '{slug}'")

        first       = hits[0]["_source"]
        product_name = first.get("product_name", "this product")
        brand        = first.get("brand", "")
        category     = first.get("category", "")
        insurable    = first.get("insurable", False)
        is_handset   = category == "handsets"
        products     = extract_products(hits)

        # --- Build plan upsell context (handsets only) ---
        # Sort plans most expensive first — sales life
        mobile_plans = first.get("mobile_plans", []) if is_handset else []
        consumer_plans = sorted(
            [p for p in mobile_plans if p.get("plan_id", "").startswith("mbundle07") and p.get("monthly_price")],
            key=lambda p: p.get("monthly_price", 0),
            reverse=True  # most expensive first
        )[:3]

        plans_context = ""
        for p in consumer_plans:
            perks = []
            if p.get("streaming_perks"):
                perks += [s.capitalize() for s in p["streaming_perks"]]
            if p.get("includes_satellite"):
                perks.append("Spark Satellite")
            if p.get("includes_roaming_au"):
                perks.append("AU Roaming")
            if p.get("team_up_discount"):
                perks.append(f"Team Up from ${p['team_up_min_price']}/mo")

            mo36 = p.get("ifp_monthly", {}).get("months_36", "")
            credit = p.get("credit_amount", 0)
            perk_str = f" — includes {', '.join(perks)}" if perks else ""
            plans_context += f"- {p['name']} (${p['monthly_price']}/mo): device ${mo36}/mo on 36mo, ${credit} credit{perk_str}\n"

        # --- Query 2: Compatible accessories ---
        # Use Haiku to extract model keyword variants from the slug
        # e.g. "samsung-galaxy-s26-ultra-5g" → ["Galaxy S26 Ultra", "S26 Ultra", "S26"]
        accessories = []
        model_keywords = []

        try:
            slug_parse_prompt = f"""Extract phone model name variants from this Spark NZ product URL slug for accessory compatibility matching.

Slug: "{slug}"

Return a JSON array of 2-4 model name variants, from most specific to least specific.
These will be used to query a "compatible_models" field in an accessories index.

Examples:
- "samsung-galaxy-s26-ultra-5g" → ["Galaxy S26 Ultra", "S26 Ultra", "S26"]
- "apple-iphone-17-pro-max" → ["iPhone 17 Pro Max", "17 Pro Max", "iPhone 17"]
- "oppo-find-n6" → ["Find N6", "OPPO Find N6"]
- "samsung-galaxy-z-fold7-5g" → ["Galaxy Z Fold7", "Z Fold7", "Galaxy Z Fold"]

Return ONLY a valid JSON array of strings, no explanation."""

            raw_keywords = es_client.inference.completion(
                inference_id=EIS_HAIKU,
                input=slug_parse_prompt,
                task_settings={"max_tokens": 100}
            )
            kw_text = raw_keywords["completion"][0]["result"].strip()
            kw_text = kw_text.replace("```json", "").replace("```", "").strip()
            model_keywords = json.loads(kw_text)
            logger.info(f"Lookup model keywords: {model_keywords}")

        except Exception as e:
            logger.warning(f"Slug keyword extraction failed: {e}")

        if model_keywords:
            should_clauses = [
                {"term": {"compatible_models": kw}} for kw in model_keywords
            ]
            acc_result = es_client.search(index=SEARCH_INDEX, body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"availability": "in_stock"}},
                            {"terms": {"category": [
                                "accessories_cases_protection",
                                "accessories_cables_chargers",
                                "accessories_gaming",
                                "accessories_speakers"
                            ]}}
                        ],
                        "should": should_clauses,
                        "minimum_should_match": 1
                    }
                },
                "size": 4,
                "_source": [
                    "product_name", "brand", "category", "color", "pricing",
                    "primary_image_url", "source_url", "compatible_models"
                ]
            })
            accessories = extract_products(acc_result["hits"]["hits"])
            logger.info(f"Lookup: {len(accessories)} compatible accessories found")
        else:
            logger.info("Lookup: no model keywords extracted, skipping accessories query")

        # --- Build insurance context ---
        insurance_line = "Spark Device Protect insurance is available for this device." if insurable else ""

        # --- Generate greeting — plan upsell for handsets, simple assist for everything else ---
        if consumer_plans:
            greeting_prompt = f"""You are Tui, a friendly Spark NZ sales assistant.

A customer just opened the chat while browsing the {product_name} page on spark.co.nz.
They already know what the product is — do NOT describe specs or features they can read on the page.

Your job: jump straight to the best deal. Lead with the most expensive plan first (that's the upsell), mention the key perk that makes it worth it, then offer to help them explore.

Available plans (most expensive first):
{plans_context}
{insurance_line}

Rules:
- Max 3 sentences
- Skip any opening greeting — jump straight to the deal
- Lead with the highest-value plan and its standout perk (Netflix, satellite, AU roaming)
- Mention the device credit
- End with one natural offer to help — not a question list
- Never describe the product specs

Good example for S26 Ultra:
"The best deal on the S26 Ultra right now is the $95 Unlimited Netflix Plan — unlimited data, Netflix Standard included, plus a $600 device credit bringing it to $51.39/mo. Want me to walk you through all the plan options?"

Generate the greeting now.
<products>{json.dumps([str(i+1) for i in range(min(len(hits), 3))])}</products>
<suggestions>["Show all plan options", "Tell me about Device Protect", "Any compatible cases?", "What's the trade-in value?"]</suggestions>"""
        else:
            # Build probe context from affinity map + cross-sell catalogue
            affinity_cats = CATEGORY_AFFINITY.get(category, [])
            probe_context = ""
            with CROSS_SELL_LOCK:
                available_probes = [
                    (cat, CROSS_SELL_CATALOGUE[cat])
                    for cat in affinity_cats
                    if cat in CROSS_SELL_CATALOGUE
                ]
            if available_probes:
                lines = []
                for cat, info in available_probes:
                    readable = cat.replace("accessories_", "").replace("_", " ").title()
                    examples = ", ".join(info.get("examples", [])[:2])
                    lines.append(f"- {readable}: {examples}" if examples else f"- {readable}")
                probe_context = "Available cross-sell categories to probe:\n" + "\n".join(lines)

            greeting_prompt = f"""You are Tui, a friendly Spark NZ sales assistant.

A customer just opened the chat while browsing the {product_name} page on spark.co.nz.
They already know what the product is — do NOT describe specs or features they can read on the page.
This is a {category.replace("_", " ")} product. Do NOT mention mobile plans, device credits, or monthly plan pricing.
{insurance_line}

{probe_context}

Your job:
1. One short sentence that acknowledges they're looking at something great (no specs)
2. Ask a creative dual-path lifestyle question that feels like genuine curiosity — where BOTH pill answers reveal a different cross-sell need

Rules:
- Max 1 sentence of prose before the probe
- Skip any opening greeting
- The probe question must bridge naturally from the product to a lifestyle interest
- Pills should represent distinct lifestyles — both answers open different but valid cross-sell paths
- Pick ONE probe category from the available list above that best fits the conversation

Output format — always append these structured blocks after the prose:

<products>["1","2"]</products>
<suggestions>["suggestion 1", "suggestion 2", "suggestion 3", "suggestion 4"]</suggestions>
<probe>category:accessories_gaming|question:Your probe question here?|pills:["Pill 1", "Pill 2", "Pill 3"]</probe>

Good example for a Smart TV:
Prose: "Great choice for a home cinema setup."
<products>["1","2","3"]</products>
<suggestions>["Find compatible accessories", "What's in the box?", "Tell me about Device Protect", "Any current deals?"]</suggestions>
<probe>category:accessories_gaming|question:Quick question — do you tend to use your TV more for gaming, or for streaming movies and shows?|pills:["I game on it", "Streaming & movies", "Both!", "Just browsing"]</probe>

Generate the greeting now."""

        raw = es_client.inference.completion(
            inference_id=EIS_SONNET,
            input=greeting_prompt,
            task_settings={"max_tokens": 350}
        )
        full_text = raw["completion"][0]["result"]

        # Parse blocks
        ranked_indices  = [str(i+1) for i in range(min(len(hits), 3))]
        tui_suggestions = (
            ["Show all plan options", "Tell me about Device Protect", "Any compatible cases?", "What's the trade-in value?"]
            if is_handset else
            ["Find compatible accessories", "What's in the box?", "Tell me about Device Protect", "Any current deals?"]
        )
        prose           = full_text

        match_p = re.search(r'<products>(.*?)</products>', full_text, re.DOTALL)
        if match_p:
            try: ranked_indices = json.loads(match_p.group(1).strip())
            except: pass

        match_s = re.search(r'<suggestions>(.*?)</suggestions>', full_text, re.DOTALL)
        if match_s:
            try: tui_suggestions = json.loads(match_s.group(1).strip())
            except: pass

        tui_probe = None
        match_probe = re.search(r'<probe>(.*?)</probe>', full_text, re.DOTALL)
        if match_probe:
            try:
                probe_parts = dict(part.split(":", 1) for part in match_probe.group(1).strip().split("|") if ":" in part)
                tui_probe = {
                    "category": probe_parts.get("category", ""),
                    "question": probe_parts.get("question", ""),
                    "pills":    json.loads(probe_parts.get("pills", "[]"))
                }
            except: pass

        prose = re.sub(r'<products>.*?</products>', '', full_text, flags=re.DOTALL)
        prose = re.sub(r'<suggestions>.*?</suggestions>', '', prose, flags=re.DOTALL)
        prose = re.sub(r'<probe>.*?</probe>', '', prose, flags=re.DOTALL)
        prose = prose.strip()

        # Reorder product variants by Tui ranking
        index_map        = {str(i + 1): products[i] for i in range(len(products))}
        ordered_products = [index_map[i] for i in ranked_indices if i in index_map] or products

        logger.info(f"Lookup greeting generated for: {product_name}")
        logger.info(f"Lookup accessories: {len(accessories)}")

        return jsonify({
            "matched":      True,
            "product":      product_name,
            "response":     prose,
            "accessories":  accessories,
            "suggestions":  tui_suggestions,
            "probe":        tui_probe,
            "insurable":    insurable
        })

    except Exception as e:
        logger.error(f"Lookup error: {str(e)}")
        return jsonify({"matched": False, "error": str(e)}), 500



# ---------------------------------------------------------------------------
# Click endpoint — records product card clicks as OTel spans
# Enables CTR, MRR, and click position distribution in ES|QL
# ---------------------------------------------------------------------------
import threading as _threading

_clicked_queries: set = set()
_clicked_queries_lock = _threading.Lock()

@app.route('/click', methods=['POST'])
def track_click():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"ok": False}), 400

        object_id  = data.get('object_id', '')
        position   = data.get('position', 0)
        query_id   = data.get('query_id', '')
        user_query = data.get('user_query', '')

        current_span = trace.get_current_span()
        current_span.set_attribute("search.action",                "click")
        current_span.set_attribute("search.result_click_id",       object_id)
        current_span.set_attribute("search.result_click_position", int(position))
        current_span.set_attribute("search.result_click_type",     "product")
        current_span.set_attribute("search.query_id",              query_id)
        if user_query:
            current_span.set_attribute("search.user_query", user_query.strip().lower())

        with _clicked_queries_lock:
            is_first = query_id not in _clicked_queries
            if is_first:
                _clicked_queries.add(query_id)

        current_span.set_attribute("search.first_click", str(is_first).lower())

        logger.info(f"Click: pos={position} query_id={query_id[:8]}… first={is_first}")
        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Click tracking error: {e}")
        return jsonify({"ok": False}), 500


@app.route('/status', methods=['GET'])
def status_check():
    try:
        es_info = es_client.info()
        return jsonify({
            "status": "OK",
            "elasticsearch": {
                "status":       "connected",
                "cluster_name": es_info.get("cluster_name", "unknown"),
                "index":        SEARCH_INDEX
            },
            "eis": {
                "intent":        EIS_HAIKU,
                "response":      EIS_SONNET,
                "summarisation": EIS_HAIKU
            },
            "conversation": {
                "raw_limit":      HISTORY_RAW_LIMIT,
                "summarise_at":   HISTORY_SUMMARISE_AT
            }
        })
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 500

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    required_vars = ["ELASTIC_CLOUD_ID", "ELASTIC_API_KEY"]
    missing_vars  = [v for v in required_vars if not os.environ.get(v)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)

    logger.info(f"Starting Tui — Spark NZ sales assistant")
    logger.info(f"Index: {SEARCH_INDEX} | EIS Haiku: {EIS_HAIKU} | EIS Sonnet: {EIS_SONNET}")
    logger.info(f"Conversation: summarise after {HISTORY_SUMMARISE_AT} turns, keep {HISTORY_RAW_LIMIT} raw")
    logger.info(f"Debug bar: {DEBUG_BAR}")

    # Load cross-sell catalogue on startup
    schedule_catalogue_refresh()

    app.run(host='0.0.0.0', port=5000, debug=True)
