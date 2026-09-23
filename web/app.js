const form = document.getElementById("extractForm");
const notebookInput = document.getElementById("notebookName");
const lectureInput = document.getElementById("lectureName");
const bookInput = document.getElementById("bookName");
const contentTypeInput = document.getElementById("contentType");
const profileInput = document.getElementById("profileName");
const startButton = document.getElementById("startButton");
const stopButton = document.getElementById("stopButton");
const statusBadge = document.getElementById("statusBadge");
const activityDot = document.getElementById("activityDot");
const notice = document.getElementById("notice");
const log = document.getElementById("log");
const emptyLog = document.getElementById("emptyLog");
const files = document.getElementById("files");
const refreshFiles = document.getElementById("refreshFiles");

let lastLogId = 0;
let pollTimer = null;

const statusLabels = {
  idle: "جاهز",
  starting: "جارٍ البدء",
  running: "فتح المتصفح",
  waiting_for_login: "بانتظار تسجيل الدخول",
  extracting: "جارٍ الاستخراج",
  extracting_sections: "استخراج الأقسام",
  finalizing: "حفظ الملفات",
  stopping: "جارٍ الإيقاف",
  stopped: "متوقف",
  completed: "اكتمل",
  failed: "فشل",
};

const activeStatuses = new Set([
  "starting",
  "running",
  "waiting_for_login",
  "extracting",
  "extracting_sections",
  "finalizing",
  "stopping",
]);

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "تعذر تنفيذ الطلب.");
  }
  return data;
}

function setNotice(message = "") {
  notice.textContent = message;
  notice.classList.toggle("hidden", !message);
}

function renderStatus(job) {
  const status = job.status || "idle";
  statusBadge.textContent = statusLabels[status] || status;
  statusBadge.className = "status-badge";
  activityDot.className = "activity-dot";

  if (activeStatuses.has(status)) {
    statusBadge.classList.add(
      status === "waiting_for_login" ? "waiting" : "active"
    );
    activityDot.classList.add("active");
  } else if (status === "completed") {
    statusBadge.classList.add("success");
  } else if (status === "failed" || status === "stopped") {
    statusBadge.classList.add("failed");
  } else {
    statusBadge.classList.add("idle");
  }

  startButton.disabled = !job.can_start;
  stopButton.disabled = !job.can_stop;
  notebookInput.disabled = !job.can_start;
  lectureInput.disabled = !job.can_start;
  bookInput.disabled = !job.can_start;
  contentTypeInput.disabled = !job.can_start;
  profileInput.disabled = !job.can_start;
}

function appendLogs(entries) {
  if (!entries || !entries.length) return;
  emptyLog.classList.add("hidden");
  log.classList.remove("hidden");

  for (const entry of entries) {
    const row = document.createElement("div");
    row.className = "log-line";

    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = entry.time;

    const message = document.createElement("span");
    message.className = "log-message";
    message.textContent = entry.message;

    row.append(time, message);
    log.append(row);
    lastLogId = Math.max(lastLogId, entry.id);
  }
  log.scrollTop = log.scrollHeight;
}

function formatSize(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function renderFiles(items) {
  files.replaceChildren();
  if (!items || !items.length) {
    const empty = document.createElement("div");
    empty.className = "files-empty";
    empty.textContent = "لا توجد ملفات نهائية بعد.";
    files.append(empty);
    return;
  }

  for (const item of items.slice(0, 9)) {
    const link = document.createElement("a");
    link.className = "file-item";
    link.href = item.download_url;

    const type = document.createElement("span");
    type.className = "file-type";
    type.textContent = item.extension;

    const details = document.createElement("span");
    details.className = "file-details";

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = item.name;
    name.title = item.name;

    const meta = document.createElement("span");
    meta.className = "file-meta";
    meta.textContent = formatSize(item.size);

    details.append(name, meta);
    link.append(type, details);
    files.append(link);
  }
}

async function poll() {
  try {
    const job = await api(`/api/jobs/current?after=${lastLogId}`);
    renderStatus(job);
    appendLogs(job.logs);
    renderFiles(job.files);
  } catch (error) {
    setNotice(error.message);
  } finally {
    pollTimer = window.setTimeout(poll, 1200);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setNotice();
  log.replaceChildren();
  lastLogId = 0;
  emptyLog.classList.remove("hidden");
  log.classList.add("hidden");

  try {
    const job = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        profile_name: profileInput.value,
        notebook_name: notebookInput.value,
        lecture_name: lectureInput.value,
        book_name: bookInput.value,
        content_type: contentTypeInput.value,
      }),
    });
    renderStatus(job);
    appendLogs(job.logs);
  } catch (error) {
    setNotice(error.message);
  }
});

stopButton.addEventListener("click", async () => {
  setNotice();
  try {
    const job = await api("/api/jobs/current/stop", {
      method: "POST",
      body: "{}",
    });
    renderStatus(job);
    appendLogs(job.logs);
  } catch (error) {
    setNotice(error.message);
  }
});

refreshFiles.addEventListener("click", async () => {
  try {
    const data = await api("/api/files");
    renderFiles(data.files);
  } catch (error) {
    setNotice(error.message);
  }
});

async function initialize() {
  try {
    const data = await api("/api/state");
    profileInput.value = data.defaults.profile_name || "account2";
    notebookInput.value = data.defaults.notebook_name || "";
    contentTypeInput.value = data.defaults.content_type || "arabic";
    renderStatus(data.job);
    appendLogs(data.job.logs);
    lastLogId = data.job.last_log_id || lastLogId;
    renderFiles(data.job.files);
  } catch (error) {
    setNotice(error.message);
  }
  poll();
}

initialize();
