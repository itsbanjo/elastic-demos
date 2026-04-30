// overlay.js - Updated for spark_products index schema

// Simple markdown parser to avoid external library issues
function parseMarkdown(text) {
  if (!text) return '';
  
  let html = text;
  
  // Headers
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
  
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');
  
  // Italic
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/_(.*?)_/g, '<em>$1</em>');
  
  // Code inline
  html = html.replace(/`(.*?)`/g, '<code>$1</code>');
  
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  
  // Line breaks
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');
  
  // Lists
  const lines = html.split('<br>');
  let inList = false;
  let processedLines = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    if (line.startsWith('- ') || line.startsWith('* ')) {
      if (!inList) {
        processedLines.push('<ul>');
        inList = true;
      }
      processedLines.push('<li>' + line.substring(2) + '</li>');
    } else if (line.match(/^\d+\. /)) {
      if (!inList) {
        processedLines.push('<ol>');
        inList = true;
      }
      processedLines.push('<li>' + line.replace(/^\d+\. /, '') + '</li>');
    } else {
      if (inList) {
        processedLines.push('</ul>');
        inList = false;
      }
      if (line) {
        processedLines.push(line);
      }
    }
  }
  
  if (inList) {
    processedLines.push('</ul>');
  }
  
  html = processedLines.join('<br>');
  
  // Wrap in paragraphs if not already wrapped
  if (!html.includes('<p>') && !html.includes('<ul>') && !html.includes('<h')) {
    html = '<p>' + html + '</p>';
  }
  
  // Clean up extra breaks
  html = html.replace(/<br><br>/g, '<br>');
  html = html.replace(/<p><br>/g, '<p>');
  html = html.replace(/<br><\/p>/g, '</p>');
  
  return html;
}

