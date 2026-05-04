const state = {
  sessionId: null,
  session: null,
  deckStack: [],
  currentDeckId: null,
  cards: [],
  cursor: 0,
  nextCursor: null,
  sortMode: "random",
  pollTimer: null,
  pointerStartX: null,
  pointerActive: false,
  pointerMoved: false,
  activeTab: "tab-deck",
  autoOpenedReview: false,
  settings: {},
  selectingFolder: false,
  tutorial: {
    active: false,
    step: null,
    dismissed: false
  }
};

const SETTINGS_KEY = "decksweep_settings_v1";
const DEFAULT_SETTINGS = {
  includeHidden: false,
  confirmApply: true,
  autoOpenReview: true,
  autoResume: true,
  showSplash: true,
  defaultSort: "random",
  swipeThreshold: 95,
  deckPageLimit: 24,
  theme: "sunset"
};

const TUTORIAL_STEPS = {
  root: {
    title: "Step 1 - Folder Root",
    message: "Choose directory or paste path and hit Start Session to start clearing.",
    dismissLabel: "Skip tutorial",
    targetKey: "rootPanel"
  },
  deck: {
    title: "Step 2 - Main Deck",
    message: "Swipe right to keep this file, left to queue delete. Use arrow keys, and click the card to view more properties.",
    dismissLabel: "Got it",
    targetKey: "mainDeckPanel"
  }
};

const elements = {
  splashOverlay: document.getElementById("splashOverlay"),
  splashStartBtn: document.getElementById("splashStartBtn"),
  splashDontShow: document.getElementById("splashDontShow"),
  splashAcknowledge: document.getElementById("splashAcknowledge"),
  settingIncludeHidden: document.getElementById("settingIncludeHidden"),
  settingConfirmApply: document.getElementById("settingConfirmApply"),
  settingAutoOpenReview: document.getElementById("settingAutoOpenReview"),
  settingAutoResume: document.getElementById("settingAutoResume"),
  settingShowSplash: document.getElementById("settingShowSplash"),
  settingDefaultSort: document.getElementById("settingDefaultSort"),
  settingSwipeThreshold: document.getElementById("settingSwipeThreshold"),
  settingSwipeThresholdValue: document.getElementById("settingSwipeThresholdValue"),
  settingDeckPageLimit: document.getElementById("settingDeckPageLimit"),
  settingDeckPageLimitValue: document.getElementById("settingDeckPageLimitValue"),
  themeTiles: Array.from(document.querySelectorAll(".theme-tile")),
  rootPanel: document.getElementById("rootPanel"),
  mainDeckPanel: document.getElementById("mainDeckPanel"),
  rootPathInput: document.getElementById("rootPathInput"),
  browsePathBtn: document.getElementById("browsePathBtn"),
  sortModeSelect: document.getElementById("sortModeSelect"),
  startSessionBtn: document.getElementById("startSessionBtn"),
  resumeBtn: document.getElementById("resumeBtn"),
  sessionStatus: document.getElementById("sessionStatus"),
  indexedCount: document.getElementById("indexedCount"),
  scoreCount: document.getElementById("scoreCount"),
  streakCount: document.getElementById("streakCount"),
  reclaimableCount: document.getElementById("reclaimableCount"),
  deckPathLabel: document.getElementById("deckPathLabel"),
  backDeckBtn: document.getElementById("backDeckBtn"),
  flashcard: document.getElementById("flashcard"),
  emptyDeckState: document.getElementById("emptyDeckState"),
  cardIcon: document.getElementById("cardIcon"),
  previewIcon: document.getElementById("previewIcon"),
  cardKindBadge: document.getElementById("cardKindBadge"),
  cardName: document.getElementById("cardName"),
  cardPath: document.getElementById("cardPath"),
  cardSize: document.getElementById("cardSize"),
  propType: document.getElementById("propType"),
  propMime: document.getElementById("propMime"),
  propSize: document.getElementById("propSize"),
  propPercent: document.getElementById("propPercent"),
  propModified: document.getElementById("propModified"),
  keepBtn: document.getElementById("keepBtn"),
  deleteBtn: document.getElementById("deleteBtn"),
  enterBtn: document.getElementById("enterBtn"),
  skipBtn: document.getElementById("skipBtn"),
  openBtn: document.getElementById("openBtn"),
  reviewBtn: document.getElementById("reviewBtn"),
  applyBtn: document.getElementById("applyBtn"),
  previewContainer: document.getElementById("previewContainer"),
  fileTreeAscii: document.getElementById("fileTreeAscii"),
  fileWebMeta: document.getElementById("fileWebMeta"),
  fileWebEmpty: document.getElementById("fileWebEmpty"),
  reviewDeleteCount: document.getElementById("reviewDeleteCount"),
  reviewKeepCount: document.getElementById("reviewKeepCount"),
  reviewUnresolvedCount: document.getElementById("reviewUnresolvedCount"),
  reviewReclaimable: document.getElementById("reviewReclaimable"),
  deleteList: document.getElementById("deleteList"),
  keepList: document.getElementById("keepList"),
  summaryContent: document.getElementById("summaryContent"),
  tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
  tabPanels: Array.from(document.querySelectorAll(".tab-panel")),
  stackShadows: Array.from(document.querySelectorAll(".stack-shadow")),
  tutorialOverlay: document.getElementById("tutorialOverlay"),
  tutorialTooltip: document.getElementById("tutorialTooltip"),
  tutorialStepTitle: document.getElementById("tutorialStepTitle"),
  tutorialText: document.getElementById("tutorialText"),
  tutorialDismissBtn: document.getElementById("tutorialDismissBtn"),
  toast: document.getElementById("toast")
};

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const precision = value >= 100 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizePath(path) {
  return String(path || "").replaceAll("/", "\\");
}

