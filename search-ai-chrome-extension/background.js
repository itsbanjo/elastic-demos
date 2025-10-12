chrome.runtime.onInstalled.addListener(function() {
  chrome.storage.sync.set({websites: ['spark.co.nz']}, function() {
    console.log("Default website set.");
  });
});
