/* CareerSphere Student Assistant + Eligibility-based job recommendations. */
(() => {
  "use strict";
  const session = (() => {
    try { return JSON.parse(sessionStorage.getItem("campusconnectUser") || "null"); }
    catch (_) { return null; }
  })();
  if (!session || !session.access_token || String(session.role).toLowerCase() !== "student") return;

  const API = window.CAREERSPHERE_API_URL || "/api";
  const headers = { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json" };
  let conversationId = null;

  const section = document.createElement("section");
  section.className = "cs-recommendations container-fluid px-0";
  section.innerHTML = `
    <div class="cs-section-heading"><div><span class="cs-eyebrow">CURATED FOR YOUR PROFILE</span><h2>Recommended opportunities</h2><p>Based on your department, graduation year and available CGPA details.</p></div><button class="btn btn-outline-primary btn-sm" id="csRefreshRecommendations"><i class="bi bi-arrow-clockwise me-1"></i>Refresh</button></div>
    <div class="cs-recommendation-grid" id="csRecommendationGrid"><div class="cs-empty">Loading eligible opportunities…</div></div>`;
  const jobsSection = document.querySelector(".jobs-section");
  if (jobsSection) jobsSection.parentNode.insertBefore(section, jobsSection);

  async function loadRecommendations() {
    const grid = document.getElementById("csRecommendationGrid");
    if (!grid) return;
    grid.innerHTML = '<div class="cs-empty">Finding opportunities that match your eligibility…</div>';
    try {
      const response = await fetch(`${API}/students/me/recommended-jobs`, { headers: { Authorization: headers.Authorization } });
      const data = await response.json();
      if (!response.ok) throw new Error(readableError(data, "Could not load recommendations."));
      if (!data.length) { grid.innerHTML = '<div class="cs-empty">No eligible recommendations are available right now. Check the latest placement opportunities below.</div>'; return; }
      grid.innerHTML = data.map(job => `<article class="cs-job-card"><div class="cs-job-top"><span class="cs-company-mark">${escapeHtml((job.company || "C").slice(0,1).toUpperCase())}</span><span class="cs-match-label"><i class="bi bi-check-circle-fill"></i> Eligibility match</span></div><h3>${escapeHtml(job.title || "Opportunity")}</h3><p class="cs-company">${escapeHtml(job.company || "Company")}</p><div class="cs-job-meta"><span><i class="bi bi-geo-alt"></i> ${escapeHtml(job.location || "Location not specified")}</span><span><i class="bi bi-mortarboard"></i> ${escapeHtml(job.department || "All departments")}</span></div><p class="cs-job-reason">${escapeHtml(job.recommendation_reason || "Matches your profile eligibility.")}</p><a class="btn btn-primary btn-sm" href="#jobsContainer">View opportunity <i class="bi bi-arrow-right ms-1"></i></a></article>`).join("");
    } catch (error) { grid.innerHTML = `<div class="cs-empty cs-error">${escapeHtml(error.message)}</div>`; }
  }
  function readableError(data, fallback) {
    const detail = data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map(item => typeof item === "string" ? item : `${Array.isArray(item.loc) ? item.loc.join(" → ") + ": " : ""}${item.msg || "Invalid value"}`).join("\n");
    if (detail && typeof detail === "object") return detail.message || JSON.stringify(detail);
    return data?.message || fallback;
  }
  function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  document.getElementById("csRefreshRecommendations")?.addEventListener("click", loadRecommendations);
  loadRecommendations();

  const launcher = document.createElement("button");
  launcher.className = "cs-assistant-launcher"; launcher.type = "button";
  launcher.setAttribute("aria-label", "Open CareerSphere AI Assistant");
  launcher.innerHTML = '<i class="bi bi-stars"></i><span>Career Assistant</span>';
  const panel = document.createElement("aside"); panel.className = "cs-assistant-panel"; panel.hidden = true;
  panel.innerHTML = `<header class="cs-chat-header"><div class="cs-chat-avatar"><i class="bi bi-stars"></i></div><div><strong>CareerSphere Assistant</strong><small><span class="cs-online-dot"></span> Placement support</small></div><button type="button" class="cs-chat-close" aria-label="Close assistant"><i class="bi bi-x-lg"></i></button></header><div class="cs-chat-messages" aria-live="polite"><div class="cs-chat-bubble cs-bot">Hi ${escapeHtml(session.name || "there")}! I can help with resumes, interviews, placement preparation and understanding your application journey. What would you like help with?</div></div><div class="cs-assistant-context"><label for="csApplicationContext">Guide me for an application</label><select id="csApplicationContext"><option value="">General placement help</option></select></div><div class="cs-prompts"><button type="button">Help me prepare for interviews</button><button type="button">How can I improve my resume?</button></div><form class="cs-chat-form"><input maxlength="2000" aria-label="Your message" placeholder="Ask your placement question…" required><button type="submit" aria-label="Send message"><i class="bi bi-send-fill"></i></button></form><div class="cs-chat-footnote">AI guidance can make mistakes. Verify important placement information with your placement office.</div>`;
  document.body.append(launcher, panel);
  const applicationSelect = panel.querySelector("#csApplicationContext");
  fetch(`${API}/students/${encodeURIComponent(session.user_id || session.id || session._id || "")}/applications`, { headers: { Authorization: headers.Authorization } })
    .then(response => response.ok ? response.json() : [])
    .then(applications => {
      if (!Array.isArray(applications)) return;
      applications.forEach(item => {
        const option = document.createElement("option");
        option.value = item.application_id || item.id;
        option.textContent = `${item.title || item.job_title} · ${item.company} · ${item.status}`;
        applicationSelect.appendChild(option);
      });
    }).catch(() => {});
  const messages = panel.querySelector(".cs-chat-messages");
  function addMessage(content, role) { const bubble = document.createElement("div"); bubble.className = `cs-chat-bubble ${role === "user" ? "cs-user" : "cs-bot"}`; bubble.textContent = content; messages.appendChild(bubble); messages.scrollTop = messages.scrollHeight; return bubble; }
  async function loadHistory() {
    try { const response = await fetch(`${API}/assistant/history`, { headers: { Authorization: headers.Authorization } }); if (!response.ok) return; const data = await response.json(); conversationId = data.conversation_id; if (data.messages?.length) { messages.innerHTML = ""; data.messages.forEach(item => addMessage(item.content, item.role)); } }
    catch (_) { /* Keep the welcome message if history is unavailable. */ }
  }
  launcher.addEventListener("click", () => { panel.hidden = !panel.hidden; launcher.classList.toggle("is-open", !panel.hidden); if (!panel.hidden) { loadHistory(); panel.querySelector("input").focus(); } });
  panel.querySelector(".cs-chat-close").addEventListener("click", () => { panel.hidden = true; launcher.classList.remove("is-open"); });
  panel.querySelectorAll(".cs-prompts button").forEach(button => button.addEventListener("click", () => { panel.querySelector("input").value = button.textContent; panel.querySelector("input").focus(); }));
  panel.querySelector("form").addEventListener("submit", async event => {
    event.preventDefault(); const input = panel.querySelector("input"); const message = input.value.trim(); if (!message) return;
    addMessage(message, "user"); input.value = ""; input.disabled = true;
    const pending = addMessage("Thinking through that…", "bot");
    try {
      const response = await fetch(`${API}/assistant/chat`, { method: "POST", headers, body: JSON.stringify({ message, conversation_id: conversationId, application_id: applicationSelect.value || null }) });
      const data = await response.json(); if (!response.ok) throw new Error(readableError(data, "Assistant request failed."));
      conversationId = data.conversation_id; pending.textContent = data.reply;
    } catch (error) { pending.textContent = error.message || "I couldn't send that. Please try again."; }
    finally { input.disabled = false; input.focus(); }
  });
})();
