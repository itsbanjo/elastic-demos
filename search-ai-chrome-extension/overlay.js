// overlay.js - Spark NZ assistant with conversation history

// ---------------------------------------------------------------------------
// Markdown parser
// ---------------------------------------------------------------------------
function parseMarkdown(text) {
  if (!text) return '';

  // ---------------------------------------------------------------------------
  // Parse tables first — before any other processing touches the newlines
  // Works by scanning line-by-line for pipe-delimited rows
  // ---------------------------------------------------------------------------
  function parseTables(input) {
    const lines  = input.split('\n');
    const output = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // Detect a table header row — starts and ends with |
      if (/^\|.+\|/.test(line.trim())) {
        // Check next line is a separator (|---|---|)
        const sepLine = lines[i + 1] || '';
        if (/^\|[-| :]+\|/.test(sepLine.trim())) {
          const tableLines = [line, sepLine];
          let j = i + 2;
          while (j < lines.length && /^\|.+\|/.test(lines[j].trim())) {
            tableLines.push(lines[j]);
            j++;
          }

          // Build HTML table
          const parseRow = (row) =>
            row.split('|').map(c => c.trim()).filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);

          const headers = parseRow(tableLines[0]).map(c => `<th>${c}</th>`).join('');
          const rows    = tableLines.slice(2).map(row =>
            `<tr>${parseRow(row).map(c => `<td>${c}</td>`).join('')}</tr>`
          ).join('');

          output.push(`<table class="md-table"><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table>`);
          i = j;
          continue;
        }
      }

      output.push(line);
      i++;
    }

    return output.join('\n');
  }

  let html = parseTables(text);

  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/_(.*?)_/g, '<em>$1</em>');
  html = html.replace(/`(.*?)`/g, '<code>$1</code>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  html = html.replace(/\n{3,}/g, '\n\n');
  html = html.replace(/\n\n/g, '<br>');
  html = html.replace(/\n/g, '<br>');

  const lines = html.split('<br>');
  let inList = false;
  let processedLines = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('- ') || line.startsWith('* ')) {
      if (!inList) { processedLines.push('<ul>'); inList = true; }
      processedLines.push('<li>' + line.substring(2) + '</li>');
    } else if (line.match(/^\d+\. /)) {
      if (!inList) { processedLines.push('<ol>'); inList = true; }
      processedLines.push('<li>' + line.replace(/^\d+\. /, '') + '</li>');
    } else {
      if (inList) { processedLines.push('</ul>'); inList = false; }
      if (line) processedLines.push(line);
    }
  }
  if (inList) processedLines.push('</ul>');
  html = processedLines.join('<br>');
  if (!html.includes('<ul>') && !html.includes('<h')) {
    html = '<p>' + html + '</p>';
  }
  html = html.replace(/<br><br>/g, '<br>');
  return html;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
