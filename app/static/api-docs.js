"use strict";
(async () => {
  const root = document.getElementById("api-reference");
  try {
    const response = await fetch("/openapi.json");
    if (!response.ok) throw new Error("Schema could not be loaded.");
    const schema = await response.json();
    root.replaceChildren();
    for (const [path, methods] of Object.entries(schema.paths)) {
      for (const [method, operation] of Object.entries(methods)) {
        const card = document.createElement("details");
        card.className = "card";
        const summary = document.createElement("summary");
        summary.textContent = method.toUpperCase() + " " + path + " — " + (operation.summary || "");
        const pre = document.createElement("pre");
        pre.className = "message-text";
        pre.textContent = JSON.stringify(operation, null, 2);
        card.append(summary, pre);
        root.append(card);
      }
    }
    const card = document.createElement("details");
    card.className = "card";
    const summary = document.createElement("summary");
    summary.textContent = "Request and response schemas";
    const pre = document.createElement("pre");
    pre.className = "message-text";
    pre.textContent = JSON.stringify(schema.components?.schemas || {}, null, 2);
    card.append(summary, pre); root.append(card);
  } catch (error) { root.textContent = error.message; }
})();
