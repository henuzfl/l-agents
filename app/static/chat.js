"use strict";

const STORAGE_KEY = "agent-desk-conversations";
const USER_ID = "web-user";
const state = { conversations: [], activeId: "", sending: false };

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

function id() { return crypto.randomUUID(); }
function activeConversation() { return state.conversations.find((item) => item.id === state.activeId); }
function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.conversations)); }
function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
}

function createConversation() {
  const conversation = { id: id(), title: "新对话", messages: [] };
  state.conversations.unshift(conversation);
  state.activeId = conversation.id;
  closeSidebar();
  save();
  render();
  elements.input.focus();
}

function selectConversation(conversationId) {
  state.activeId = conversationId;
  closeSidebar();
  clearError();
  render();
}

function deleteConversation(conversationId) {
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

function messageHtml(message) {
  const badge = message.role === "assistant" ? '<div class="assistant-badge"><i></i><i></i><i></i><i></i></div>' : "";
  const label = message.role === "assistant" ? "Manager" : "你";
  return `<article class="message ${message.role}">${badge}<div class="message-body"><div class="message-label">${label}</div><p>${escapeHtml(message.content)}</p></div></article>`;
}

function renderConversation() {
  const conversation = activeConversation();
  if (!conversation?.messages.length) {
    elements.conversation.innerHTML = document.querySelector("#welcomeTemplate").innerHTML;
  } else {
    const pending = state.sending ? '<article class="message assistant"><div class="assistant-badge"><i></i><i></i><i></i><i></i></div><div class="message-body"><div class="message-label">Manager</div><div class="typing"><span></span><span></span><span></span></div></div></article>' : "";
    elements.conversation.innerHTML = `<div class="message-list">${conversation.messages.map(messageHtml).join("")}${pending}</div>`;
  }
  requestAnimationFrame(() => elements.conversation.scrollTo({ top: elements.conversation.scrollHeight, behavior: "smooth" }));
}

function render() { renderHistory(); renderConversation(); }
function clearError() { elements.error.hidden = true; elements.errorText.textContent = ""; }
function showError(message) { elements.errorText.textContent = message; elements.error.hidden = false; }
function closeSidebar() { elements.sidebar.classList.remove("open"); elements.scrim.hidden = true; }

async function sendMessage(prefill) {
  const content = (prefill || elements.input.value).trim();
  const conversation = activeConversation();
  if (!content || !conversation || state.sending) return;
  clearError();
  elements.input.value = "";
  elements.send.disabled = true;
  conversation.messages.push({ id: id(), role: "user", content });
  if (conversation.title === "新对话") conversation.title = content.slice(0, 24);
  state.sending = true;
  save();
  render();

  try {
    const response = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER_ID, conversation_id: conversation.id, message: content }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "请求未完成，请检查模型配置后重试。");
    conversation.messages.push({ id: id(), role: "assistant", content: payload.answer });
    save();
  } catch (error) {
    showError(error instanceof Error ? error.message : "网络连接失败，请稍后重试。");
  } finally {
    state.sending = false;
    render();
    elements.input.focus();
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
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); createConversation(); }
});

try { state.conversations = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); } catch { state.conversations = []; }
if (state.conversations[0]) state.activeId = state.conversations[0].id; else createConversation();
render();
