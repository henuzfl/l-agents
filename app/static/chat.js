"use strict";

let STORAGE_KEY = "agent-desk-conversations";
const evidenceImageCache = new Map();
const evidenceBlobUrls = new Set();
const state = {
  conversations: [],
  activeId: "",
  sending: false,
  activeRequest: null,
  clock: null,
};

const elements = {
  conversation: document.querySelector("#conversation"),
  history: document.querySelector("#history"),
  input: document.querySelector("#messageInput"),
  send: document.querySelector("#sendButton"),
  error: document.querySelector("#errorBanner"),
  errorText: document.querySelector("#errorText"),
  sidebar: document.querySelector("#sidebar"),
  scrim: document.querySelector("#scrim"),
};

function id() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();

  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}
function activeConversation() { return state.conversations.find((item) => item.id === state.activeId); }
function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.conversations)); }
function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
}

function escapeAttribute(value) {
  return escapeHtml(String(value ?? "")).replace(/"/g, "&quot;");
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function parseMarkdownTableRow(line) {
  let value = String(line || "").trim();
  if (!value.includes("|")) return null;
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);

  const cells = [];
  let cell = "";
  let inCode = false;
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (character === "\\" && value[index + 1] === "|") {
      cell += "|";
      index += 1;
      continue;
    }
    if (character === "`") inCode = !inCode;
    if (character === "|" && !inCode) {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
  }
  cells.push(cell.trim());
  return cells.length >= 2 ? cells : null;
}

function isMarkdownTableSeparator(cells) {
  return Array.isArray(cells)
    && cells.length >= 2
    && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function markdownTableAlignment(separator) {
  const value = separator.trim();
  if (value.startsWith(":") && value.endsWith(":")) return "center";
  if (value.endsWith(":")) return "right";
  return "left";
}

function renderMarkdownTable(headers, separators, rows) {
  const alignments = headers.map((_, index) => markdownTableAlignment(separators[index] || "---"));
  const headerHtml = headers.map((cell, index) => (
    `<th class="align-${alignments[index]}" scope="col">${renderInlineMarkdown(cell)}</th>`
  )).join("");
  const bodyHtml = rows.map((row) => `<tr>${headers.map((_, index) => (
    `<td class="align-${alignments[index]}">${renderInlineMarkdown(row[index] || "")}</td>`
  )).join("")}</tr>`).join("");
  return `<div class="markdown-table-wrap"><table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`;
}

function renderMarkdown(value) {
  const lines = value.replace(/\r\n?/g, "\n").split("\n");
  const output = [];
  let paragraph = [];
  let listType = "";
  let code = [];
  let inCodeBlock = false;

  const closeParagraph = () => {
    if (paragraph.length) output.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (listType) output.push(`</${listType}>`);
    listType = "";
  };
  const openList = (type) => {
    closeParagraph();
    if (listType !== type) {
      closeList();
      output.push(`<${type}>`);
      listType = type;
    }
  };

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const line = lines[lineIndex];
    if (/^\s*```/.test(line)) {
      closeParagraph();
      closeList();
      if (inCodeBlock) {
        output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        code = [];
      }
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) { code.push(line); continue; }
    const tableHeaders = parseMarkdownTableRow(line);
    const tableSeparators = parseMarkdownTableRow(lines[lineIndex + 1]);
    if (
      tableHeaders
      && tableSeparators
      && tableHeaders.length === tableSeparators.length
      && isMarkdownTableSeparator(tableSeparators)
    ) {
      closeParagraph();
      closeList();
      const rows = [];
      let rowIndex = lineIndex + 2;
      while (rowIndex < lines.length) {
        const row = parseMarkdownTableRow(lines[rowIndex]);
        if (!row) break;
        rows.push(row);
        rowIndex += 1;
      }
      output.push(renderMarkdownTable(tableHeaders, tableSeparators, rows));
      lineIndex = rowIndex - 1;
      continue;
    }
    const heading = line.match(/^\s*(#{1,4})\s+(.+)$/);
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const quote = line.match(/^\s*>\s?(.+)$/);
    if (!line.trim()) { closeParagraph(); closeList(); continue; }
    if (/^\s*---+\s*$/.test(line)) { closeParagraph(); closeList(); output.push("<hr>"); continue; }
    if (heading) {
      closeParagraph(); closeList();
      const level = Math.min(heading[1].length + 1, 5);
      output.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    if (unordered) { openList("ul"); output.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`); continue; }
    if (ordered) { openList("ol"); output.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`); continue; }
    if (quote) {
      closeParagraph(); closeList();
      output.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }
    closeList();
    paragraph.push(line.trim());
  }
  closeParagraph();
  closeList();
  if (inCodeBlock && code.length) output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
  return output.join("");
}

function formatDuration(milliseconds) {
  const seconds = Math.max(0, milliseconds || 0) / 1000;
  return seconds < 10 ? `${seconds.toFixed(1)} 秒` : `${Math.round(seconds)} 秒`;
}

function traceHtml(message) {
  if (!message.traceStatus && !message.trace?.length) return "";
  const running = message.traceStatus === "running";
  const interrupted = message.traceStatus === "interrupted";
  const duration = running
    ? Date.now() - (message.startedAt || Date.now())
    : message.durationMs || 0;
  const title = running ? "正在思考" : interrupted ? "执行中断" : "已思考";
  const count = message.trace?.length || 0;
  const open = message.traceOpen === true || running ? " open" : "";
  const steps = (message.trace || []).map((step) => {
    const meta = [step.agent, step.tool].filter(Boolean).map(escapeHtml).join(" · ");
    return `<li class="trace-step ${escapeHtml(step.status || "completed")}">
      <div><span>${escapeHtml(step.label || "执行步骤")}</span><time>+${formatDuration(step.elapsed_ms)}</time></div>
      ${meta ? `<code>${meta}</code>` : ""}
    </li>`;
  }).join("");
  const pulse = running ? '<i class="trace-pulse" aria-hidden="true"></i>' : "";
  return `<details class="trace-panel ${message.traceStatus}" data-trace-id="${message.id}"${open}>
    <summary>${pulse}<span>${title} ${formatDuration(duration)}</span><small>${count} 步</small><b aria-hidden="true">⌄</b></summary>
    <ol class="trace-steps">${steps}</ol>
  </details>`;
}

function createConversation() {
  cancelActiveRequest();
  const conversation = { id: id(), title: "新对话", messages: [] };
  state.conversations.unshift(conversation);
  state.activeId = conversation.id;
  closeSidebar();
  save();
  render();
  elements.input.focus();
}

function selectConversation(conversationId) {
  if (conversationId !== state.activeId) cancelActiveRequest();
  state.activeId = conversationId;
  closeSidebar();
  clearError();
  render();
}

function deleteConversation(conversationId) {
  if (conversationId === state.activeRequest?.conversationId) cancelActiveRequest();
  state.conversations = state.conversations.filter((item) => item.id !== conversationId);
  if (state.activeId === conversationId) state.activeId = state.conversations[0]?.id || "";
  save();
  if (!state.activeId) createConversation(); else render();
}

function renderHistory() {
  elements.history.innerHTML = state.conversations.map((item) => `
    <div class="history-row ${item.id === state.activeId ? "active" : ""}">
      <button class="history-title" data-select="${item.id}"><span class="chat-dot"></span><span>${escapeHtml(item.title)}</span></button>
      <button class="delete-chat" data-delete="${item.id}" aria-label="删除对话">×</button>
    </div>`).join("");
}

function knowledgeSourcesHtml(items) {
  if (!Array.isArray(items) || !items.length) return "";
  const sources = new Map();
  items.forEach((item) => {
    const key = item.minio_object || item.source || "未知文档";
    if (!sources.has(key)) {
      sources.set(key, {name: item.source || "未知文档", pages: new Set()});
    }
    const pageNumber = Number(item.page_number);
    if (Number.isInteger(pageNumber) && pageNumber > 0) {
      sources.get(key).pages.add(pageNumber);
    }
  });
  const rows = Array.from(sources.values()).map((source) => {
    const pages = Array.from(source.pages).sort((left, right) => left - right);
    const pageLabel = pages.length ? `（第${pages.join("、")}页）` : "";
    return `<li><code>${escapeHtml(source.name)}</code>${pageLabel}</li>`;
  }).join("");
  return `<section class="knowledge-sources" aria-label="知识库来源引用">
    <strong>知识库来源引用：</strong>
    <ul>${rows}</ul>
  </section>`;
}

function inlineImageBlockHtml(block) {
  const page = block.page_number == null ? "" : `第 ${block.page_number} 页`;
  const source = [block.source, page].filter(Boolean).join(" · ");
  return `<figure class="answer-inline-image">
    <div class="evidence-image-frame loading">
      <img alt="${escapeAttribute(block.caption || `${block.source} 中的图片`)}" data-evidence-src="${escapeAttribute(block.asset_url)}">
      <span>正在加载原文图片…</span>
    </div>
    <figcaption>
      ${block.caption ? `<p>${escapeHtml(block.caption)}</p>` : ""}
      ${source ? `<small>来源：${escapeHtml(source)}</small>` : ""}
    </figcaption>
  </figure>`;
}

function answerContentHtml(message) {
  if (!Array.isArray(message.contentBlocks) || !message.contentBlocks.length) {
    return `<div class="markdown-body">${renderMarkdown(message.content)}</div>`;
  }
  return `<div class="answer-content">${message.contentBlocks.map((block) => {
    if (block.type === "markdown") {
      return `<div class="markdown-body answer-markdown-block">${renderMarkdown(block.content || "")}</div>`;
    }
    if (block.type === "image" && block.asset_url) return inlineImageBlockHtml(block);
    return "";
  }).join("")}</div>`;
}

async function loadEvidenceImage(assetUrl) {
  if (!evidenceImageCache.has(assetUrl)) {
    const pending = fetch(assetUrl).then(async (response) => {
      if (!response.ok) throw new Error(`图片加载失败 (${response.status})`);
      const objectUrl = URL.createObjectURL(await response.blob());
      evidenceBlobUrls.add(objectUrl);
      return objectUrl;
    }).catch((error) => {
      evidenceImageCache.delete(assetUrl);
      throw error;
    });
    evidenceImageCache.set(assetUrl, pending);
  }
  return evidenceImageCache.get(assetUrl);
}

function hydrateEvidenceImages() {
  elements.conversation.querySelectorAll("img[data-evidence-src]").forEach(async (image) => {
    const frame = image.closest(".evidence-image-frame");
    try {
      image.src = await loadEvidenceImage(image.dataset.evidenceSrc);
      frame?.classList.replace("loading", "loaded");
    } catch {
      frame?.classList.replace("loading", "failed");
      const status = frame?.querySelector("span");
      if (status) status.textContent = "图片加载失败";
    }
  });
}

function messageHtml(message) {
  const badge = message.role === "assistant" ? '<div class="assistant-badge"><i></i><i></i><i></i><i></i></div>' : "";
  const label = message.role === "assistant" ? "Manager" : "你";
  const content = message.role === "assistant"
    ? `${answerContentHtml(message)}${knowledgeSourcesHtml(message.evidence)}`
    : `<p>${escapeHtml(message.content)}</p>`;
  return `<article class="message ${message.role}">${badge}<div class="message-body"><div class="message-label">${label}</div>${traceHtml(message)}${content}</div></article>`;
}

function renderConversation() {
  const conversation = activeConversation();
  if (!conversation?.messages.length) {
    elements.conversation.innerHTML = document.querySelector("#welcomeTemplate").innerHTML;
  } else {
    elements.conversation.innerHTML = `<div class="message-list">${conversation.messages.map(messageHtml).join("")}</div>`;
  }
  requestAnimationFrame(() => {
    hydrateEvidenceImages();
    elements.conversation.scrollTo({ top: elements.conversation.scrollHeight, behavior: "smooth" });
  });
}

function render() { renderHistory(); renderConversation(); }
function clearError() { elements.error.hidden = true; elements.errorText.textContent = ""; }
function showError(message) { elements.errorText.textContent = message; elements.error.hidden = false; }
function closeSidebar() { elements.sidebar.classList.remove("open"); elements.scrim.hidden = true; }

function startClock() {
  clearInterval(state.clock);
  state.clock = setInterval(() => {
    if (state.sending) renderConversation(); else clearInterval(state.clock);
  }, 500);
}

function cancelActiveRequest() {
  const request = state.activeRequest;
  if (!request) return;
  request.intentional = true;
  request.controller.abort();
  if (request.message.traceStatus === "running") {
    request.message.traceStatus = "interrupted";
    request.message.traceOpen = false;
    request.message.durationMs = Date.now() - request.message.startedAt;
    request.message.trace.push({
      sequence: request.message.trace.length + 1,
      status: "interrupted",
      label: "请求已取消",
      agent: "manager",
      tool: null,
      elapsed_ms: request.message.durationMs,
    });
  }
  state.activeRequest = null;
  state.sending = false;
  clearInterval(state.clock);
  save();
}

function applyStreamEvent(message, eventName, payload) {
  if (eventName === "start") {
    message.runId = payload.run_id;
    return;
  }
  if (eventName === "trace") {
    message.trace.push({
      sequence: payload.sequence,
      status: payload.status,
      label: payload.label,
      agent: payload.agent,
      tool: payload.tool,
      elapsed_ms: payload.elapsed_ms,
    });
    return;
  }
  if (eventName === "delta") {
    message.content += payload.text || "";
    return;
  }
  if (eventName === "done") {
    message.content = payload.answer || message.content;
    message.contentBlocks = Array.isArray(payload.content_blocks) ? payload.content_blocks : [];
    message.evidence = Array.isArray(payload.evidence) ? payload.evidence : [];
    message.durationMs = payload.duration_ms || 0;
    message.traceStatus = "completed";
    message.traceOpen = false;
    return;
  }
  if (eventName === "error") {
    message.durationMs = payload.duration_ms || Date.now() - message.startedAt;
    message.traceStatus = "interrupted";
    message.traceOpen = true;
    throw new Error(payload.message || "执行过程已中断，请重试。");
  }
}

async function consumeEventStream(response, onEvent) {
  if (!response.body) throw new Error("浏览器不支持流式响应。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    blocks.forEach((block) => {
      if (!block || block.startsWith(":")) return;
      let eventName = "message";
      const data = [];
      block.split("\n").forEach((line) => {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      });
      if (data.length) onEvent(eventName, JSON.parse(data.join("\n")));
    });
    if (done) break;
  }
}

async function sendMessage(prefill) {
  const content = (prefill || elements.input.value).trim();
  const conversation = activeConversation();
  if (!content || !conversation || state.sending) return;
  clearError();
  elements.input.value = "";
  elements.send.disabled = true;
  conversation.messages.push({ id: id(), role: "user", content });
  if (conversation.title === "新对话") conversation.title = content.slice(0, 24);
  const assistant = {
    id: id(),
    role: "assistant",
    content: "",
    trace: [],
    traceStatus: "running",
    traceOpen: true,
    durationMs: 0,
    startedAt: Date.now(),
    contentBlocks: [],
    evidence: [],
  };
  conversation.messages.push(assistant);
  const controller = new AbortController();
  const activeRequest = { controller, conversationId: conversation.id, message: assistant, intentional: false };
  state.activeRequest = activeRequest;
  state.sending = true;
  startClock();
  save();
  render();

  try {
    const response = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversation.id, message: content }),
      signal: controller.signal,
    });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.error?.message || "请求未完成，请检查模型配置后重试。");
    }
    await consumeEventStream(response, (eventName, payload) => {
      applyStreamEvent(assistant, eventName, payload);
      save();
      if (state.activeId === conversation.id) renderConversation();
    });
    if (assistant.traceStatus === "running") throw new Error("流式连接提前结束，请重试。");
    save();
  } catch (error) {
    if (!activeRequest.intentional) {
      assistant.traceStatus = "interrupted";
      assistant.traceOpen = true;
      assistant.durationMs ||= Date.now() - assistant.startedAt;
      showError(error instanceof Error ? error.message : "网络连接失败，请稍后重试。");
      save();
    }
  } finally {
    if (state.activeRequest === activeRequest) {
      state.activeRequest = null;
      state.sending = false;
      clearInterval(state.clock);
      render();
      elements.input.focus();
    }
  }
}

document.querySelector("#newChatButton").addEventListener("click", createConversation);
document.querySelector("#menuButton").addEventListener("click", () => { elements.sidebar.classList.add("open"); elements.scrim.hidden = false; });
elements.scrim.addEventListener("click", closeSidebar);
elements.send.addEventListener("click", () => sendMessage());
elements.input.addEventListener("input", () => { elements.send.disabled = !elements.input.value.trim() || state.sending; });
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); }
});
elements.history.addEventListener("click", (event) => {
  const select = event.target.closest("[data-select]");
  const remove = event.target.closest("[data-delete]");
  if (select) selectConversation(select.dataset.select);
  if (remove) deleteConversation(remove.dataset.delete);
});
elements.conversation.addEventListener("click", (event) => {
  const suggestion = event.target.closest("[data-message]");
  if (suggestion) sendMessage(suggestion.dataset.message);
});
elements.conversation.addEventListener("toggle", (event) => {
  const panel = event.target.closest?.("[data-trace-id]");
  if (!panel) return;
  for (const conversation of state.conversations) {
    const message = conversation.messages.find((item) => item.id === panel.dataset.traceId);
    if (message) { message.traceOpen = panel.open; save(); break; }
  }
}, true);
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); createConversation(); }
});
window.addEventListener("beforeunload", () => {
  evidenceBlobUrls.forEach((url) => URL.revokeObjectURL(url));
});

document.querySelector("[data-logout]").addEventListener("click", () => window.logout());
window.authReady.then((user) => {
  if (!user) return;
  STORAGE_KEY = `agent-desk-conversations:${user.id}`;
  try { state.conversations = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); } catch { state.conversations = []; }
  state.conversations.forEach((conversation) => conversation.messages.forEach((message) => {
    if (message.traceStatus === "running") {
      message.traceStatus = "interrupted";
      message.traceOpen = false;
    }
  }));
  if (state.conversations[0]) state.activeId = state.conversations[0].id; else createConversation();
  render();
});
