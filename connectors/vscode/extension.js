const vscode = require("vscode");
const http = require("http");
const https = require("https");

function config() {
  const section = vscode.workspace.getConfiguration("breadcrumbs");
  return {
    apiBase: section.get("apiBase") || "http://127.0.0.1:8765",
    sessionId: section.get("sessionId") || ""
  };
}

function postJson(url, payload) {
  const body = Buffer.from(JSON.stringify(payload), "utf8");
  const client = url.startsWith("https:") ? https : http;
  const req = client.request(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Content-Length": body.length
    }
  });
  req.on("error", () => {});
  req.write(body);
  req.end();
}

function activeDocumentEvent(eventType) {
  const { apiBase, sessionId } = config();
  const editor = vscode.window.activeTextEditor;
  if (!sessionId || !editor) return;
  const document = editor.document;
  const selection = editor.selection;
  const selectedText = document.getText(selection);
  const text = selectedText || document.getText().slice(0, 12000);
  postJson(`${apiBase}/events/connector`, {
    sessionId,
    app: "vscode",
    eventType,
    source: "vscode-extension",
    documentId: document.uri.toString(),
    title: vscode.workspace.asRelativePath(document.uri),
    text,
    metadata: {
      languageId: document.languageId,
      lineCount: document.lineCount,
      hasSelection: Boolean(selectedText)
    }
  });
}

function debounce(fn, wait) {
  let timeout = null;
  return () => {
    clearTimeout(timeout);
    timeout = setTimeout(fn, wait);
  };
}

function activate(context) {
  const emitChange = debounce(() => activeDocumentEvent("document_change"), 750);
  context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(() => activeDocumentEvent("active_editor")));
  context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(emitChange));
  context.subscriptions.push(vscode.window.onDidChangeTextEditorSelection(debounce(() => activeDocumentEvent("selection"), 500)));
  activeDocumentEvent("startup");
}

function deactivate() {}

module.exports = { activate, deactivate };
