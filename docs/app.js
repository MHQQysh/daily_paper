const state = {
  papers: [],
  sourcePapers: [],
  topics: [],
  serverTopics: [],
  selectedPaperId: null,
  mode: "all",
  query: "",
  openTopics: new Set(),
  customTopics: false,
};

const TOPIC_STORAGE_KEY = "dailyPaper.customTopics.v1";
const topicTree = document.getElementById("topicTree");
const detail = document.getElementById("paperDetail");
const searchInput = document.getElementById("searchInput");
const allButton = document.getElementById("allButton");
const highButton = document.getElementById("highButton");
const editTopicsButton = document.getElementById("editTopicsButton");
const topicDialog = document.getElementById("topicDialog");
const topicEditor = document.getElementById("topicEditor");
const saveTopicsButton = document.getElementById("saveTopicsButton");
const resetTopicsButton = document.getElementById("resetTopicsButton");
const copyTopicsButton = document.getElementById("copyTopicsButton");
const statusText = document.getElementById("statusText");
const paperCount = document.getElementById("paperCount");
const topicCount = document.getElementById("topicCount");
const latestDate = document.getElementById("latestDate");
const viewTitle = document.getElementById("viewTitle");
const openSidebar = document.getElementById("openSidebar");
const closeSidebar = document.getElementById("closeSidebar");

function byId(topicId) {
  return state.topics.find((topic) => topic.id === topicId);
}

function slugify(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100) || "direction";
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function clonePaper(paper) {
  return {
    ...paper,
    source_topics: paper.source_topics || paper.topics || [],
  };
}

function matchCustomTopics(paper, topics) {
  const text = [paper.title, paper.abstract, paper.abstract_zh, paper.summary_zh, paper.why_relevant_zh]
    .join(" ")
    .toLowerCase();
  return topics
    .filter((topic) => (topic.keywords || []).some((keyword) => text.includes(String(keyword).toLowerCase())))
    .map((topic) => topic.id);
}

function applyTopicModel() {
  state.papers = state.sourcePapers.map((paper) => {
    const next = clonePaper(paper);
    if (state.customTopics) {
      next.topics = matchCustomTopics(next, state.topics);
    } else {
      next.topics = next.source_topics || next.topics || [];
    }
    return next;
  });
}

function formatTopicsForEditor(topics) {
  return topics
    .map((topic) => `${topic.name} | ${(topic.keywords || []).join(", ")}`)
    .join("\n");
}

function parseTopicsFromEditor(value) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [rawName, rawKeywords = ""] = line.split("|");
      const name = rawName.trim();
      const keywords = rawKeywords
        .split(",")
        .map((keyword) => keyword.trim())
        .filter(Boolean);
      return {
        id: slugify(name),
        name,
        description: keywords.slice(0, 5).join(", "),
        keywords,
      };
    })
    .filter((topic) => topic.name && topic.keywords.length);
}

function loadStoredTopics(serverTopics) {
  const stored = localStorage.getItem(TOPIC_STORAGE_KEY);
  if (!stored) {
    state.customTopics = false;
    return serverTopics;
  }
  try {
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed.topics) && parsed.topics.length) {
      state.customTopics = true;
      return parsed.topics;
    }
  } catch {
    localStorage.removeItem(TOPIC_STORAGE_KEY);
  }
  state.customTopics = false;
  return serverTopics;
}

