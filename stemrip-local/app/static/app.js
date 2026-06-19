const form = document.querySelector('#jobForm');
const fileInput = document.querySelector('#audioFile');
const fileName = document.querySelector('#fileName');
const dropzone = document.querySelector('#dropzone');
const submitButton = document.querySelector('#submitButton');
const jobPanel = document.querySelector('#jobPanel');
const jobTitle = document.querySelector('#jobTitle');
const statusBadge = document.querySelector('#statusBadge');
const progressBar = document.querySelector('#progressBar');
const jobMeta = document.querySelector('#jobMeta');
const downloads = document.querySelector('#downloads');
const logs = document.querySelector('#logs');

let pollTimer = null;

function setFileLabel() {
  const file = fileInput.files?.[0];
  fileName.textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : 'WAV, MP3, FLAC, M4A, AAC, OGG, OPUS, AIFF, WMA';
}

function setProgress(status) {
  const width = { queued: 12, running: 55, complete: 100, failed: 100 }[status] ?? 5;
  progressBar.style.width = `${width}%`;
  progressBar.dataset.status = status;
}

function renderJob(job) {
  jobPanel.classList.remove('hidden');
  jobTitle.textContent = job.original_name || job.id;
  statusBadge.textContent = job.status;
  statusBadge.dataset.status = job.status;
  setProgress(job.status);

  const elapsed = job.started_at ? Math.max(0, Math.round(((job.finished_at || Date.now() / 1000) - job.started_at))) : 0;
  jobMeta.textContent = `Mode: ${job.mode} · Model: ${job.model} · Shifts: ${job.shifts} · ${elapsed}s elapsed`;
  logs.textContent = (job.logs || []).join('\n');
  logs.scrollTop = logs.scrollHeight;

  downloads.innerHTML = '';
  if (job.status === 'complete') {
    if (job.zip_url) {
      const zip = document.createElement('a');
      zip.href = job.zip_url;
      zip.className = 'download download-main';
      zip.textContent = 'Download all stems ZIP';
      downloads.appendChild(zip);
    }
    for (const file of job.files || []) {
      const link = document.createElement('a');
      link.href = file.download_url;
      link.className = 'download';
      link.textContent = file.name;
      downloads.appendChild(link);
    }
  }

  if (job.status === 'failed') {
    const error = document.createElement('p');
    error.className = 'error';
    error.textContent = job.error || 'Separation failed.';
    downloads.appendChild(error);
  }
}

async function poll(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) throw new Error('Could not fetch job status');
  const job = await response.json();
  renderJob(job);
  if (job.status === 'complete' || job.status === 'failed') {
    clearInterval(pollTimer);
    pollTimer = null;
    submitButton.disabled = false;
    submitButton.textContent = 'Separate stems';
  }
}

fileInput.addEventListener('change', setFileLabel);

for (const eventName of ['dragenter', 'dragover']) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add('dragging');
  });
}

for (const eventName of ['dragleave', 'drop']) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove('dragging');
  });
}

dropzone.addEventListener('drop', (event) => {
  const [file] = event.dataTransfer.files;
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  setFileLabel();
});

document.querySelector('#mode').addEventListener('change', (event) => {
  if (event.target.value === 'six_stems') {
    document.querySelector('#model').value = 'htdemucs_6s';
  }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) return;

  submitButton.disabled = true;
  submitButton.textContent = 'Uploading...';
  downloads.innerHTML = '';
  logs.textContent = '';

  const formData = new FormData(form);
  try {
    const response = await fetch('/api/jobs', { method: 'POST', body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Upload failed');
    renderJob(payload);
    submitButton.textContent = 'Separating...';
    clearInterval(pollTimer);
    pollTimer = setInterval(() => poll(payload.id).catch(console.error), 2000);
  } catch (error) {
    jobPanel.classList.remove('hidden');
    statusBadge.textContent = 'failed';
    statusBadge.dataset.status = 'failed';
    setProgress('failed');
    logs.textContent = error.message;
    submitButton.disabled = false;
    submitButton.textContent = 'Separate stems';
  }
});