function createChatbotOverlay() {

  // Conversation history — persisted in chrome.storage.session
  // Survives page navigation within the same browser session
  // Cleared automatically when browser closes
  const STORAGE_KEY      = 'tui_conversation_history';
  const OPEN_STATE_KEY   = 'tui_is_open';
  let conversationHistory = [];

  // --- Floating bubble ---
  const bubble = document.createElement('div');
  bubble.id = 'rag-chatbot-bubble';
  bubble.innerHTML = `
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  `;
  document.body.appendChild(bubble);

  // --- Overlay panel ---
  const overlay = document.createElement('div');
  overlay.id = 'rag-chatbot-overlay';
  overlay.classList.add('is-hidden');
  overlay.innerHTML = `
    <div id="rag-chatbot-header">
      <div id="rag-chatbot-header-title">
        <div id="rag-chatbot-avatar">S</div>
        <div>
          <div id="rag-chatbot-name">Spark Assistant</div>
          <div id="rag-chatbot-status">spark_products · NLP search active</div>
        </div>
      </div>
      <button id="rag-chatbot-minimise" title="Minimise">&#8722;</button>
    </div>
    <div id="rag-chatbot-messages"></div>
    <div id="rag-chatbot-input">
      <input type="text" placeholder="Ask about products...">
      <button id="rag-send-btn">Send</button>
    </div>
  `;
  document.body.appendChild(overlay);

  // --- DOM refs ---
  const messagesContainer = overlay.querySelector('#rag-chatbot-messages');
  const input             = overlay.querySelector('input');
  const sendButton        = overlay.querySelector('#rag-send-btn');
  const minimiseBtn       = overlay.querySelector('#rag-chatbot-minimise');

  // ---------------------------------------------------------------------------
  // Session storage helpers
  // ---------------------------------------------------------------------------
  function saveHistory() {
    chrome.storage.session.set({ [STORAGE_KEY]: conversationHistory });
  }

  function clearHistory() {
    conversationHistory = [];
    chrome.storage.session.remove(STORAGE_KEY);
  }

  function saveOpenState(isOpen) {
    chrome.storage.session.set({ [OPEN_STATE_KEY]: isOpen });
  }

  // ---------------------------------------------------------------------------
  // Restore conversation AND open state from session storage on page load
  // Replays stored messages into the DOM so the user sees their history
  // ---------------------------------------------------------------------------
  function restoreSession(onComplete) {
    chrome.storage.session.get([STORAGE_KEY, OPEN_STATE_KEY], (result) => {
      const stored  = result[STORAGE_KEY];
      const wasOpen = result[OPEN_STATE_KEY] === true;

      if (stored && stored.length > 0) {
        conversationHistory = stored;

        // Replay messages into the DOM
        messagesContainer.innerHTML = '';
        stored.forEach(turn => {
          if (turn.role === 'user') {
            addMessage('user', turn.content, false);
          } else {
            const cleaned = turn.content
              .replace(/<products>.*?<\/products>/gs, '')
              .replace(/<suggestions>.*?<\/suggestions>/gs, '')
              .replace(/<followup>.*?<\/followup>/gs, '')
              .replace(/<probe>.*?<\/probe>/gs, '')
              .trim();
            if (cleaned) addMessage('bot', cleaned, true);
          }
        });

        // Show "previous conversation" indicator
        const indicator = document.createElement('div');
        indicator.className = 'session-restored';
        indicator.textContent = '↑ Previous conversation';
        messagesContainer.appendChild(indicator);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

      } else {
        // No stored history — show welcome message
        addMessage('bot', "Kia ora! I'm Tui, your Spark assistant. Ask me about phones, plans, or accessories! 📱", false);
      }

      // Restore open state silently — don't trigger lookup or reset history
      if (wasOpen) {
        overlay.classList.remove('is-hidden');
        bubble.classList.add('is-open');
      }

      if (onComplete) onComplete();
    });
  }

  // --- Spark product page URL detection ---
  const SPARK_PRODUCT_PATTERN = /spark\.co\.nz\/online\/shop\/products\/([^/?#]+)/;
  const currentSlug = (window.location.href.match(SPARK_PRODUCT_PATTERN) || [])[1] || null;

  // --- Toggle open/close ---
  function openOverlay() {
    overlay.classList.remove('is-hidden');
    bubble.classList.add('is-open');
    input.focus();
    saveOpenState(true);

    // Proactive product greeting — only if no existing history
    if (currentSlug && conversationHistory.length === 0) {
      setTimeout(() => triggerProductLookup(), 2000);
    }
  }

  function closeOverlay() {
    // Just hide — don't reset history (Option B)
    overlay.classList.add('is-hidden');
    bubble.classList.remove('is-open');
    saveOpenState(false);
  }

  bubble.addEventListener('click', () => {
    overlay.classList.contains('is-hidden') ? openOverlay() : closeOverlay();
  });
  minimiseBtn.addEventListener('click', closeOverlay);

  // --- Proactive product page lookup ---
  async function triggerProductLookup() {
    if (conversationHistory.length > 0) return;

    showTypingIndicator();
    try {
      const response = await fetch('http://localhost:5000/lookup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: window.location.href })
      });

      const data = await response.json();
      removeTypingIndicator();

      if (data.matched) {
        messagesContainer.innerHTML = '';
        addMessage('bot', data.response, true);
        conversationHistory.push({ role: 'assistant', content: data.response });
        saveHistory();

        // Accessories carousel
        if (data.accessories && data.accessories.length > 0) {
          addSectionLabel('Compatible accessories');
          addProductCards(data.accessories);
        }

        // Device Protect nudge
        if (data.insurable) {
          addMessage('bot', '🛡️ **Device Protect** insurance is available for this device — covers accidental damage, theft, and more.', true);
        }

        if (data.suggestions && data.suggestions.length > 0) {
          addSuggestionsSection(data.suggestions);
        }
      } else {
        removeTypingIndicator();
      }
    } catch (error) {
      console.error('Lookup error:', error);
      removeTypingIndicator();
    }
  }

  // --- Welcome / session restore ---
  restoreSession(() => {
    // After session is restored, init is complete
    // Lookup will trigger on bubble open if needed
  });

  // ---------------------------------------------------------------------------
  // Send / receive
  // ---------------------------------------------------------------------------
  function handleSend() {
    const message = input.value.trim();
    if (!message) return;

    addMessage('user', message, false);
    input.value = '';
    showTypingIndicator();

    conversationHistory.push({ role: 'user', content: message });
    saveHistory();

    sendQuery(message);
  }

  sendButton.addEventListener('click', handleSend);
  input.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSend(); });

  async function sendQuery(message) {
    try {
      const response = await fetch('http://localhost:5000/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text:    message,
          website: window.location.hostname,
          history: conversationHistory.slice(0, -1)
        }),
      });

      if (!response.ok) throw new Error('Network error');
      const data = await response.json();

      removeTypingIndicator();

      if (data.response) {
        conversationHistory.push({ role: 'assistant', content: data.response });
        saveHistory();
      }

      processResponse(
        data.response,
        data.products      || [],
        data.sourceDetails || [],
        data.suggestions   || [],
        data.followup      || null,
        data.probe         || null,
        data.debugBar      || null
      );

    } catch (error) {
      console.error('Error:', error);
      removeTypingIndicator();
      // Remove the failed user turn from history and storage
      conversationHistory.pop();
      saveHistory();
      addMessage('bot', 'Sorry, something went wrong. Please try again.', false);
    }
  }

  function processResponse(response, products, sourceDetails, suggestions, followup, probe, debugBar) {
    // Mark the scroll anchor — we want to scroll to the START of this response
    // not the bottom, so the user sees Tui's answer first
    const scrollAnchor = document.createElement('div');
    scrollAnchor.className = 'scroll-anchor';
    messagesContainer.appendChild(scrollAnchor);

    if (response && response.trim()) {
      addMessage('bot', response, true);
    }
    if (products && products.length > 0) {
      addProductCards(products);
    }
    if (followup) {
      addFollowupQuestion(followup);
    }
    if (probe && probe.question) {
      addProbe(probe);
    }
    if (suggestions && suggestions.length > 0) {
      addSuggestionsSection(suggestions);
    }
    if (debugBar) {
      addDebugBar(debugBar);
    }

    // Scroll to the anchor — shows the start of this response
    scrollAnchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ---------------------------------------------------------------------------
  // Messages
  // ---------------------------------------------------------------------------
  function addMessage(sender, text, isMarkdown = false) {
    const el = document.createElement('div');
    el.className = `message ${sender}`;
    const bbl = document.createElement('div');
    bbl.className = 'message-bubble';
    if (isMarkdown) {
      try { bbl.innerHTML = parseMarkdown(text); }
      catch (e) { bbl.innerHTML = text.replace(/\n/g, '<br>'); }
    } else {
      bbl.innerHTML = text.replace(/\n/g, '<br>');
    }
    el.appendChild(bbl);
    messagesContainer.appendChild(el);
  }

  // ---------------------------------------------------------------------------
  // Product cards carousel
  // ---------------------------------------------------------------------------
  function addProductCards(products) {
    const container = document.createElement('div');
    container.className = 'products-container';
    const scroll = document.createElement('div');
    scroll.className = 'products-scroll';
    products.forEach((product, index) => {
      scroll.appendChild(createProductCard(product, index));
    });
    container.appendChild(scroll);
    const el = document.createElement('div');
    el.className = 'message bot';
    el.appendChild(container);
    messagesContainer.appendChild(el);
  }

  function createProductCard(product, index) {
    const card = document.createElement('div');
    card.className = 'product-card';
    card.style.animationDelay = `${index * 0.1}s`;

    const cleanName = sanitizeText(product.product_name || product.name || 'Unknown Product');
    const imageUrl  = product.primary_image_url || null;
    const brand     = sanitizeText(product.brand   || '');
    const storage   = sanitizeText(product.storage || '');
    const color     = sanitizeText(product.color   || '');

    const pricing  = product.pricing || {};
    const upfront  = pricing.upfront    != null ? pricing.upfront    : null;
    const monthly  = pricing.min_monthly != null ? pricing.min_monthly : null;
    const priceHtml = buildPriceHtml(upfront, monthly);

    const badgeParts = [brand, storage !== 'NA' ? storage : '', color].filter(Boolean);
    const badgeHtml  = badgeParts.length
      ? `<div class="product-category">${badgeParts.join(' · ')}</div>`
      : '';

    const features    = Array.isArray(product.features) ? product.features : [];
    const featureHtml = features.length
      ? `<div class="feature-tags">${
          features.slice(0, 3).map(f =>
            `<span class="feature-tag">${sanitizeText(f)}</span>`
          ).join('')
        }</div>`
      : '';

    const plans    = Array.isArray(product.payment_plans) ? product.payment_plans : [];
    const planRows = plans
      .sort((a, b) => b.term_months - a.term_months)
      .slice(0, 3)
      .map((p, i) => `
        <tr class="${i === 0 ? 'plan-row-active' : 'plan-row'}">
          <td>${p.term_months} months</td>
          <td class="plan-amount">$${formatPrice(p.monthly_amount)}/mo</td>
        </tr>
      `).join('');

    const upfrontRow = upfront
      ? `<tr class="plan-row">
           <td>Upfront</td>
           <td class="plan-amount">$${formatPrice(upfront)}</td>
         </tr>`
      : '';

    const planTableHtml = planRows
      ? `<div class="plan-table-wrap">
           <div class="plan-table-title">Payment options — all interest-free</div>
           <table class="plan-table">
             ${planRows}
             ${upfrontRow}
           </table>
         </div>`
      : '';

    card.innerHTML = `
      <div class="product-image">
        ${imageUrl
          ? `<img src="${imageUrl}" alt="${cleanName}">`
          : '<div class="placeholder">📦</div>'
        }
      </div>
      <div class="product-info">
        <div class="product-name">${cleanName}</div>
        ${badgeHtml}
        ${priceHtml}
        ${featureHtml}
        ${planTableHtml}
        <div class="card-actions">
          <button class="card-btn btn-details">View Details ↗</button>
        </div>
      </div>
    `;

    card.querySelector('.btn-details').addEventListener('click', () => {
      const url = product.url || product.source_url;
      if (url) window.open(url, '_blank');
    });

    const img = card.querySelector('img');
    if (img) {
      img.addEventListener('error', function() {
        this.parentElement.innerHTML = '<div class="placeholder">📦</div>';
      });
    }

    return card;
  }

  function buildPriceHtml(upfront, monthly) {
    if (upfront != null && upfront > 0) {
      const sub = monthly != null
        ? `<span class="price-monthly">or $${formatPrice(monthly)}/mo</span>`
        : '';
      return `<div class="product-price">$${formatPrice(upfront)} ${sub}</div>`;
    }
    if (monthly != null) {
      return `<div class="product-price">
                <span class="price-monthly-only">From $${formatPrice(monthly)}/mo</span>
              </div>`;
    }
    return '';
  }

  // ---------------------------------------------------------------------------
  // Section label — lightweight divider between product and accessories carousels
  // ---------------------------------------------------------------------------
  function addSectionLabel(text) {
    const el = document.createElement('div');
    el.className = 'message bot';
    el.innerHTML = `<div class="section-label">${text}</div>`;
    messagesContainer.appendChild(el);
  }

  // ---------------------------------------------------------------------------
  // Follow-up question — rendered as a distinct highlighted block
  // ---------------------------------------------------------------------------
  function addFollowupQuestion(question) {
    const el = document.createElement('div');
    el.className = 'message bot';
    el.innerHTML = `
      <div class="followup-question">
        <span class="followup-icon">💬</span>
        <span class="followup-text">${sanitizeText(question)}</span>
      </div>
    `;
    messagesContainer.appendChild(el);
  }

  // ---------------------------------------------------------------------------
  // Probe — cross-sell question with answer pills that submit as queries
  // ---------------------------------------------------------------------------
  function addProbe(probe) {
    const el = document.createElement('div');
    el.className = 'message bot';

    const pills = (probe.pills || []).map(pill => {
      // Map pill text to a meaningful query including category context
      const query = pill.toLowerCase().includes('not') || pill.toLowerCase().includes('no')
        ? pill
        : `${pill} — show me ${probe.category.replace('accessories_', '').replace('_', ' ')}`;
      return `<div class="probe-pill" data-query="${sanitizeText(query)}">${sanitizeText(pill)}</div>`;
    }).join('');

    el.innerHTML = `
      <div class="probe-block">
        <span class="probe-icon">💡</span>
        <div class="probe-content">
          <div class="probe-question">${sanitizeText(probe.question)}</div>
          <div class="probe-pills">${pills}</div>
        </div>
      </div>
    `;

    // Wire up pill clicks
    el.querySelectorAll('.probe-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        input.value = pill.dataset.query;
        handleSend();
      });
    });

    messagesContainer.appendChild(el);
  }

  // ---------------------------------------------------------------------------
  // Suggestions
  // ---------------------------------------------------------------------------
  function addSuggestionsSection(suggestions) {
    const container = document.createElement('div');
    container.className = 'suggestions-section';
    const title = document.createElement('div');
    title.className = 'suggestions-title';
    title.textContent = 'You might also ask:';
    const grid = document.createElement('div');
    grid.className = 'suggestions-grid';
    suggestions.forEach((s, i) => {
      const pill = document.createElement('div');
      pill.className = 'suggestion-pill';
      pill.textContent = s;
      pill.style.animationDelay = `${i * 0.1}s`;
      pill.addEventListener('click', () => { input.value = s; handleSend(); });
      grid.appendChild(pill);
    });
    container.appendChild(title);
    container.appendChild(grid);
    const el = document.createElement('div');
    el.className = 'message bot';
    el.appendChild(container);
    messagesContainer.appendChild(el);
  }

  // ---------------------------------------------------------------------------
  // Debug bar
  // ---------------------------------------------------------------------------
  function addDebugBar(debugBar) {
    const bar = document.createElement('div');
    bar.className = 'debug-bar';

    const historyInfo = debugBar.history_turns > 0
      ? ` · ${debugBar.history_turns} turns${debugBar.summarised ? ' (summarised)' : ''}`
      : '';

    bar.innerHTML = `
      <span class="debug-index">${sanitizeText(debugBar.index)} · ${debugBar.hits} hit${debugBar.hits !== 1 ? 's' : ''} · ${sanitizeText(debugBar.query_type)}${historyInfo}</span>
      <span class="debug-tags">
        <span class="debug-tag">semantic</span>
        <span class="debug-tag">in_stock</span>
        <span class="debug-tag">~${debugBar.latency_ms}ms</span>
      </span>
    `;
    const el = document.createElement('div');
    el.className = 'message bot';
    el.appendChild(bar);
    messagesContainer.appendChild(el);
  }

  // ---------------------------------------------------------------------------
  // Typing indicator
  // ---------------------------------------------------------------------------
  function showTypingIndicator() {
    const el = document.createElement('div');
    el.className = 'message bot typing-indicator';
    el.innerHTML = `
      <div class="message-bubble">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    `;
    messagesContainer.appendChild(el);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function removeTypingIndicator() {
    const el = messagesContainer.querySelector('.typing-indicator');
    if (el) el.remove();
  }

  // ---------------------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------------------
  function sanitizeText(text) {
    if (!text) return '';
    return text
      .replace(/&gt;/g, '').replace(/&lt;/g, '')
      .replace(/&amp;/g, '&').replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'").replace(/>/g, '')
      .replace(/</g, '').replace(/<[^>]*>/g, '')
      .trim();
  }

  function formatPrice(price) {
    if (price == null) return '';
    if (typeof price === 'number') return price.toFixed(2);
    return sanitizeText(price.toString());
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
chrome.storage.sync.get(['websites'], function(result) {
  const websites = result.websites || [];
  if (websites.some(website => window.location.hostname.includes(website))) {
    createChatbotOverlay();
  }
});