function depthFromRoot(path) {
  if (!state.session || !state.session.root_path) {
    return 0;
  }
  const root = normalizePath(state.session.root_path).replace(/\\+$/, "");
  const full = normalizePath(path);
  if (!full.toLowerCase().startsWith(root.toLowerCase())) {
    return 0;
  }
  const relative = full.slice(root.length).replace(/^\\+/, "");
  if (!relative) {
    return 0;
  }
  const parts = relative.split("\\").filter(Boolean);
  return Math.max(0, parts.length - 1);
}

function relativePathFromRoot(path) {
  if (!state.session || !state.session.root_path) {
    return normalizePath(path);
  }
  const root = normalizePath(state.session.root_path).replace(/\\+$/, "");
  const full = normalizePath(path);
  if (!full.toLowerCase().startsWith(root.toLowerCase())) {
    return full;
  }
  const relative = full.slice(root.length).replace(/^\\+/, "");
  return relative || ".";
}

function statusToken(action) {
  if (action === "keep") {
    return "K";
  }
  if (action === "delete") {
    return "D";
  }
  return "U";
}

function statusClass(action) {
  if (action === "keep") {
    return "tree-status-k";
  }
  if (action === "delete") {
    return "tree-status-d";
  }
  return "tree-status-u";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_error) {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function loadSettings() {
  let parsed = {};
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      parsed = JSON.parse(stored);
    }
  } catch (_error) {
    parsed = {};
  }
  const merged = { ...DEFAULT_SETTINGS, ...parsed };
  if (!["random", "size_desc", "newest"].includes(merged.defaultSort)) {
    merged.defaultSort = "random";
  }
  if (!["sunset", "ocean", "forest", "dusk", "dark"].includes(merged.theme)) {
    merged.theme = "sunset";
  }
  merged.swipeThreshold = clamp(Number(merged.swipeThreshold) || 95, 60, 180);
  merged.deckPageLimit = clamp(Number(merged.deckPageLimit) || 24, 12, 48);
  merged.includeHidden = Boolean(merged.includeHidden);
  merged.confirmApply = Boolean(merged.confirmApply);
  merged.autoOpenReview = Boolean(merged.autoOpenReview);
  merged.autoResume = Boolean(merged.autoResume);
  merged.showSplash = Boolean(merged.showSplash);
  state.settings = merged;
}

function saveSettings() {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
}

function applyTheme(themeName) {
  document.body.dataset.theme = themeName;
  elements.themeTiles.forEach((tile) => {
    tile.classList.toggle("active", tile.dataset.theme === themeName);
  });
}

function syncSettingsUI() {
  elements.settingIncludeHidden.checked = state.settings.includeHidden;
  elements.settingConfirmApply.checked = state.settings.confirmApply;
  elements.settingAutoOpenReview.checked = state.settings.autoOpenReview;
  elements.settingAutoResume.checked = state.settings.autoResume;
  elements.settingShowSplash.checked = state.settings.showSplash;
  elements.settingDefaultSort.value = state.settings.defaultSort;
  elements.settingSwipeThreshold.value = String(state.settings.swipeThreshold);
  elements.settingDeckPageLimit.value = String(state.settings.deckPageLimit);
  elements.settingSwipeThresholdValue.textContent = `${state.settings.swipeThreshold}px`;
  elements.settingDeckPageLimitValue.textContent = `${state.settings.deckPageLimit}`;
  if (!state.sessionId) {
    elements.sortModeSelect.value = state.settings.defaultSort;
  }
  applyTheme(state.settings.theme);
}

function isSplashVisible() {
  return !elements.splashOverlay.classList.contains("hidden");
}

function hideSplash() {
  elements.splashOverlay.classList.add("hidden");
  maybeStartTutorial();
}

function canStartFromSplash() {
  return Boolean(elements.splashAcknowledge.checked);
}

function syncSplashActionState() {
  elements.splashStartBtn.disabled = !canStartFromSplash();
}

function initSplash() {
  elements.splashAcknowledge.checked = false;
  syncSplashActionState();
  elements.splashDontShow.checked = !state.settings.showSplash;
  if (!state.settings.showSplash) {
    hideSplash();
  } else {
    elements.splashOverlay.classList.remove("hidden");
    hideTutorial();
  }
}

function clearTutorialHighlights() {
  [elements.rootPanel, elements.mainDeckPanel].forEach((panel) => {
    if (panel) {
      panel.classList.remove("tutorial-focus");
    }
  });
}

function hideTutorial() {
  clearTutorialHighlights();
  elements.tutorialOverlay.classList.add("hidden");
  state.tutorial.active = false;
  state.tutorial.step = null;
}

