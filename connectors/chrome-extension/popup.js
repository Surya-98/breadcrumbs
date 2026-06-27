const input = document.getElementById("session");
const status = document.getElementById("status");
const save = document.getElementById("save");

chrome.storage.local.get(["breadcrumbsSessionId"], (result) => {
  input.value = result.breadcrumbsSessionId || "";
  status.textContent = input.value ? "Connected." : "Waiting for a Breadcrumbs session.";
});

save.addEventListener("click", () => {
  const value = input.value.trim();
  chrome.storage.local.set({ breadcrumbsSessionId: value }, () => {
    status.textContent = value ? "Connected." : "Disconnected.";
  });
});
