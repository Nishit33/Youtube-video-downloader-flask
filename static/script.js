const urlInput = document.getElementById("url");
const checkBtn = document.getElementById("checkBtn");
const optionsBox = document.getElementById("options");
const qualitySelect = document.getElementById("quality");
const downloadBtn = document.getElementById("downloadBtn");
const progressBox = document.getElementById("progressBox");
const bar = document.getElementById("bar");
const percentText = document.getElementById("percent");
const detailsText = document.getElementById("details");
const statusText = document.getElementById("status");

function setStatus(message, type = "") {
  statusText.textContent = message;
  statusText.className = "status " + type;
}

function setProgress(percent, details = "") {
  bar.style.width = percent + "%";
  percentText.textContent = Math.floor(percent) + "%";
  detailsText.textContent = details;
}

async function postJSON(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

// ---- Step 1: check the link and load the real qualities ----
async function checkLink() {
  const url = urlInput.value.trim();
  if (!url) {
    setStatus("Please paste a YouTube link first.", "error");
    return;
  }

  checkBtn.disabled = true;
  checkBtn.textContent = "Checking...";
  optionsBox.classList.add("hidden");
  progressBox.classList.add("hidden");
  setStatus("Reading video details...");

  try {
    const info = await postJSON("/api/info", { url });

    document.getElementById("thumb").src = info.thumbnail;
    document.getElementById("title").textContent = info.title;
    document.getElementById("meta").textContent =
      [info.channel, info.duration].filter(Boolean).join(" • ");

    qualitySelect.innerHTML = "";
    info.qualities.forEach((q) => {
      const option = document.createElement("option");
      option.value = q.value;
      option.textContent = q.size ? `${q.label}  (${q.size})` : q.label;
      qualitySelect.appendChild(option);
    });

    optionsBox.classList.remove("hidden");
    setStatus("");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    checkBtn.disabled = false;
    checkBtn.textContent = "Check";
  }
}

// ---- Step 2: start the download and show live progress ----
async function startDownload() {
  downloadBtn.disabled = true;
  checkBtn.disabled = true;
  progressBox.classList.remove("hidden");
  setProgress(0, "Starting...");
  setStatus("");

  try {
    const { job_id } = await postJSON("/api/download", {
      url: urlInput.value.trim(),
      quality: qualitySelect.value,
    });
    pollProgress(job_id);
  } catch (error) {
    setStatus(error.message, "error");
    finish();
  }
}

async function pollProgress(jobId) {
  try {
    const response = await fetch(`/api/progress/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.error);

    if (job.status === "error") {
      throw new Error(job.error || "Download failed.");
    }

    if (job.status === "done") {
      setProgress(100, "Saving to your device...");
      window.location.href = `/api/file/${jobId}`; // browser saves the file
      setStatus(`Download complete! Quality: ${job.quality}`, "success");
      finish();
      return;
    }

    if (job.status === "processing") {
      setProgress(99, "Merging video and audio...");
    } else {
      const parts = [job.speed, job.eta != null ? `${job.eta}s left` : ""];
      setProgress(job.percent, parts.filter(Boolean).join(" • "));
    }
    setTimeout(() => pollProgress(jobId), 300);
  } catch (error) {
    setStatus(error.message, "error");
    progressBox.classList.add("hidden");
    finish();
  }
}

function finish() {
  downloadBtn.disabled = false;
  checkBtn.disabled = false;
}

checkBtn.addEventListener("click", checkLink);
urlInput.addEventListener("keydown", (e) => e.key === "Enter" && checkLink());
downloadBtn.addEventListener("click", startDownload);