function positionTutorialTooltip() {
  if (!state.tutorial.active || !state.tutorial.step) {
    return;
  }
  const step = TUTORIAL_STEPS[state.tutorial.step];
  if (!step) {
    return;
  }
  const target = elements[step.targetKey];
  if (!target) {
    return;
  }
  const rect = target.getBoundingClientRect();
  if (rect.width < 8 || rect.height < 8) {
    return;
  }
  const spacing = 12;
  const tipWidth = elements.tutorialTooltip.offsetWidth;
  const tipHeight = elements.tutorialTooltip.offsetHeight;

  let top = rect.bottom + spacing;
  if (top + tipHeight > window.innerHeight - spacing) {
    top = rect.top - tipHeight - spacing;
  }
  if (top < spacing) {
    top = spacing;
  }

  let left = rect.left;
  if (left + tipWidth > window.innerWidth - spacing) {
    left = window.innerWidth - tipWidth - spacing;
  }
  if (left < spacing) {
    left = spacing;
  }

  elements.tutorialTooltip.style.top = `${Math.round(top)}px`;
  elements.tutorialTooltip.style.left = `${Math.round(left)}px`;
}

function showTutorialStep(stepName) {
  if (state.tutorial.dismissed || isSplashVisible()) {
    return;
  }
  const step = TUTORIAL_STEPS[stepName];
  if (!step) {
    return;
  }
  const target = elements[step.targetKey];
  if (!target) {
    return;
  }
  clearTutorialHighlights();
  target.classList.add("tutorial-focus");
  elements.tutorialStepTitle.textContent = step.title;
  elements.tutorialText.textContent = step.message;
  elements.tutorialDismissBtn.textContent = step.dismissLabel;
  elements.tutorialOverlay.classList.remove("hidden");
  state.tutorial.active = true;
  state.tutorial.step = stepName;
  requestAnimationFrame(positionTutorialTooltip);
}

function maybeStartTutorial() {
  if (state.tutorial.dismissed || isSplashVisible()) {
    return;
  }
  if (state.sessionId) {
    showTutorialStep("deck");
    return;
  }
  showTutorialStep("root");
}

function dismissTutorial() {
  state.tutorial.dismissed = true;
  hideTutorial();
}

function setToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  setTimeout(() => elements.toast.classList.add("hidden"), 2300);
}

function setSessionHud(session) {
  elements.sessionStatus.textContent = session.status;
  elements.indexedCount.textContent = session.indexed_count.toLocaleString();
  elements.scoreCount.textContent = session.score.toLocaleString();
  elements.streakCount.textContent = session.streak.toLocaleString();
  elements.reclaimableCount.textContent = formatBytes(session.reclaimed_estimate_bytes);
}

function clearFileWeb(message = "Waiting for session...") {
  elements.fileTreeAscii.innerHTML = "";
  elements.fileWebMeta.textContent = message;
  elements.fileWebEmpty.classList.remove("hidden");
}

function buildAsciiTree(nodes) {
  const root = {
    name: ".",
    kind: "folder",
    action: "unresolved",
    size_bytes: 0,
    children: new Map(),
    isSource: false
  };

  for (const node of nodes) {
    const relative = normalizePath(node.relative_path || node.name || "").replace(/^\\+/, "");
    if (!relative) {
      continue;
    }
    const parts = relative.split("\\").filter(Boolean);
    let current = root;
    let currentPath = "";
    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index];
      currentPath = currentPath ? `${currentPath}\\${part}` : part;
      if (!current.children.has(part)) {
        current.children.set(part, {
          name: part,
          kind: index === parts.length - 1 ? node.kind : "folder",
          action: "unresolved",
          size_bytes: 0,
          children: new Map(),
          isSource: false
        });
      }
      const child = current.children.get(part);
      child.size_bytes += Number(node.size_bytes) || 0;
      if (index === parts.length - 1) {
        child.kind = node.kind;
        child.action = node.effective_action || "unresolved";
        child.isSource = true;
      }
      current = child;
    }
  }

  const resolveFolderStates = (treeNode) => {
    if (!treeNode.children.size) {
      return treeNode.action || "unresolved";
    }
    const states = new Set();
    for (const child of treeNode.children.values()) {
      states.add(resolveFolderStates(child));
    }
    if (treeNode.isSource) {
      states.add(treeNode.action || "unresolved");
    }
    if (states.size === 1) {
      const [single] = states;
      treeNode.action = single;
      return single;
    }
    treeNode.action = "unresolved";
    return "unresolved";
  };

  resolveFolderStates(root);
  return root;
}