function createChatbotOverlay() {
  // Create overlay HTML structure
  const overlay = document.createElement('div');
  overlay.id = 'rag-chatbot-overlay';
  overlay.innerHTML = `
    <div id="rag-chatbot-header">✨ Spark Elastic Assistant</div>
    <div id="rag-chatbot-messages"></div>
    <div id="rag-chatbot-input">
      <input type="text" placeholder="Ask about products...">
      <button>Send</button>
    </div>
  `;
  document.body.appendChild(overlay);

  // Get DOM elements
  const messagesContainer = overlay.querySelector('#rag-chatbot-messages');
  const input = overlay.querySelector('input');
  const sendButton = overlay.querySelector('button');

  // Store reference data for clickable functionality
  let currentReferenceSources = [];

  // Add welcome message
  addMessage('bot', 'Hi! I\'m your Spark product assistant. Ask me about phones, plans, or accessories! 📱', false);

  // Event handlers
  function handleSend() {
    const message = input.value.trim();
    if (message) {
      addMessage('user', message, false);
      input.value = '';
      showTypingIndicator();
      sendQuery(message);
    }
  }

  sendButton.addEventListener('click', handleSend);
  input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      handleSend();
    }
  });

  // Send query to backend
  async function sendQuery(message) {
    try {
      const response = await fetch('http://localhost:5000/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          text: message,
          website: window.location.hostname
        }),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();
      
      removeTypingIndicator();
      processResponse(data.response, data.products || [], data.sources || 0, data.sourceDetails || [], data.suggestions || []);
      
    } catch (error) {
      console.error('Error:', error);
      removeTypingIndicator();
      addMessage('bot', 'Sorry, I encountered an error while processing your request. Please try again.', false);
    }
  }

  // Process the server response
  function processResponse(response, products = [], sourcesCount = 0, sourceDetails = [], suggestions = []) {
    console.log('Processing response:', { response, products, sourcesCount, sourceDetails, suggestions });
    
    // Store source details for clickable references
    currentReferenceSources = sourceDetails;
    
    // Add the markdown-rendered conversational response
    if (response && response.trim()) {
      addMessage('bot', response, true);
    }
    
    // Add product cards if available
    if (products && products.length > 0) {
      addProductCards(products);
    }
    
    // Add smart suggestions section
    if (suggestions && suggestions.length > 0) {
      addSuggestionsSection(suggestions);
    }
  }

  // Extract citation references from response text with actual source data
  // (kept for future use if references section is re-enabled)
  function extractReferences(text, sourcesCount, sourceDetails = []) {
    const references = [];
    if (!text) return references;
    
    const citationMatches = text.match(/\[(\d+)\]/g);
    
    if (citationMatches) {
      const citationNumbers = [...new Set(citationMatches.map(match => 
        parseInt(match.replace(/[\[\]]/g, ''))
      ))].sort((a, b) => a - b);
      
      citationNumbers.forEach(num => {
        const sourceDetail = sourceDetails.find(s => s.index === num);
        
        references.push({
          number: num,
          source: sourceDetail ? sourceDetail.title || sourceDetail.name || `Product Information - Source ${num}` : `Spark Product Information - Source ${num}`,
          url: sourceDetail ? sourceDetail.url || '#' : '#',
          description: sourceDetail ? sourceDetail.description : null
        });
      });
    }
    
    return references;
  }

  // Add message with markdown support
  function addMessage(sender, text, isMarkdown = false) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${sender}`;
    
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    if (isMarkdown) {
      try {
        const htmlContent = parseMarkdown(text);
        bubble.innerHTML = htmlContent;
      } catch (error) {
        console.warn('Markdown parsing failed:', error);
        bubble.innerHTML = text.replace(/\n/g, '<br>');
      }
    } else {
      bubble.innerHTML = text.replace(/\n/g, '<br>');
    }
    
    messageElement.appendChild(bubble);
    messagesContainer.appendChild(messageElement);
  }

  // Add product cards carousel — structure unchanged, card internals updated
  function addProductCards(products) {
    const productsContainer = document.createElement('div');
    productsContainer.className = 'products-container';
    
    const scrollContainer = document.createElement('div');
    scrollContainer.className = 'products-scroll';
    
    products.forEach((product, index) => {
      const card = createProductCard(product, index);
      scrollContainer.appendChild(card);
    });
    
    productsContainer.appendChild(scrollContainer);
    
    const messageElement = document.createElement('div');
    messageElement.className = 'message bot';
    messageElement.appendChild(productsContainer);
    
    messagesContainer.appendChild(messageElement);
  }

  // ---------------------------------------------------------------------------
  // createProductCard — updated for spark_products schema
  //
  // Field mapping (old → new):
  //   product.name        → product.product_name
  //   product.image       → product.primary_image_url  (already a full CDN URL)
  //   product.price       → product.pricing.upfront / product.pricing.min_monthly
  //   product.color       → product.colors[].color_name (array, drives swatches)
  //   extractCategory()   → product.brand  (direct field, no description sniffing)
  //   getDomainForImages  → removed (URL is already absolute)
  //
  // New: colour swatch row — clicking a swatch swaps the card image to
  //      that variant's gallery_urls[0] (or primary_image_url as fallback).
  // ---------------------------------------------------------------------------
  function createProductCard(product, index) {
    const card = document.createElement('div');
    card.className = 'product-card';
    card.style.animationDelay = `${index * 0.1}s`;

    // --- Field resolution ---
    const cleanName   = sanitizeText(product.product_name || product.name || 'Unknown Product');
    const imageUrl    = product.primary_image_url || null;
    const brand       = sanitizeText(product.brand || '');
    const storage     = sanitizeText(product.storage || '');
    const colors      = Array.isArray(product.colors) ? product.colors : [];

    // Prefer upfront price; fall back to monthly if upfront is absent
    const pricing     = product.pricing || {};
    const upfront     = pricing.upfront != null ? pricing.upfront : null;
    const monthly     = pricing.min_monthly != null ? pricing.min_monthly : null;
    const priceHtml   = buildPriceHtml(upfront, monthly);

    // Badge line: brand and/or storage
    const badgeParts  = [brand, storage].filter(Boolean);
    const badgeHtml   = badgeParts.length
      ? `<div class="product-category">${badgeParts.join(' · ')}</div>`
      : '';

    // Build swatch HTML — rendered into card, wired up after innerHTML set
    const swatchHtml  = colors.length > 1
      ? `<div class="color-swatches">${
          colors.slice(0, 6).map((c, i) =>
            `<div class="color-swatch${i === 0 ? ' swatch-active' : ''}"
               style="background:${sanitizeText(c.color_hex || '#ccc')}"
               title="${sanitizeText(c.color_name || '')}"
               data-swatch-index="${i}"></div>`
          ).join('')
        }</div>`
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
        ${swatchHtml}
        <button class="product-cta">View Details</button>
      </div>
    `;

    // --- Wire up swatch clicks ---
    // Clicking a swatch swaps the <img> src to that variant's first gallery image,
    // or falls back to primary_image_url if gallery_urls is empty.
    if (colors.length > 1) {
      const imgEl    = card.querySelector('img');
      const swatches = card.querySelectorAll('.color-swatch');

      swatches.forEach((swatch, i) => {
        swatch.addEventListener('click', () => {
          // Update active state
          swatches.forEach(s => s.classList.remove('swatch-active'));
          swatch.classList.add('swatch-active');

          // Swap image if we have an img element to swap
          if (imgEl && colors[i]) {
            const variant    = colors[i];
            const variantImg = (variant.gallery_urls && variant.gallery_urls[0])
              || variant.primary_image_url
              || imageUrl;

            if (variantImg) {
              imgEl.src = variantImg;
            }
          }
        });
      });
    }

    // --- View Details CTA ---
    const ctaButton = card.querySelector('.product-cta');
    ctaButton.addEventListener('click', () => {
      if (product.url || product.source_url) {
        window.open(product.url || product.source_url, '_blank');
      }
    });

    // --- Image load error fallback ---
    const img = card.querySelector('img');
    if (img) {
      img.addEventListener('error', function() {
        // If a color_hex is available for the active variant, show a colour circle
        // instead of a generic box icon, so the swatch context isn't lost
        const activeColor = colors[0];
        if (activeColor && activeColor.color_hex) {
          this.parentElement.innerHTML = `
            <div class="placeholder color-fallback"
                 style="background:${sanitizeText(activeColor.color_hex)}">
            </div>`;
        } else {
          this.parentElement.innerHTML = '<div class="placeholder">📦</div>';
        }
      });
    }
    
    return card;
  }

  // Build price display HTML from upfront + monthly fields
  function buildPriceHtml(upfront, monthly) {
    if (upfront != null && upfront > 0) {
      const monthlyLine = monthly != null
        ? `<span class="price-monthly">or $${formatPrice(monthly)}/mo</span>`
        : '';
      return `<div class="product-price">$${formatPrice(upfront)} ${monthlyLine}</div>`;
    }
    if (monthly != null) {
      return `<div class="product-price"><span class="price-monthly-only">From $${formatPrice(monthly)}/mo</span></div>`;
    }
    return '';
  }

  // Add clickable references section (kept, currently commented out in processResponse)
  function addReferencesSection(references) {
    const referencesContainer = document.createElement('div');
    referencesContainer.className = 'references-section';
    
    const title = document.createElement('div');
    title.className = 'references-title';
    title.textContent = 'References';
    
    const referencesList = document.createElement('div');
    referencesList.className = 'references-list';
    
    references.forEach(ref => {
      const referenceItem = document.createElement('div');
      referenceItem.className = 'reference-item';
      
      const numberBadge = document.createElement('div');
      numberBadge.className = 'reference-number';
      numberBadge.textContent = ref.number;
      
      const sourceText = document.createElement('div');
      sourceText.className = 'reference-source';
      sourceText.textContent = ref.source;
      sourceText.title = ref.description || ref.source;
      
      if (ref.url && ref.url !== '#') {
        referenceItem.classList.add('clickable');
        referenceItem.addEventListener('click', () => {
          window.open(ref.url, '_blank');
        });
        referenceItem.style.cursor = 'pointer';
        referenceItem.addEventListener('mouseenter', () => {
          referenceItem.style.backgroundColor = 'rgba(102, 126, 234, 0.1)';
        });
        referenceItem.addEventListener('mouseleave', () => {
          referenceItem.style.backgroundColor = 'transparent';
        });
      }
      
      referenceItem.appendChild(numberBadge);
      referenceItem.appendChild(sourceText);
      referencesList.appendChild(referenceItem);
    });
    
    referencesContainer.appendChild(title);
    referencesContainer.appendChild(referencesList);
    
    const messageElement = document.createElement('div');
    messageElement.className = 'message bot';
    messageElement.appendChild(referencesContainer);
    
    messagesContainer.appendChild(messageElement);
  }

  // Add smart suggestions section
  function addSuggestionsSection(suggestions) {
    const suggestionsContainer = document.createElement('div');
    suggestionsContainer.className = 'suggestions-section';
    
    const title = document.createElement('div');
    title.className = 'suggestions-title';
    title.textContent = 'You might also ask:';
    
    const suggestionsGrid = document.createElement('div');
    suggestionsGrid.className = 'suggestions-grid';
    
    suggestions.forEach((suggestion, index) => {
      const suggestionPill = document.createElement('div');
      suggestionPill.className = 'suggestion-pill';
      suggestionPill.textContent = suggestion;
      suggestionPill.style.animationDelay = `${index * 0.1}s`;
      
      suggestionPill.addEventListener('click', () => {
        input.value = suggestion;
        handleSend();
      });
      
      suggestionsGrid.appendChild(suggestionPill);
    });
    
    suggestionsContainer.appendChild(title);
    suggestionsContainer.appendChild(suggestionsGrid);
    
    const messageElement = document.createElement('div');
    messageElement.className = 'message bot';
    messageElement.appendChild(suggestionsContainer);
    
    messagesContainer.appendChild(messageElement);
  }

  // Typing indicator
  function showTypingIndicator() {
    const typingElement = document.createElement('div');
    typingElement.className = 'message bot typing-indicator';
    typingElement.innerHTML = `
      <div class="message-bubble">
        <div class="typing-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    `;
    
    messagesContainer.appendChild(typingElement);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function removeTypingIndicator() {
    const typingIndicator = messagesContainer.querySelector('.typing-indicator');
    if (typingIndicator) {
      typingIndicator.remove();
    }
  }

  // Utility functions
  function sanitizeText(text) {
    if (!text) return '';
    return text
      .replace(/&gt;/g, '')
      .replace(/&lt;/g, '')
      .replace(/&amp;/g, '&')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/>/g, '')
      .replace(/</g, '')
      .replace(/<[^>]*>/g, '')
      .trim();
  }

  function formatPrice(price) {
    if (price == null) return '';
    if (typeof price === 'number') return price.toFixed(2);
    return sanitizeText(price.toString());
  }

  // getDomainForImages() removed — primary_image_url is already a full CDN URL.
  // extractCategory()  removed — product.brand is now a direct field.
}

// Initialize overlay based on website configuration
chrome.storage.sync.get(['websites'], function(result) {
  const websites = result.websites || [];
  if (websites.some(website => window.location.hostname.includes(website))) {
    createChatbotOverlay();
  }
});
