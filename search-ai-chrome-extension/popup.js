document.addEventListener('DOMContentLoaded', function() {
  const addButton = document.getElementById('addWebsite');
  const newWebsiteInput = document.getElementById('newWebsite');
  const websiteList = document.getElementById('websiteList');

  function updateWebsiteList() {
    chrome.storage.sync.get(['websites'], function(result) {
      const websites = result.websites || [];
      websiteList.innerHTML = '';
      websites.forEach(function(website) {
        const div = document.createElement('div');
        div.textContent = website;
        const removeButton = document.createElement('button');
        removeButton.textContent = 'Remove';
        removeButton.onclick = function() {
          const updatedWebsites = websites.filter(w => w !== website);
          chrome.storage.sync.set({websites: updatedWebsites}, updateWebsiteList);
        };
        div.appendChild(removeButton);
        websiteList.appendChild(div);
      });
    });
  }

  addButton.addEventListener('click', function() {
    const newWebsite = newWebsiteInput.value.trim();
    if (newWebsite) {
      chrome.storage.sync.get(['websites'], function(result) {
        const websites = result.websites || [];
        if (!websites.includes(newWebsite)) {
          websites.push(newWebsite);
          chrome.storage.sync.set({websites: websites}, function() {
            newWebsiteInput.value = '';
            updateWebsiteList();
          });
        }
      });
    }
  });

  updateWebsiteList();
});