function renderFileWeb(payload) {
  const nodes = payload.nodes || [];
  const counts = payload.counts || { unresolved: 0, keep: 0, delete: 0 };
  if (!nodes.length) {
    clearFileWeb(
      payload.status === "scanning"
        ? `Indexing... ${payload.indexed_count.toLocaleString()} found`
        : "No files available yet."
    );
    return;
  }

  elements.fileWebEmpty.classList.add("hidden");
  elements.fileWebMeta.textContent =
    `${payload.indexed_count.toLocaleString()} indexed | `
    + `${counts.unresolved} unresolved, ${counts.keep} keep, ${counts.delete} delete`;

  const rootLabel = payload.root_name || "Root";
  const sortedNodes = [...nodes].sort((a, b) => Number(b.size_bytes) - Number(a.size_bytes));
  const tree = buildAsciiTree(sortedNodes);
  const lines = [];
  const maxLines = 140;

  lines.push({
    prefix: `[ROOT] ${rootLabel} (${formatBytes(payload.root_size_bytes || 0)})`,
    action: "unresolved",
    depth: 0
  });

  const traverse = (node, prefix, isLast, depth) => {
    if (lines.length >= maxLines) {
      return;
    }
    const connector = isLast ? "`-- " : "|-- ";
    const label = node.kind === "folder" ? "[DIR]" : "[FILE]";
    const nodeName = node.name.length > 35 ? `${node.name.slice(0, 34)}...` : node.name;
    lines.push({
      prefix: `${prefix}${connector}${label} ${nodeName} (${formatBytes(node.size_bytes)})`,
      action: node.action,
      depth
    });

    const nextPrefix = `${prefix}${isLast ? "    " : "|   "}`;
    const children = Array.from(node.children.values()).sort(
      (left, right) => Number(right.size_bytes) - Number(left.size_bytes)
    );
    for (let index = 0; index < children.length; index += 1) {
      traverse(children[index], nextPrefix, index === children.length - 1, depth + 1);
      if (lines.length >= maxLines) {
        break;
      }
    }
  };

  const children = Array.from(tree.children.values()).sort(
    (left, right) => Number(right.size_bytes) - Number(left.size_bytes)
  );
  for (let index = 0; index < children.length; index += 1) {
    traverse(children[index], "", index === children.length - 1, 1);
    if (lines.length >= maxLines) {
      break;
    }
  }

  if (lines.length >= maxLines) {
    lines.push({
      prefix: "... more items not shown",
      action: "unresolved",
      depth: 0
    });
  }

  elements.fileTreeAscii.innerHTML = lines
    .map((line) => {
      const token = statusToken(line.action);
      return `<div class="tree-line">${escapeHtml(line.prefix)} <span class="${statusClass(line.action)}">[${token}]</span></div>`;
    })
    .join("");
}

async function refreshFileWeb() {
  if (!state.sessionId) {
    clearFileWeb("Waiting for session...");
    return;
  }
  try {
    const payload = await api(`/api/session/${state.sessionId}/file-web?limit=72`);
    renderFileWeb(payload);
  } catch (error) {
    clearFileWeb(error.message);
  }
}

function activateTab(tabId) {
  state.activeTab = tabId;
  elements.tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  elements.tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === tabId);
  });
  if (state.tutorial.active) {
    requestAnimationFrame(positionTutorialTooltip);
  }
}

function clearPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function refreshSession() {
  if (!state.sessionId) {
    return;
  }
  const session = await api(`/api/session/${state.sessionId}`);
  state.session = session;
  state.sortMode = session.order_mode || state.sortMode;
  elements.sortModeSelect.value = state.sortMode;
  setSessionHud(session);
  await refreshFileWeb();
  if (session.status === "ready") {
    clearPolling();
  }
}

function startPollingSession() {
  clearPolling();
  state.pollTimer = setInterval(async () => {
    try {
      await refreshSession();
      if (state.session && state.session.status === "ready" && state.cards.length === 0) {
        await loadDeck({ reset: true });
      }
    } catch (error) {
      clearPolling();
      setToast(error.message);
    }
  }, 1800);
}

async function browseForPath() {
  if (state.selectingFolder) {
    return;
  }
  state.selectingFolder = true;
  try {
    const payload = await api("/api/system/select-folder", { method: "POST" });
    if (payload.path) {
      elements.rootPathInput.value = payload.path;
    }
  } catch (error) {
    setToast(error.message);
  } finally {
    state.selectingFolder = false;
  }
}

