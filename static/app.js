"use strict";
var state = {};
state.taskId = null;
state.pollTimer = null;
state.firstFrameUrl = null;
state.demo = false;
state.model = '';
function byId(id) { return document.getElementById(id); }
var els = {};
els.prompt = byId('prompt');
els.promptCount = byId('promptCount');
els.duration = byId('duration');
els.resolution = byId('resolution');
els.ratio = byId('ratio');
els.generateAudio = byId('generateAudio');
els.watermark = byId('watermark');
els.imageInput = byId('imageInput');
els.imageUrl = byId('imageUrl');
els.dropText = byId('dropText');
els.clearImage = byId('clearImage');
els.generateBtn = byId('generateBtn');
els.btnText = byId('btnText');
els.errorBox = byId('errorBox');
els.progressWrap = byId('progressWrap');
els.progressBar = byId('progressBar');
els.progressText = byId('progressText');
els.progressPct = byId('progressPct');
els.resultHint = byId('resultHint');
els.videoWrap = byId('videoWrap');
els.player = byId('player');
els.emptyState = byId('emptyState');
els.resultActions = byId('resultActions');
els.downloadBtn = byId('downloadBtn');
els.retryBtn = byId('retryBtn');
els.taskMeta = byId('taskMeta');
els.historyGrid = byId('historyGrid');
els.refreshHistory = byId('refreshHistory');
els.modelBadge = byId('modelBadge');
els.modeBadge = byId('modeBadge');
els.footerMode = byId('footerMode');
var STATUS_LABEL = {};
STATUS_LABEL.queued = 'Dalam antrean';
STATUS_LABEL.running = 'Diproses';
STATUS_LABEL.succeeded = 'Selesai';
STATUS_LABEL.failed = 'Gagal';
STATUS_LABEL.expired = 'Kedaluwarsa';
STATUS_LABEL.cancelled = 'Dibatalkan';
function setError(msg) {
els.errorBox.textContent = msg;
if (msg) {
els.errorBox.hidden = false;
} else {
els.errorBox.hidden = true;
}
}
function setButtonLoading(loading) {
els.generateBtn.disabled = loading;
if (loading) {
els.btnText.textContent = 'Membuat video...';
} else {
els.btnText.textContent = 'Generate Video';
}
}
function setProgress(show, pct, text) {
els.progressWrap.hidden = !show;
if (show) {
if (pct) {
els.progressBar.style.width = pct + '%';
els.progressPct.textContent = pct + '%';
} else {
els.progressBar.style.width = '2%';
els.progressPct.textContent = '2%';
}
if (text) {
els.progressText.textContent = text;
}
}
}
function formatTime(ts) {
if (!ts) { return '?'; }
var d = new Date(ts * 1000);
return d.toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' });
}
async function loadConfig() {
try {
var res = await fetch('/api/config');
if (!res.ok) { return; }
var cfg = await res.json();
state.demo = cfg.demo_mode;
state.model = cfg.model;
els.modelBadge.textContent = cfg.model;
if (cfg.demo_mode) {
els.modeBadge.textContent = 'mode demo';
els.modeBadge.className = 'badge badge-demo';
els.footerMode.textContent = 'Mode demo aktif. Atur ARK_API_KEY server untuk video asli.';
} else {
els.modeBadge.textContent = 'mode live';
els.modeBadge.className = 'badge badge-live';
els.footerMode.textContent = 'Terhubung ke BytePlus ModelArk' + ' dengan ' + cfg.model + '.';
}
} catch (err) { console.warn('config gagal', err); }
}
function startPolling(taskId) {
stopPolling();
state.taskId = taskId;
checkStatus(taskId);
state.pollTimer = setInterval(function () { checkStatus(taskId); }, 3000);
}
function stopPolling() {
if (state.pollTimer) {
clearInterval(state.pollTimer);
state.pollTimer = null;
}
}
async function checkStatus(taskId) {
try {
var res = await fetch('/api/status/' + taskId);
if (!res.ok) { return; }
var data = await res.json();
if (data.status === 'succeeded') {
stopPolling();
setProgress(false);
setButtonLoading(false);
showResult(data);
loadHistory();
} else if (data.status === 'failed') {
stopPolling();
setProgress(false);
setButtonLoading(false);
var errMsg = 'Generasi gagal.';
if (data.error) {
errMsg = data.error.message;
if (!errMsg) { errMsg = data.error.code; }
}
setError(errMsg);
loadHistory();
} else if (data.status === 'expired') {
stopPolling();
setProgress(false);
setButtonLoading(false);
setError('Task kedaluwarsa.');
loadHistory();
} else if (data.status === 'cancelled') {
stopPolling();
setProgress(false);
setButtonLoading(false);
setError('Task dibatalkan.');
loadHistory();
} else {
var pct = data.progress;
if (!pct) { pct = data.status === 'queued' ? 5 : 45; }
var label = STATUS_LABEL[data.status];
if (!label) { label = data.status; }
setProgress(true, pct, label + '...');
}
} catch (err) { console.warn('poll gagal', err); }
}
function showResult(data) {
var url = data.video_url;
if (!url) {
els.resultHint.textContent = 'Task selesai tapi video kosong.';
return;
}
els.player.src = url;
els.player.hidden = false;
els.emptyState.hidden = true;
els.videoWrap.classList.remove('empty');
els.resultHint.textContent = 'Video siap diputar.';
els.downloadBtn.href = url;
els.downloadBtn.hidden = false;
els.retryBtn.hidden = false;
els.resultActions.hidden = false;
var bits = [];
if (data.resolution) { bits[bits.length] = data.resolution; }
if (data.ratio) { bits[bits.length] = data.ratio; }
if (data.duration) { bits[bits.length] = data.duration + ' dtk'; }
els.taskMeta.textContent = bits.join(' - ');
}
function replayInHistory(item){
if (item.status === 'succeeded') {
showResult(item);
window.scrollTo({ top: 0, behavior: 'smooth' });
return;
}
if (item.status === 'queued' || item.status === 'running') {
state.taskId = item.id;i
startPolling(item.id);
setProgress(true, item.progress, 'Melanjutkan pemantauan...');
} else if (item.error) {
setError(item.error.message);
if (!els.errorBox.hidden) { setError(item.error.code); }
}
}
async function handleImageFile(file){
if (!file) { return; }
if (!file.type.startsWith('image/')){ return; }
var maxBytes = 30 * 1024 * 1024;
if (file.size > maxBytes) {
setError('Gambar maksimal 30 MB.');
return;
}
setError(null);
try {
var form = new FormData();
form.append('file', file);
var res = await fetch('/api/upload', { method: 'POST', body: form });
if (!res.ok) {
var d = await res.json().catch(function () { return {}; });
var detail = d.detail;
if (!detail) { detail = 'Upload gagal.'; }
throw new Error(detail);
}
var data = await res.json();
state.firstFrameUrl = data.url;
els.imageUrl.value = '';
els.dropText.textContent = file.name;
els.clearImage.hidden = false;
} catch (err) { setError(err.message); }
}
function clearImage() {
state.firstFrameUrl = null;
els.imageUrl.value = '';
els.dropText.textContent = 'Klik / seret gambar pertama';
els.clearImage.hidden = true;
}
async function loadHistory() {
try {
var res = await fetch('/api/history');
if (!res.ok) { return; }
var items = await res.json();
renderHistory(items);
} catch (err) { console.warn('history gagal', err); }
}
function renderHistory(items){
els.historyGrid.innerHTML = '';
if (items.length === 0) {
els.historyGrid.innerHTML = '<div class="history-empty">Belum ada riwayat.</div>';
return;
}
for (var i = 0; i < items.length; i++) {
var item = items[i];
var div = document.createElement('div');
div.className = 'h-item';
var thumb = document.createElement('div');
thumb.className = 'h-thumb';
var st = document.createElement('span');
st.className = 'h-status ' + item.status;
st.textContent = STATUS_LABEL[item.status];
if (!st.textContent) { st.textContent = item.status; }
thumb.appendChild(st);
if (item.video_url && item.status === 'succeeded') {
var vid = document.createElement('video');
vid.muted = true;
vid.playsInline = true;
vid.preload = 'metadata';
vid.src = item.video_url;
thumb.appendChild(vid);
}
div.appendChild(thumb);
var body = document.createElement('div');
body.className = 'h-body';
var p = document.createElement('p');
p.className = 'h-prompt';
p.textContent = item.prompt;
if (!p.textContent) { p.textContent = '(tanpa prompt)'; }
body.appendChild(p);
var meta = document.createElement('div');
meta.className = 'h-meta';
var a = document.createElement('span');
a.textContent = formatTime(item.created_at);
var b = document.createElement('span');
b.textContent = item.resolution;
meta.appendChild(a);
meta.appendChild(b);
body.appendChild(meta);
div.appendChild(body);
div.addEventListener('click', (function (it) {
return function () { replayInHistory(it); };
}))(item);
els.historyGrid.appendChild(div);
}
}
els.prompt.addEventListener('input', function () {
els.promptCount.textContent = els.prompt.value.length + ' / 2000';
});
els.imageInput.addEventListener('change', function (e) {
var f = e.target.files;
if (f.length > 0) { handleImageFile(f[0]); }
});
els.imageUrl.addEventListener('change', function () {
var v = els.imageUrl.value.trim();
if (v.length > 0) {
state.firstFrameUrl = v;i
els.dropText.textContent = 'Gambar dari URL : ' + v.split('/').pop();
els.clearImage.hidden = false;
}
});
els.clearImage.addEventListener('click', function () { clearImage(); });
els.generateBtn.addEventListener('click', function () { handleGenerate(); });
els.refreshHistory.addEventListener('click', function () { loadHistory(); });
els.retryBtn.addEventListener('click', function () { els.prompt.value = ''; els.prompt.focus(); });
loadConfig();
loadHistory();
