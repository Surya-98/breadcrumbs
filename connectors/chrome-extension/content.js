const API_BASE = "http://127.0.0.1:8765";
const INPUT_SELECTOR = [
  "div[contenteditable='true'][role='textbox']",
  "div[contenteditable='true']",
  "textarea",
  "input[type='text']"
].join(",");

let sessionId = null;
let lastSent = new Map();

function appName() {
  if (location.hostname.includes("mail.google.com")) return "gmail";
  if (location.hostname.includes("slack.com")) return "slack";
  return "browser";
}

function readText(element) {
  if (!element) return "";
  if ("value" in element) return element.value || "";
  return element.innerText || element.textContent || "";
}

function documentIdFor(element) {
  const index = Array.from(document.querySelectorAll(INPUT_SELECTOR)).indexOf(element);
  const base = `${appName()}:${location.pathname}:${Math.max(index, 0)}`;
  if (appName() === "gmail") {
    const subject = document.querySelector("input[name='subjectbox']");
    return `${base}:${(subject && subject.value) || "draft"}`;
  }
  return base;
}

function currentTitle() {
  if (appName() === "gmail") {
    const subject = document.querySelector("input[name='subjectbox']");
    return (subject && subject.value) || document.title;
  }
  return document.title;
}

async function postEvent(payload) {
  try {
    await fetch(`${API_BASE}/events/connector`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (_error) {
    // The local app may not be running yet.
  }
}

function emitForElement(element, eventType = "text_change") {
  if (!sessionId || !element) return;
  const text = readText(element).trim();
  if (!text) return;
  const documentId = documentIdFor(element);
  const last = lastSent.get(documentId);
  if (last === text) return;
  lastSent.set(documentId, text);
  postEvent({
    sessionId,
    app: appName(),
    eventType,
    source: "chrome-extension",
    documentId,
    title: currentTitle(),
    text,
    metadata: {
      url: location.origin + location.pathname,
      hostname: location.hostname
    }
  });
}

function debounce(fn, wait) {
  let timeout = null;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), wait);
  };
}

const debouncedEmit = debounce((event) => {
  const target = event.target && event.target.closest ? event.target.closest(INPUT_SELECTOR) : null;
  emitForElement(target || document.activeElement);
}, 500);

function setElementText(element, text) {
  if (!element) return;
  element.focus();
  if ("value" in element) {
    element.value = text;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }
  element.textContent = text;
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
}

async function pollActions() {
  if (!sessionId) return;
  try {
    const response = await fetch(`${API_BASE}/actions/pending?app=${encodeURIComponent(appName())}`);
    const data = await response.json();
    for (const action of data.actions || []) {
      const elements = Array.from(document.querySelectorAll(INPUT_SELECTOR));
      const target = elements.find((element) => documentIdFor(element) === action.target_id);
      if (!target) continue;
      setElementText(target, action.payload.after_text || "");
      await fetch(`${API_BASE}/actions/${action.id}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "completed" })
      });
    }
  } catch (_error) {
    // Keep polling quietly; this connector should never interrupt the user.
  }
}

chrome.storage.local.get(["breadcrumbsSessionId"], (result) => {
  sessionId = result.breadcrumbsSessionId || null;
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.breadcrumbsSessionId) {
    sessionId = changes.breadcrumbsSessionId.newValue || null;
  }
});

document.addEventListener("input", debouncedEmit, true);
document.addEventListener("focusin", (event) => {
  const target = event.target && event.target.closest ? event.target.closest(INPUT_SELECTOR) : null;
  emitForElement(target, "focus");
}, true);

setInterval(pollActions, 2000);