async function startSession() {
  try {
    const payload = {
      root_path: elements.rootPathInput.value.trim() || null,
      include_hidden: state.settings.includeHidden,
      order_mode: elements.sortModeSelect.value
    };
    const session = await api("/api/session/start", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    await hydrateSession(session);
    setToast("Session started. Indexing in background.");
  } catch (error) {
    setToast(error.message);
  }
}

async function resumeLatest() {
  try {
    const session = await api("/api/session/latest");
    await hydrateSession(session);
    setToast("Resumed latest session.");
  } catch (error) {
    setToast(error.message);
  }
}

async function hydrateSession(session) {
  state.sessionId = session.session_id;
  localStorage.setItem("decksweep_session_id", state.sessionId);
  state.session = session;
  state.sortMode = session.order_mode;
  elements.sortModeSelect.value = state.sortMode;
  state.deckStack = [{ deckId: session.root_deck_id, label: "Main Deck" }];
  state.currentDeckId = session.root_deck_id;
  state.cards = [];
  state.cursor = 0;
  state.nextCursor = null;
  state.autoOpenedReview = false;
  setSessionHud(session);
  updateDeckPath();
  activateTab("tab-deck");
  if (!state.tutorial.dismissed) {
    showTutorialStep("deck");
  }
  if (session.status !== "ready") {
    startPollingSession();
  } else {
    clearPolling();
  }
  await loadDeck({ reset: true });
  await refreshFileWeb();
}

function updateDeckPath() {
  const label = state.deckStack.map((deck) => deck.label).join(" / ");
  elements.deckPathLabel.textContent = label;
  elements.backDeckBtn.disabled = state.deckStack.length <= 1;
}

async function loadDeck({ reset }) {
  if (!state.sessionId || !state.currentDeckId) {
    return;
  }
  if (!state.session || state.session.status === "failed") {
    setToast("Session failed to index.");
    return;
  }
  if (reset) {
    state.cards = [];
    state.cursor = 0;
    state.nextCursor = null;
    state.autoOpenedReview = false;
  }
  try {
    const pageLimit = state.settings.deckPageLimit || 24;
    const page = await api(
      `/api/session/${state.sessionId}/deck?deck_id=${encodeURIComponent(
        state.currentDeckId
      )}&cursor=${state.cursor}&limit=${pageLimit}&sort=${encodeURIComponent(
        elements.sortModeSelect.value
      )}&unresolved_only=true`
    );
    if (reset) {
      state.cards = page.items;
    } else {
      state.cards = state.cards.concat(page.items);
    }
    state.cursor = page.next_cursor || 0;
    state.nextCursor = page.next_cursor;
    renderCard();
    await refreshFileWeb();
  } catch (error) {
    setToast(error.message);
  }
}

function currentCard() {
  if (!state.cards.length) {
    return null;
  }
  return state.cards[0];
}

function cardIconUrl(item) {
  if (!item || !state.sessionId) {
    return "";
  }
  return `/api/session/${state.sessionId}/icon/${item.id}`;
}

async function renderPreview(item) {
  if (!item || !state.sessionId) {
    elements.previewContainer.innerHTML = '<p class="muted">Select a card to load preview.</p>';
    elements.previewIcon.src = "";
    return;
  }
  elements.previewIcon.src = cardIconUrl(item);
  try {
    const preview = await api(`/api/session/${state.sessionId}/preview/${item.id}`);
    if (preview.preview_type === "image") {
      elements.previewContainer.innerHTML = `<img alt="Preview" src="${preview.content_url}">`;
      return;
    }
    if (preview.preview_type === "video") {
      elements.previewContainer.innerHTML = `<video controls src="${preview.content_url}"></video>`;
      return;
    }
    if (preview.preview_type === "audio") {
      elements.previewContainer.innerHTML = `<audio controls src="${preview.content_url}"></audio>`;
      return;
    }
    if (preview.preview_type === "pdf") {
      elements.previewContainer.innerHTML = `<iframe title="PDF preview" src="${preview.content_url}" width="100%" height="520"></iframe>`;
      return;
    }
    if (preview.preview_type === "text") {
      elements.previewContainer.innerHTML = `<pre>${escapeHtml(preview.text_snippet || "")}</pre>`;
      return;
    }
    if (preview.preview_type === "folder") {
      const children = preview.folder_children || [];
      const childMarkup = children.length
        ? `<ul>${children.map((child) => `<li>${escapeHtml(child)}</li>`).join("")}</ul>`
        : "<p>No readable children.</p>";
      elements.previewContainer.innerHTML = `
        <div class="preview-metadata">
          <div class="preview-meta-header">
            <img class="item-icon" src="${cardIconUrl(item)}" alt="Folder icon">
            <h3>Folder Snapshot</h3>
          </div>
          ${childMarkup}
        </div>
      `;
      return;
    }
    elements.previewContainer.innerHTML = `
      <div class="preview-metadata">
        <div class="preview-meta-header">
          <img class="item-icon" src="${cardIconUrl(item)}" alt="File icon">
          <h3>Metadata Preview</h3>
        </div>
        <p class="muted">${escapeHtml(preview.metadata_only_reason || "Preview unavailable.")}</p>
      </div>
    `;
  } catch (error) {
    elements.previewContainer.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

function updateStackVisuals() {
  const hasCards = state.cards.length > 0;
  elements.stackShadows.forEach((shadow) => {
    shadow.style.opacity = hasCards ? "" : "0";
  });
}

function clearDragState() {
  elements.flashcard.classList.remove("drag-left", "drag-right");
  elements.flashcard.style.transform = "";
}

function renderCard() {
  const card = currentCard();
  if (!card) {
    elements.flashcard.classList.add("hidden");
    elements.emptyDeckState.classList.remove("hidden");
    elements.enterBtn.disabled = true;
    elements.skipBtn.disabled = true;
    elements.keepBtn.disabled = true;
    elements.deleteBtn.disabled = true;
    elements.openBtn.disabled = true;
    updateStackVisuals();
    renderPreview(null);
    if (state.nextCursor !== null) {
      loadDeck({ reset: false });
    } else if (
      state.settings.autoOpenReview
      && state.sessionId
      && !state.autoOpenedReview
      && state.activeTab === "tab-deck"
    ) {
      state.autoOpenedReview = true;
      openReview();
    }
    return;
  }

  state.autoOpenedReview = false;
  elements.flashcard.classList.remove("hidden");
  elements.emptyDeckState.classList.add("hidden");
  elements.flashcard.classList.remove("is-flipped", "swipe-left", "swipe-right");
  clearDragState();
  elements.keepBtn.disabled = false;
  elements.deleteBtn.disabled = false;
  elements.openBtn.disabled = false;

  const isFolder = card.kind === "folder";
  elements.enterBtn.disabled = !isFolder;
  elements.skipBtn.disabled = !isFolder;

  elements.cardKindBadge.textContent = isFolder ? "Folder Card" : "File Card";
  elements.cardName.textContent = card.name;
  elements.cardPath.textContent = card.path;
  elements.cardSize.textContent = formatBytes(card.size_bytes);
  elements.propType.textContent = card.kind;
  elements.propMime.textContent = card.mime || "Unknown";
  elements.propSize.textContent = formatBytes(card.size_bytes);
  elements.propPercent.textContent = `${card.percent_of_root.toFixed(2)}%`;
  elements.propModified.textContent = card.modified_at
    ? new Date(card.modified_at).toLocaleString()
    : "-";
  elements.cardIcon.src = cardIconUrl(card);

  updateStackVisuals();
  renderPreview(card);
}

async function decision(action) {
  const card = currentCard();
  if (!card || !state.sessionId) {
    return;
  }
  try {
    await api(`/api/session/${state.sessionId}/decision`, {
      method: "POST",
      body: JSON.stringify({ item_id: card.id, action })
    });
    clearDragState();
    const className = action === "keep" ? "swipe-right" : "swipe-left";
    elements.flashcard.classList.add(className);
    setTimeout(() => {
      state.cards.shift();
      renderCard();
    }, 140);
    await refreshSession();
    if (state.cards.length < 4 && state.nextCursor !== null) {
      await loadDeck({ reset: false });
    }
  } catch (error) {
    setToast(error.message);
  }
}

async function enterFolder() {
  const card = currentCard();
  if (!card || card.kind !== "folder" || !state.sessionId) {
    return;
  }
  try {
    const payload = await api(`/api/session/${state.sessionId}/enter-folder`, {
      method: "POST",
      body: JSON.stringify({ item_id: card.id })
    });
    state.deckStack.push({ deckId: payload.deck_id, label: payload.name });
    state.currentDeckId = payload.deck_id;
    updateDeckPath();
    await loadDeck({ reset: true });
  } catch (error) {
    setToast(error.message);
  }
}

async function skipFolder() {
  const card = currentCard();
  if (!card || card.kind !== "folder" || !state.sessionId) {
    return;
  }
  try {
    await api(`/api/session/${state.sessionId}/skip-folder`, {
      method: "POST",
      body: JSON.stringify({ item_id: card.id })
    });
    state.cards.shift();
    renderCard();
    setToast("Folder skipped.");
  } catch (error) {
    setToast(error.message);
  }
}

async function goBackDeck() {
  if (state.deckStack.length <= 1) {
    return;
  }
  state.deckStack.pop();
  const previous = state.deckStack[state.deckStack.length - 1];
  state.currentDeckId = previous.deckId;
  updateDeckPath();
  await loadDeck({ reset: true });
}

async function openInSystem() {
  const card = currentCard();
  if (!card || !state.sessionId) {
    return;
  }
  try {
    await api(`/api/session/${state.sessionId}/open/${card.id}`, { method: "POST" });
    setToast("Located in File Explorer.");
  } catch (error) {
    setToast(error.message);
  }
}

function renderReviewList(container, items) {
  if (!items.length) {
    container.innerHTML = '<p class="muted">No items.</p>';
    return;
  }
  const sortedItems = [...items].sort((left, right) =>
    normalizePath(left.path).localeCompare(normalizePath(right.path), undefined, {
      sensitivity: "base"
    })
  );
  container.innerHTML = sortedItems
    .map(
      (item) => `
      <article class="review-entry ${depthFromRoot(item.path) > 0 ? "indented" : ""}" style="--indent:${Math.min(
        depthFromRoot(item.path) * 14,
        64
      )}px">
        <strong>${escapeHtml(item.name)}</strong>
        <div class="path">${escapeHtml(relativePathFromRoot(item.path))}</div>
        <div class="row">
          <span>${item.kind}</span>
          <span>${formatBytes(item.size_bytes)}</span>
        </div>
        <div class="controls">
          <button class="ghost-btn review-undo" data-item-id="${item.id}">Undo</button>
          <button class="ghost-btn review-toggle" data-item-id="${item.id}" data-next="${item.effective_action === "delete" ? "keep" : "delete"}">
            Mark ${item.effective_action === "delete" ? "Keep" : "Delete"}
          </button>
        </div>
      </article>
    `
    )
    .join("");
}

function bindReviewButtons() {
  document.querySelectorAll(".review-undo").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.sessionId) {
        return;
      }
      const itemId = button.dataset.itemId;
      try {
        await api(`/api/session/${state.sessionId}/undo`, {
          method: "POST",
          body: JSON.stringify({ item_id: itemId })
        });
        await openReview();
        await refreshSession();
        await loadDeck({ reset: true });
      } catch (error) {
        setToast(error.message);
      }
    });
  });

  document.querySelectorAll(".review-toggle").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.sessionId) {
        return;
      }
      const itemId = button.dataset.itemId;
      const nextAction = button.dataset.next;
      try {
        await api(`/api/session/${state.sessionId}/decision`, {
          method: "POST",
          body: JSON.stringify({ item_id: itemId, action: nextAction })
        });
        await openReview();
        await refreshSession();
        await loadDeck({ reset: true });
      } catch (error) {
        setToast(error.message);
      }
    });
  });
}

