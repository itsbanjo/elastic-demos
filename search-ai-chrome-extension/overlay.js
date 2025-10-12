// overlay.js - Enhanced with smart query suggestions

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
  addMessage('bot', 'Hi! I\'m your product assistant. Ask me anything about our products and I\'ll help you find what you\'re looking for! 🛍️', false);

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
      addMessage('bot', response, true); // true = render as markdown
    }
    
    // Add product cards if available
    if (products && products.length > 0) {
      addProductCards(products);
    }
    
    // Add references section
   // const references = extractReferences(response, sourcesCount, sourceDetails);
   // if (references.length > 0) {
   //   addReferencesSection(references);
   // }
    
    // Add smart suggestions section - NEW!
    if (suggestions && suggestions.length > 0) {
      addSuggestionsSection(suggestions);
    }
  }

  // Extract citation references from response text with actual source data
  function extractReferences(text, sourcesCount, sourceDetails = []) {
    const references = [];
    if (!text) return references;
    
    const citationMatches = text.match(/\[(\d+)\]/g);
    
    if (citationMatches) {
      const citationNumbers = [...new Set(citationMatches.map(match => 
        parseInt(match.replace(/[\[\]]/g, ''))
      ))].sort((a, b) => a - b);
      
      citationNumbers.forEach(num => {
        // Try to find actual source details from the server response
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
    // messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Add product cards carousel
  function addProductCards(products) {
    const productsContainer = document.createElement('div');
    productsContainer.className = 'products-container';
    
    const scrollContainer = document.createElement('div');
    scrollContainer.className = 'products-scroll';
    
    // Add all product cards to scroll container
    products.forEach((product, index) => {
      const card = createProductCard(product, index);
      scrollContainer.appendChild(card);
    });
    
    // Add scroll container to products container
    productsContainer.appendChild(scrollContainer);
    
    // Now create the message element and add the complete products container
    const messageElement = document.createElement('div');
    messageElement.className = 'message bot';
    messageElement.appendChild(productsContainer);
    
    // Add to messages container
    messagesContainer.appendChild(messageElement);
    // messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Create individual product card
  function createProductCard(product, index) {
    const card = document.createElement('div');
    card.className = 'product-card';
    card.style.animationDelay = `${index * 0.1}s`;
    
    const domain = getDomainForImages();
    const imageUrl = product.image ? `${domain}${product.image}` : null;
    const formattedPrice = formatPrice(product.price);
    const cleanName = sanitizeText(product.name);
    const category = extractCategory(product);
    
    card.innerHTML = `
      <div class="product-image">
        ${imageUrl ? 
          `<img src="${imageUrl}" alt="${cleanName}">` :
          '<div class="placeholder">📦</div>'
        }
      </div>
      <div class="product-info">
        <div class="product-name">${cleanName}</div>
        ${category ? `<div class="product-category">${category}</div>` : ''}
        ${formattedPrice ? `<div class="product-price">$ ${formattedPrice}</div>` : ''}
        <button class="product-cta">View Details</button>
      </div>
    `;
    
    // Add click handler for CTA button
    const ctaButton = card.querySelector('.product-cta');
    ctaButton.addEventListener('click', () => {
      if (product.url) {
        window.open(product.url, '_blank');
      }
    });
    
    // Handle image error
    const img = card.querySelector('img');
    if (img) {
      img.addEventListener('error', function() {
        this.parentElement.innerHTML = '<div class="placeholder">📦</div>';
      });
    }
    
    return card;
  }

  // Add clickable references section
  function addReferencesSection(references) {
    const referencesContainer = document.createElement('div');
    referencesContainer.className = 'references-section';
    
    // Create title
    const title = document.createElement('div');
    title.className = 'references-title';
    title.textContent = 'References';
    
    // Create list container
    const referencesList = document.createElement('div');
    referencesList.className = 'references-list';
    
    // Add each reference as clickable item
    references.forEach(ref => {
      const referenceItem = document.createElement('div');
      referenceItem.className = 'reference-item';
      
      // Create number badge
      const numberBadge = document.createElement('div');
      numberBadge.className = 'reference-number';
      numberBadge.textContent = ref.number;
      
      // Create source text (clickable if URL exists)
      const sourceText = document.createElement('div');
      sourceText.className = 'reference-source';
      sourceText.textContent = ref.source;
      sourceText.title = ref.description || ref.source; // Tooltip
      
      // Make it clickable if we have a valid URL
      if (ref.url && ref.url !== '#') {
        referenceItem.classList.add('clickable');
        referenceItem.addEventListener('click', () => {
          window.open(ref.url, '_blank');
        });
        
        // Add click cursor styling
        referenceItem.style.cursor = 'pointer';
        
        // Add hover effect
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
    // messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // NEW: Add smart suggestions section
  function addSuggestionsSection(suggestions) {
    const suggestionsContainer = document.createElement('div');
    suggestionsContainer.className = 'suggestions-section';
    
    // Create title
    const title = document.createElement('div');
    title.className = 'suggestions-title';
    title.textContent = 'You might also ask:';
    
    // Create suggestions container
    const suggestionsGrid = document.createElement('div');
    suggestionsGrid.className = 'suggestions-grid';
    
    // Add each suggestion as clickable pill
    suggestions.forEach((suggestion, index) => {
      const suggestionPill = document.createElement('div');
      suggestionPill.className = 'suggestion-pill';
      suggestionPill.textContent = suggestion;
      suggestionPill.style.animationDelay = `${index * 0.1}s`;
      
      // Add click handler
      suggestionPill.addEventListener('click', () => {
        // Simulate user typing and sending the suggestion
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
    // messagesContainer.scrollTop = messagesContainer.scrollHeight;
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
    if (!price) return '';
    if (typeof price === 'number') return `${price.toFixed(2)}`;
    return sanitizeText(price.toString());
  }

  function extractCategory(product) {
    if (product.description) {
      const desc = product.description.toLowerCase();
      if (desc.includes('women') || desc.includes('ladies')) return 'for women';
      if (desc.includes('men') || desc.includes('mens')) return 'for men';
      if (desc.includes('kids') || desc.includes('children')) return 'for kids';
    }
    return null;
  }

  function getDomainForImages() {
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;
    
    if (hostname.includes('localhost')) {
      return `${protocol}//localhost:3000`;
    } else if (hostname.includes('staging')) {
      return `${protocol}//staging.spark.co.nz`;
    } else {
      return `${protocol}//spark.co.nz`;
    }
  }
}

// Initialize overlay based on website configuration
chrome.storage.sync.get(['websites'], function(result) {
  const websites = result.websites || [];
  if (websites.some(website => window.location.hostname.includes(website))) {
    createChatbotOverlay();
  }
});
