const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#chatInput");
const quickReplies = document.querySelector("#quickReplies");
const restartButton = document.querySelector("#restartButton");
const typingTemplate = document.querySelector("#typingTemplate");

const conversation = { step: "name", prospect_name: "", document_id: "", product: "" };

const labels = {
  identity_agent: "Identidad",
  risk_agent: "Riesgo",
  documentation_agent: "Documentación",
  response_agent: "Respuesta",
  orchestrator_agent: "Orquestador",
  orchestrator: "Orquestador",
};

function addMessage(text, sender = "bot", tone = "") {
  const row = document.createElement("div");
  row.className = `message-row ${sender}`;
  if (sender === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = "O";
    row.appendChild(avatar);
  }
  const bubble = document.createElement("div");
  bubble.className = `bubble ${tone}`.trim();
  bubble.textContent = text;
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollToBottom();
}

function showTyping() {
  const node = typingTemplate.content.firstElementChild.cloneNode(true);
  messages.appendChild(node);
  scrollToBottom();
  return () => node.remove();
}

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function setQuickReplies(options = []) {
  quickReplies.replaceChildren();
  options.forEach(({ label, value }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => handleAnswer(value, label));
    quickReplies.appendChild(button);
  });
}

function setBusy(busy) {
  input.disabled = busy;
  form.querySelector("button").disabled = busy;
  quickReplies.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
}

function activateAgent(name) {
  document.querySelectorAll(".agent-list li").forEach((item) => item.classList.remove("active"));
  const item = document.querySelector(`[data-agent="${name}"]`);
  if (item) item.classList.add("active");
}

function completeAllAgents() {
  document.querySelectorAll(".agent-list li").forEach((item) => {
    item.classList.remove("active");
    item.classList.add("done");
  });
}

function startConversation() {
  Object.assign(conversation, { step: "name", prospect_name: "", document_id: "", product: "" });
  messages.replaceChildren();
  quickReplies.replaceChildren();
  document.querySelectorAll(".agent-list li").forEach((item) => item.className = "");
  setBusy(false);
  input.placeholder = "Escribe tu nombre completo…";
  addMessage("¡Hola! Soy tu asistente de onboarding. Te acompañaré en la solicitud de una nueva cuenta.\n\nPara comenzar, ¿cuál es tu nombre completo?");
  input.focus();
}

function handleAnswer(value, displayValue = value) {
  const clean = String(value).trim();
  if (!clean) return;

  if (conversation.step === "name") {
    if (clean.length < 2) return addMessage("Necesito un nombre de al menos dos caracteres.", "bot", "error");
    conversation.prospect_name = clean;
    addMessage(displayValue, "user");
    conversation.step = "document";
    input.placeholder = "Documento de identidad…";
    addMessage(`Gracias, ${clean}. Ahora ingresa tu documento de identidad. Para esta demo puedes usar 1712345678.`);
    return;
  }

  if (conversation.step === "document") {
    if (!/^[A-Za-z0-9-]{5,30}$/.test(clean)) {
      return addMessage("El documento debe tener entre 5 y 30 caracteres alfanuméricos.", "bot", "error");
    }
    conversation.document_id = clean;
    addMessage(displayValue, "user");
    conversation.step = "product";
    input.placeholder = "Selecciona o escribe un producto…";
    addMessage("¿Qué producto deseas solicitar?");
    setQuickReplies([
      { label: "Cuenta de ahorros", value: "cuenta_ahorros" },
      { label: "Cuenta corriente", value: "cuenta_corriente" },
    ]);
    return;
  }

  if (conversation.step === "product") {
    const normalized = clean.toLowerCase().replaceAll(" ", "_");
    conversation.product = normalized;
    addMessage(displayValue, "user");
    conversation.step = "processing";
    setQuickReplies([]);
    runOnboarding();
  }
}

async function runOnboarding() {
  setBusy(true);
  input.placeholder = "Procesando solicitud…";
  activateAgent("identity");
  addMessage("Perfecto. Los agentes de identidad y riesgo están validando tu solicitud en paralelo.");
  const stopTyping = showTyping();

  try {
    const response = await fetch("/api/v1/onboarding/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prospect_name: conversation.prospect_name,
        document_id: conversation.document_id,
        product: conversation.product,
      }),
    });
    const payload = await response.json();
    stopTyping();
    if (!response.ok) throw new Error(payload.detail ? JSON.stringify(payload.detail) : "No fue posible procesar la solicitud");
    completeAllAgents();
    renderResult(payload);
    conversation.step = "complete";
    input.placeholder = "Proceso finalizado";
  } catch (error) {
    stopTyping();
    addMessage(`No pude completar la solicitud: ${error.message}`, "bot", "error");
    conversation.step = "product";
    setBusy(false);
    input.placeholder = "Intenta nuevamente…";
  }
}

function renderResult(data) {
  const approved = data.status === "approved";
  addMessage(data.customer_message || "El proceso finalizó.", "bot", approved ? "success" : "escalated");

  const card = document.createElement("section");
  card.className = "result-card";
  const title = document.createElement("h3");
  title.textContent = approved ? "Resumen de la validación" : "Solicitud enviada a revisión";
  card.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "result-grid";
  const metrics = [
    ["Estado", data.status],
    ["Confianza", data.identity ? `${Math.round(data.identity.confidence * 100)}%` : "—"],
    ["Riesgo", data.risk?.risk_level || "—"],
    ["Pasos", String(data.step_count)],
  ];
  metrics.forEach(([label, value]) => {
    const metric = document.createElement("div");
    metric.className = "metric";
    const small = document.createElement("small");
    small.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    metric.append(small, strong);
    grid.appendChild(metric);
  });
  card.appendChild(grid);

  [data.identity?.explanation, data.risk?.explanation, data.documentation?.explanation]
    .filter(Boolean)
    .forEach((text) => {
      const paragraph = document.createElement("p");
      paragraph.className = "explanation";
      paragraph.textContent = text;
      card.appendChild(paragraph);
    });

  if (data.documentation?.required_documents?.length) {
    const docs = document.createElement("p");
    docs.className = "explanation";
    docs.textContent = `Documentos: ${data.documentation.required_documents.join(", ")}.`;
    card.appendChild(docs);
  }
  messages.appendChild(card);
  renderTimeline(data.audit || []);
  scrollToBottom();
}

function renderTimeline(events) {
  const card = document.createElement("section");
  card.className = "result-card";
  const title = document.createElement("h3");
  title.textContent = "Trazabilidad del proceso";
  const timeline = document.createElement("div");
  timeline.className = "timeline";
  events.forEach((event) => {
    const item = document.createElement("div");
    item.className = `timeline-item ${event.status}`;
    const dot = document.createElement("span");
    dot.className = "dot";
    const action = document.createElement("span");
    action.textContent = `${labels[event.actor] || event.actor} · ${event.action}`;
    const status = document.createElement("strong");
    status.textContent = event.status;
    item.append(dot, action, status);
    timeline.appendChild(item);
  });
  card.append(title, timeline);
  messages.appendChild(card);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = input.value;
  input.value = "";
  handleAnswer(value);
});

restartButton.addEventListener("click", startConversation);
startConversation();