async function openReview() {
  if (!state.sessionId) {
    setToast("Start a session first.");
    return;
  }
  try {
    const review = await api(`/api/session/${state.sessionId}/review`);
    activateTab("tab-review");
    elements.reviewDeleteCount.textContent = review.delete_count.toLocaleString();
    elements.reviewKeepCount.textContent = review.keep_count.toLocaleString();
    elements.reviewUnresolvedCount.textContent = review.unresolved_count.toLocaleString();
    elements.reviewReclaimable.textContent = formatBytes(review.reclaimable_bytes);
    renderReviewList(elements.deleteList, review.delete_items);
    renderReviewList(elements.keepList, review.keep_items);
    bindReviewButtons();
  } catch (error) {
    setToast(error.message);
  }
}

async function applyQueue() {
  if (!state.sessionId) {
    setToast("Start a session first.");
    return;
  }
  if (state.settings.confirmApply && !window.confirm("Move queued items to Recycle Bin now?")) {
    return;
  }
  try {
    const result = await api(`/api/session/${state.sessionId}/apply`, { method: "POST" });
    setToast(`Applied queue: ${result.success_count}/${result.queued_count} moved to Recycle Bin.`);
    await refreshSession();
    await openSummary();
  } catch (error) {
    setToast(error.message);
  }
}