function paperMatches(paper) {
  if (state.mode === "high" && Number(paper.relevance_score || 0) < 60) {
    return false;
  }
  if (!state.query) {
    return true;
  }
  const haystack = [
    paper.title,
    paper.abstract,
    paper.abstract_zh,
    paper.summary_zh,
    paper.why_relevant_zh,
    (paper.authors || []).join(" "),
    (paper.topics || []).map((topicId) => byId(topicId)?.name || topicId).join(" "),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(state.query.toLowerCase());
}

function filteredPapers() {
  return state.papers.filter(paperMatches);
}

function papersForTopic(topicId) {
  return filteredPapers().filter((paper) => (paper.topics || []).includes(topicId));
}

function orphanPapers() {
  return filteredPapers().filter((paper) => !paper.topics || paper.topics.length === 0);
}

function setMode(mode) {
  state.mode = mode;
  allButton.classList.toggle("active", mode === "all");
  highButton.classList.toggle("active", mode === "high");
  viewTitle.textContent = mode === "high" ? "High relevance" : "All papers";
  render();
}

function selectPaper(id) {
  state.selectedPaperId = id;
  render();
  document.body.classList.remove("sidebar-open");
}

function toggleTopic(id) {
  if (state.openTopics.has(id)) {
    state.openTopics.delete(id);
  } else {
    state.openTopics.add(id);
  }
  renderTopicTree();
}

function paperRow(paper) {
  const active = paper.id === state.selectedPaperId ? " active" : "";
  const authors = (paper.authors || []).slice(0, 3).join(", ");
  return `
    <button class="paper-row${active}" type="button" data-paper-id="${escapeHtml(paper.id)}">
      <span class="paper-title">${escapeHtml(paper.title)}</span>
      <span class="paper-meta">
        <span>${escapeHtml(paper.published || "-")}</span>
        <span class="score">${Number(paper.relevance_score || 0)}</span>
        <span>${escapeHtml(authors)}</span>
      </span>
    </button>
  `;
}

function groupedPaperRows(papers) {
  const grouped = papers.reduce((acc, paper) => {
    const date = paper.published || "Unknown date";
    if (!acc.has(date)) {
      acc.set(date, []);
    }
    acc.get(date).push(paper);
    return acc;
  }, new Map());
  return Array.from(grouped.entries())
    .map(([date, items]) => `
      <div class="date-group">
        <div class="date-label">${escapeHtml(date)} · ${items.length}</div>
        ${items.map(paperRow).join("")}
      </div>
    `)
    .join("");
}

function topicGroup(topic, papers) {
  const open = state.openTopics.has(topic.id);
  const active = papers.some((paper) => paper.id === state.selectedPaperId);
  return `
    <section class="topic-group${open ? " open" : ""}">
      <button class="topic-header${active ? " active" : ""}" type="button" data-topic-id="${escapeHtml(topic.id)}">
        <span class="chevron">${open ? "v" : ">"}</span>
        <span>
          <span class="topic-name">${escapeHtml(topic.name)}</span>
          <span class="topic-desc">${escapeHtml(topic.description)}</span>
        </span>
        <span class="count">${papers.length}</span>
      </button>
      <div class="paper-list">
        ${papers.length ? groupedPaperRows(papers) : '<div class="paper-meta">No matches</div>'}
      </div>
    </section>
  `;
}

function renderTopicTree() {
  const groups = state.topics.map((topic) => topicGroup(topic, papersForTopic(topic.id)));
  const orphans = orphanPapers();
  if (orphans.length) {
    groups.push(
      topicGroup(
        { id: "unclassified", name: "Unclassified", description: "Matched by search but not assigned to a direction." },
        orphans,
      ),
    );
  }
  topicTree.innerHTML = groups.join("");
  topicTree.querySelectorAll("[data-topic-id]").forEach((button) => {
    button.addEventListener("click", () => toggleTopic(button.dataset.topicId));
  });
  topicTree.querySelectorAll("[data-paper-id]").forEach((button) => {
    button.addEventListener("click", () => selectPaper(button.dataset.paperId));
  });
}

function linkButton(label, href, primary = false) {
  if (!href) {
    return "";
  }
  return `<a class="link-button${primary ? " primary" : ""}" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function renderDetail() {
  const paper = state.papers.find((item) => item.id === state.selectedPaperId);
  if (!paper) {
    detail.innerHTML = `
      <div class="empty-state">
        <h3>Select a paper from the left</h3>
        <p>Expand a direction, choose a paper, and the summary plus links will appear here.</p>
      </div>
    `;
    return;
  }
  const topicTags = (paper.topics || [])
    .map((topicId) => `<span class="tag">${escapeHtml(byId(topicId)?.name || topicId)}</span>`)
    .join("");
  const links = paper.links || {};
  detail.innerHTML = `
    <article class="paper-detail">
      <div class="detail-kicker">
        <span class="tag strong">Score ${Number(paper.relevance_score || 0)}</span>
        <span class="tag">${escapeHtml(paper.source || "Paper")}</span>
        <span class="tag">${escapeHtml(paper.published || "-")}</span>
        ${topicTags}
      </div>
      <h3>${escapeHtml(paper.title)}</h3>
      <p class="authors">${escapeHtml((paper.authors || []).join(", ") || "Unknown authors")}</p>
      <div class="summary-grid">
        <section class="summary-box">
          <h4>Chinese summary</h4>
          <p>${escapeHtml(paper.summary_zh || "No summary yet.")}</p>
        </section>
        <section class="summary-box">
          <h4>Why relevant</h4>
          <p>${escapeHtml(paper.why_relevant_zh || "No relevance note yet.")}</p>
        </section>
      </div>
      <section class="abstract">
        <h4>中文 Abstract</h4>
        <p>${escapeHtml(paper.abstract_zh || paper.abstract || "No abstract available.")}</p>
      </section>
      <details class="original-abstract">
        <summary>Original English abstract</summary>
        <p>${escapeHtml(paper.abstract || "No abstract available.")}</p>
      </details>
      <div class="links">
        ${linkButton("Abstract", links.abstract, true)}
        ${linkButton("PDF", links.pdf)}
        ${linkButton("Code", links.code)}
      </div>
    </article>
  `;
}

function renderMetrics() {
  const papers = filteredPapers();
  paperCount.textContent = String(papers.length);
  topicCount.textContent = String(state.topics.length);
  latestDate.textContent = papers[0]?.published || "-";
  editTopicsButton.textContent = state.customTopics ? "Edit directions *" : "Edit directions";
}

function render() {
  renderTopicTree();
  renderDetail();
  renderMetrics();
}

async function loadData() {
  try {
    const response = await fetch("papers.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    state.sourcePapers = (data.papers || []).map(clonePaper);
    state.serverTopics = data.topics || [];
    state.topics = loadStoredTopics(state.serverTopics);
    applyTopicModel();
    state.topics.forEach((topic) => state.openTopics.add(topic.id));
    if (state.papers[0]) {
      state.selectedPaperId = state.papers[0].id;
    }
    statusText.textContent = data.last_updated ? `Updated ${new Date(data.last_updated).toLocaleString()}` : "Not updated yet";
    render();
  } catch (error) {
    statusText.textContent = "Failed to load data";
    detail.innerHTML = `<div class="empty-state"><h3>Could not load papers.json</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

searchInput.addEventListener("input", (event) => {
  state.query = event.target.value.trim();
  render();
});
allButton.addEventListener("click", () => setMode("all"));
highButton.addEventListener("click", () => setMode("high"));
openSidebar.addEventListener("click", () => document.body.classList.add("sidebar-open"));
closeSidebar.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
editTopicsButton.addEventListener("click", () => {
  topicEditor.value = formatTopicsForEditor(state.topics);
  topicDialog.showModal();
});
saveTopicsButton.addEventListener("click", () => {
  const topics = parseTopicsFromEditor(topicEditor.value);
  if (!topics.length) {
    return;
  }
  localStorage.setItem(TOPIC_STORAGE_KEY, JSON.stringify({ topics }));
  state.customTopics = true;
  state.topics = topics;
  state.openTopics = new Set(topics.map((topic) => topic.id));
  applyTopicModel();
  topicDialog.close();
  render();
});
resetTopicsButton.addEventListener("click", () => {
  localStorage.removeItem(TOPIC_STORAGE_KEY);
  state.customTopics = false;
  state.topics = state.serverTopics;
  state.openTopics = new Set(state.topics.map((topic) => topic.id));
  applyTopicModel();
  topicEditor.value = formatTopicsForEditor(state.topics);
  render();
});
copyTopicsButton.addEventListener("click", async () => {
  const topics = parseTopicsFromEditor(topicEditor.value);
  const content = JSON.stringify({ topics }, null, 2);
  await navigator.clipboard.writeText(content);
  copyTopicsButton.textContent = "Copied";
  setTimeout(() => {
    copyTopicsButton.textContent = "Copy JSON";
  }, 1200);
});

loadData();
