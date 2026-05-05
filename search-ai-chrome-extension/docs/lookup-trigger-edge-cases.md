# Lookup Trigger Edge Cases

Scenarios resolved before implementing slug-aware `triggerProductLookup()` logic.
Current condition: fire lookup if on a product page, `alreadyGreetedThisProduct` is false, and `lookupFired` is false.

---

## Scenario 1 — Mid-conversation navigation to a product page

**Decision: Append**
Product greeting appends below existing conversation. `messagesContainer.innerHTML` is NOT cleared. User keeps their conversation context and sees the product greeting added below.

**Status: ✅ Implemented**

---

## Scenario 2 — Navigating between two product pages

**Decision: Only fire once per session**
`lookupFired` boolean blocks any subsequent lookup after the first one fires. Prevents jarring greeting interruptions when the user is browsing multiple product pages.

**Status: ✅ Implemented**

---

## Scenario 3 — Return visit to the same product page

**Decision: No action needed**
`alreadyGreetedThisProduct` checks `conversationHistory` for the current slug — lookup blocked if already greeted. Existing conversation is restored.

**Status: ✅ Implemented**

---

## Scenario 4 — Lookup fires but server is down

**Decision: Acceptable**
Silent failure — `catch` block removes typing indicator, welcome message stays. `AbortError` distinguished from network errors in the catch handler.

**Status: ✅ Implemented**

---

## Scenario 5 — Product slug exists in URL but not in the index

**Decision: Acceptable**
`matched: false` returned, welcome message stays. Fine for demo purposes.

**Status: ✅ Implemented — no action needed**

---

## Scenario 6 — Long conversation, then navigate to product page

**Decision: Append**
Same as Scenario 1 — product greeting appends regardless of history length. No conversation history is lost from the UI.

**Status: ✅ Implemented**

---

## Scenario 7 — User types before lookup completes

**Decision: Add `lookupInFlight` flag**
`sendQuery()` calls `lookupController.abort()` if a lookup is in flight. Lookup `catch` block detects `AbortError` and exits cleanly without an error log.

**Status: ✅ Implemented**

---

## Additional — Demo reset button

A `⟳` reset button added to the chat header for demo purposes. Clicking it:
- Clears `chrome.storage.local` history
- Wipes the messages container
- Resets `lookupFired`, `lookupInFlight`, `lookupController`
- Re-shows the welcome message
- Re-triggers lookup if currently on a product page

Hover state turns red to signal destructive action. Requires deploying both `overlay.js` and `overlay.css`.

---

## Implementation checklist

- [x] `lookupFired` — session boolean, blocks any second lookup (Scenario 2)
- [x] `alreadyGreetedThisProduct` — checks history for current slug (Scenario 3)
- [x] `lookupInFlight` + `lookupController` — abortable fetch flag (Scenario 7)
- [x] Removed `messagesContainer.innerHTML = ''` from lookup success path (Scenarios 1 + 6)
- [x] Removed `conversationHistory.length === 0` guard — replaced with proper conditions
- [x] Demo reset button — resets all state including lookup flags

## Summary

| # | Scenario | Decision | Status |
|---|---|---|---|
| 1 | Mid-conversation → product page | Append | ✅ |
| 2 | Navigate between product pages | Once per session only | ✅ |
| 3 | Return to same product page | No action — handled | ✅ |
| 4 | Server down during lookup | Acceptable | ✅ |
| 5 | Slug not in index | Acceptable | ✅ |
| 6 | Long conversation → product page | Append | ✅ |
| 7 | User types before lookup completes | `lookupInFlight` abort flag | ✅ |
| — | Demo reset button | Added to header | ✅ |