async function openSummary() {
  if (!state.sessionId) {
    activateTab("tab-summary");
    return;
  }
  try {
    const summary = await api(`/api/session/${state.sessionId}/summary`);
    activateTab("tab-summary");
    const topItems = summary.top_reclaimed_items || [];
    const topMarkup = topItems.length
      ? `<ul>${topItems
          .map(
            (item) =>
              `<li>${escapeHtml(item.name)} <strong>${formatBytes(item.size_bytes)}</strong></li>`
          )
          .join("")}</ul>`
      : "<p>No delete targets yet.</p>";

    elements.summaryContent.innerHTML = `
      <div class="review-metrics">
        <div><span>Score</span><strong>${summary.score.toLocaleString()}</strong></div>
        <div><span>Max Streak</span><strong>${summary.max_streak.toLocaleString()}</strong></div>
        <div><span>Delete Count</span><strong>${summary.delete_count.toLocaleString()}</strong></div>
        <div><span>Reclaimed</span><strong>${formatBytes(summary.reclaimed_bytes)}</strong></div>
      </div>
      <h3>Badges</h3>
      <div class="badge-row">${summary.badges
        .map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`)
        .join("")}</div>
      <h3>Top Reclaimed Targets</h3>
      ${topMarkup}
    `;
  } catch (error) {
    setToast(error.message);
  }
}

function handleKeyboard(event) {
  if (isSplashVisible()) {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!canStartFromSplash()) {
        return;
      }
      state.settings.showSplash = !elements.splashDontShow.checked;
      elements.settingShowSplash.checked = state.settings.showSplash;
      saveSettings();
      hideSplash();
    }
    return;
  }
  const activeTag = document.activeElement ? document.activeElement.tagName : "";
  if (activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT") {
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    decision("keep");
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    decision("delete");
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    enterFolder();
  } else if (event.key === " ") {
    event.preventDefault();
    elements.flashcard.classList.toggle("is-flipped");
  } else if (event.key === "1") {
    activateTab("tab-deck");
  } else if (event.key === "2") {
    openReview();
  } else if (event.key === "3") {
    openSummary();
  } else if (event.key === "4") {
    activateTab("tab-settings");
  }
}

function updateDrag(dx) {
  if (!state.pointerActive) {
    return;
  }
  const clamped = Math.max(-130, Math.min(130, dx));
  if (Math.abs(clamped) < 15) {
    clearDragState();
    return;
  }
  const degrees = clamped / 20;
  elements.flashcard.style.transform = `translateX(${clamped}px) rotate(${degrees}deg)`;
  elements.flashcard.classList.toggle("drag-left", clamped < 0);
  elements.flashcard.classList.toggle("drag-right", clamped > 0);
}

function bindSwipe() {
  elements.flashcard.addEventListener("pointerdown", (event) => {
    state.pointerStartX = event.clientX;
    state.pointerActive = true;
    state.pointerMoved = false;
    elements.flashcard.setPointerCapture(event.pointerId);
  });

  elements.flashcard.addEventListener("pointermove", (event) => {
    if (!state.pointerActive || state.pointerStartX === null) {
      return;
    }
    const delta = event.clientX - state.pointerStartX;
    if (Math.abs(delta) > 8) {
      state.pointerMoved = true;
    }
    updateDrag(delta);
  });

  const endSwipe = (event) => {
    if (!state.pointerActive || state.pointerStartX === null) {
      return;
    }
    const delta = event.clientX - state.pointerStartX;
    state.pointerStartX = null;
    state.pointerActive = false;
    elements.flashcard.releasePointerCapture(event.pointerId);
    clearDragState();
    if (Math.abs(delta) >= state.settings.swipeThreshold) {
      if (delta > 0) {
        decision("keep");
      } else {
        decision("delete");
      }
    }
  };

  elements.flashcard.addEventListener("pointerup", endSwipe);
  elements.flashcard.addEventListener("pointercancel", (event) => {
    state.pointerStartX = null;
    state.pointerActive = false;
    clearDragState();
    try {
      elements.flashcard.releasePointerCapture(event.pointerId);
    } catch (_error) {
      // no-op
    }
  });
}

function bindEvents() {
  elements.splashStartBtn.addEventListener("click", () => {
    if (!canStartFromSplash()) {
      return;
    }
    state.settings.showSplash = !elements.splashDontShow.checked;
    elements.settingShowSplash.checked = state.settings.showSplash;
    saveSettings();
    hideSplash();
  });
  elements.splashAcknowledge.addEventListener("change", syncSplashActionState);
  elements.startSessionBtn.addEventListener("click", startSession);
  elements.resumeBtn.addEventListener("click", resumeLatest);
  elements.browsePathBtn.addEventListener("click", browseForPath);
  elements.rootPathInput.addEventListener("click", browseForPath);
  elements.tutorialDismissBtn.addEventListener("click", dismissTutorial);
  elements.sortModeSelect.addEventListener("change", async () => {
    state.sortMode = elements.sortModeSelect.value;
    if (!state.sessionId) {
      state.settings.defaultSort = state.sortMode;
      elements.settingDefaultSort.value = state.sortMode;
      saveSettings();
    }
    if (state.sessionId) {
      await loadDeck({ reset: true });
    }
  });
  elements.flashcard.addEventListener("click", () => {
    if (!state.pointerMoved) {
      elements.flashcard.classList.toggle("is-flipped");
    }
  });
  elements.keepBtn.addEventListener("click", () => decision("keep"));
  elements.deleteBtn.addEventListener("click", () => decision("delete"));
  elements.enterBtn.addEventListener("click", enterFolder);
  elements.skipBtn.addEventListener("click", skipFolder);
  elements.backDeckBtn.addEventListener("click", goBackDeck);
  elements.openBtn.addEventListener("click", openInSystem);
  elements.reviewBtn.addEventListener("click", openReview);
  elements.applyBtn.addEventListener("click", applyQueue);
  elements.tabButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const tab = button.dataset.tab;
      if (tab === "tab-review") {
        await openReview();
      } else if (tab === "tab-summary") {
        await openSummary();
      } else if (tab === "tab-settings") {
        activateTab("tab-settings");
      } else {
        activateTab("tab-deck");
      }
    });
  });

  elements.settingIncludeHidden.addEventListener("change", () => {
    state.settings.includeHidden = elements.settingIncludeHidden.checked;
    saveSettings();
  });
  elements.settingConfirmApply.addEventListener("change", () => {
    state.settings.confirmApply = elements.settingConfirmApply.checked;
    saveSettings();
  });
  elements.settingAutoOpenReview.addEventListener("change", () => {
    state.settings.autoOpenReview = elements.settingAutoOpenReview.checked;
    saveSettings();
  });
  elements.settingAutoResume.addEventListener("change", () => {
    state.settings.autoResume = elements.settingAutoResume.checked;
    saveSettings();
  });
  elements.settingShowSplash.addEventListener("change", () => {
    state.settings.showSplash = elements.settingShowSplash.checked;
    elements.splashDontShow.checked = !state.settings.showSplash;
    saveSettings();
  });
  elements.settingDefaultSort.addEventListener("change", async () => {
    state.settings.defaultSort = elements.settingDefaultSort.value;
    if (!state.sessionId) {
      elements.sortModeSelect.value = state.settings.defaultSort;
    }
    saveSettings();
    if (state.sessionId) {
      await loadDeck({ reset: true });
    }
  });
  elements.settingSwipeThreshold.addEventListener("input", () => {
    state.settings.swipeThreshold = Number(elements.settingSwipeThreshold.value);
    elements.settingSwipeThresholdValue.textContent = `${state.settings.swipeThreshold}px`;
    saveSettings();
  });
  elements.settingDeckPageLimit.addEventListener("input", () => {
    state.settings.deckPageLimit = Number(elements.settingDeckPageLimit.value);
    elements.settingDeckPageLimitValue.textContent = `${state.settings.deckPageLimit}`;
    saveSettings();
  });
  elements.settingDeckPageLimit.addEventListener("change", async () => {
    if (state.sessionId) {
      await loadDeck({ reset: true });
    }
  });
  elements.themeTiles.forEach((tile) => {
    tile.addEventListener("click", () => {
      state.settings.theme = tile.dataset.theme;
      applyTheme(state.settings.theme);
      saveSettings();
    });
  });

  window.addEventListener("keydown", handleKeyboard);
  window.addEventListener("resize", positionTutorialTooltip);
  window.addEventListener("scroll", positionTutorialTooltip, true);
  bindSwipe();
}

async function boot() {
  loadSettings();
  bindEvents();
  syncSettingsUI();
  initSplash();
  clearFileWeb("Waiting for session...");
  const savedSessionId = state.settings.autoResume
    ? localStorage.getItem("decksweep_session_id")
    : null;
  if (savedSessionId) {
    try {
      const session = await api(`/api/session/${savedSessionId}`);
      await hydrateSession(session);
      setToast("Resumed saved session.");
      return;
    } catch (_error) {
      localStorage.removeItem("decksweep_session_id");
    }
  }
  elements.sortModeSelect.value = state.settings.defaultSort;
  state.sortMode = state.settings.defaultSort;
  renderCard();
}

boot();
