/* ────────────────────────────────────────────────────────────
   AI Job Hunter — app.js
   Dual-tab dashboard: Live (24hr) + Archive + Not Match status
   ──────────────────────────────────────────────────────────── */

const API = '';
let currentTab = 'live';
let liveJobs = [];
let archiveJobs = [];
let searchTimers = {};
let autoRefreshTimer = null;
let currentModalJobId = null;

// ── Status helpers ──────────────────────────────────────────
const STATUS_OPTIONS = [
  'Not Applied',
  'Applied',
  'Interview Scheduled',
  'Offer Received',
  'Rejected',
  'Not Match',
];

const STATUS_CLASS = {
  'Not Applied': 'status-not-applied',
  'Applied': 'status-applied',
  'Interview Scheduled': 'status-interview',
  'Offer Received': 'status-offer',
  'Rejected': 'status-rejected',
  'Not Match': 'status-not-match',
};

const SOURCE_LABEL = {
  'linkedin_jobs': '💼 LinkedIn Jobs',
  'linkedin_post': '📢 LinkedIn Post',
  'career_page': '🏢 Career Page',
};

// ── Init ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadLiveJobs();
  loadArchiveJobs();
  // Auto-refresh live every 30 minutes
  autoRefreshTimer = setInterval(() => {
    if (currentTab === 'live') {
      showToast('Auto-refreshing live jobs...', 'info');
      loadLiveJobs();
    }
    loadStats();
  }, 30 * 60 * 1000);
});

// ── Tab Switcher ────────────────────────────────────────────
function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tab-live').classList.toggle('active', tab === 'live');
  document.getElementById('tab-live').classList.toggle('hidden', tab !== 'live');
  document.getElementById('tab-archive').classList.toggle('active', tab === 'archive');
  document.getElementById('tab-archive').classList.toggle('hidden', tab !== 'archive');
  document.getElementById('tab-live-btn').classList.toggle('active', tab === 'live');
  document.getElementById('tab-archive-btn').classList.toggle('active', tab === 'archive');

  const refreshInfo = document.getElementById('refresh-info');
  if (tab === 'live') {
    refreshInfo.textContent = 'Auto-refreshes every 30 min';
  } else {
    refreshInfo.textContent = 'Tracking older applications';
  }
}

// ── Stats ────────────────────────────────────────────────────
async function loadStats() {
  try {
    const res = await fetch(`${API}/api/stats`);
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('stat-live-val').textContent = data.live_jobs ?? '—';
    document.getElementById('stat-total-val').textContent = data.total_jobs ?? '—';
    document.getElementById('stat-applied-val').textContent = data.applied ?? '—';
    document.getElementById('stat-interview-val').textContent = data.interviews ?? '—';
    document.getElementById('stat-offer-val').textContent = data.offer_received ?? '—';
    document.getElementById('stat-rejected-val').textContent = data.rejected ?? '—';
    document.getElementById('stat-notmatch-val').textContent = data.not_match ?? '—';
    document.getElementById('stat-ats-val').textContent = `${data.average_ats_score ?? '—'}%`;
  } catch (e) {
    console.error('Stats load failed:', e);
  }
}

// ── Live Jobs ────────────────────────────────────────────────
async function loadLiveJobs() {
  const search = document.getElementById('live-search').value.trim();
  const source = document.getElementById('live-source-filter').value;
  const atsFilter = document.getElementById('live-ats-filter').value;

  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (source !== 'all') params.set('source', source);

  try {
    const res = await fetch(`${API}/api/jobs/live?${params}`);
    if (!res.ok) throw new Error('Failed to fetch live jobs');
    let jobs = await res.json();

    // Client-side ATS filter
    if (atsFilter === 'high') jobs = jobs.filter(j => j.ats_score >= 80);
    else if (atsFilter === 'medium') jobs = jobs.filter(j => j.ats_score >= 50 && j.ats_score < 80);
    else if (atsFilter === 'low') jobs = jobs.filter(j => !j.ats_score || j.ats_score < 50);

    liveJobs = jobs;
    document.getElementById('live-badge').textContent = jobs.length;
    renderLiveJobs(jobs);
  } catch (e) {
    document.getElementById('live-jobs-grid').innerHTML = `<div class="empty-state">⚠️ Could not load live jobs. Is the API running?</div>`;
  }
}

function renderLiveJobs(jobs) {
  const grid = document.getElementById('live-jobs-grid');
  if (!jobs.length) {
    grid.innerHTML = `<div class="empty-state">😴 No live jobs found in the last 24 hours.<br><small>Click "Refresh Jobs" to scrape the latest listings.</small></div>`;
    return;
  }
  const now = Date.now();
  grid.innerHTML = jobs.map(job => {
    const isNew = (now - new Date(job.created_at).getTime()) < 6 * 60 * 60 * 1000;
    const atsClass = atsScoreClass(job.ats_score);
    const atsLabel = job.ats_score ? `${job.ats_score}%` : '—';
    const sourceLabel = SOURCE_LABEL[job.source_type] || job.platform || '—';
    return `
    <div class="job-card ${isNew ? 'new-tag' : ''} ${job.status === 'Not Match' ? 'not-match' : ''}"
         onclick="openJobModal(${job.id}, 'live')">
      <div class="card-top">
        <div class="card-title">${escHtml(job.title)}</div>
        <div class="ats-badge ${atsClass}">${atsLabel}</div>
      </div>
      <div class="card-company">🏢 ${escHtml(job.company_name)}</div>
      <div class="card-meta">
        <span class="meta-chip">📍 ${escHtml(job.location || 'India')}</span>
        <span class="meta-chip">🕐 ${timeAgo(job.created_at)}</span>
        ${job.recruiter_email ? `<span class="meta-chip">📧 ${escHtml(job.recruiter_email)}</span>` : ''}
      </div>
      <div class="card-bottom">
        <span class="status-badge ${STATUS_CLASS[job.status] || 'status-not-applied'}">${job.status}</span>
        <span class="source-chip">${sourceLabel}</span>
      </div>
    </div>`;
  }).join('');
}

// ── Archive Jobs ─────────────────────────────────────────────
async function loadArchiveJobs() {
  const search = document.getElementById('archive-search').value.trim();
  const status = document.getElementById('archive-status-filter').value;
  const sort = document.getElementById('archive-sort').value;

  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (status !== 'all') params.set('status', status);

  try {
    const res = await fetch(`${API}/api/jobs/archive?${params}`);
    if (!res.ok) throw new Error('Failed to fetch archive jobs');
    let jobs = await res.json();

    // Client-side sort
    if (sort === 'date') jobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    else if (sort === 'company') jobs.sort((a, b) => a.company_name.localeCompare(b.company_name));
    // default: ats_score (already sorted by server)

    archiveJobs = jobs;
    document.getElementById('archive-badge').textContent = jobs.length;
    renderArchiveJobs(jobs);
  } catch (e) {
    document.getElementById('archive-jobs-grid').innerHTML = `<div class="empty-state">⚠️ Could not load archived jobs.</div>`;
  }
}

function renderArchiveJobs(jobs) {
  const grid = document.getElementById('archive-jobs-grid');
  if (!jobs.length) {
    grid.innerHTML = `<div class="empty-state">📂 No archived jobs yet.<br><small>Jobs older than 24 hours appear here for tracking.</small></div>`;
    return;
  }
  grid.innerHTML = jobs.map(job => {
    const atsClass = atsScoreClass(job.ats_score);
    const atsLabel = job.ats_score ? `${job.ats_score}%` : '—';
    const sourceLabel = SOURCE_LABEL[job.source_type] || job.platform || '—';
    return `
    <div class="job-card ${job.status === 'Not Match' ? 'not-match' : ''}"
         onclick="openJobModal(${job.id}, 'archive')">
      <div class="card-top">
        <div class="card-title">${escHtml(job.title)}</div>
        <div class="ats-badge ${atsClass}">${atsLabel}</div>
      </div>
      <div class="card-company">🏢 ${escHtml(job.company_name)}</div>
      <div class="card-meta">
        <span class="meta-chip">📍 ${escHtml(job.location || 'India')}</span>
        <span class="meta-chip">📅 ${formatDate(job.created_at)}</span>
        ${job.date_applied ? `<span class="meta-chip">✅ Applied: ${formatDate(job.date_applied)}</span>` : ''}
        ${job.recruiter_email ? `<span class="meta-chip">📧 ${escHtml(job.recruiter_email)}</span>` : ''}
      </div>
      <div class="card-bottom">
        <span class="status-badge ${STATUS_CLASS[job.status] || 'status-not-applied'}">${job.status}</span>
        <span class="source-chip">${sourceLabel}</span>
      </div>
    </div>`;
  }).join('');
}

// ── Modal ────────────────────────────────────────────────────
async function openJobModal(jobId, source) {
  currentModalJobId = jobId;
  document.getElementById('job-modal').classList.remove('hidden');
  document.getElementById('modal-content').innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Loading job details...</p></div>`;

  try {
    const jobs = source === 'live' ? liveJobs : archiveJobs;
    const job = jobs.find(j => j.id === jobId);
    if (!job) throw new Error('Job not found');

    const atsClass = atsScoreClass(job.ats_score);
    const sourceLabel = SOURCE_LABEL[job.source_type] || job.platform || '—';

    const statusOptions = STATUS_OPTIONS.map(s =>
      `<option value="${s}" ${job.status === s ? 'selected' : ''}>${s}</option>`
    ).join('');

    document.getElementById('modal-content').innerHTML = `
      <div class="modal-title">${escHtml(job.title)}</div>
      <div class="modal-company">🏢 ${escHtml(job.company_name)}</div>
      <div class="modal-row">
        <span class="ats-badge ${atsClass}">ATS: ${job.ats_score ? job.ats_score + '%' : '—'}</span>
        <span class="meta-chip">📍 ${escHtml(job.location || 'India')}</span>
        <span class="meta-chip">🕐 ${timeAgo(job.created_at)}</span>
        <span class="source-chip">${sourceLabel}</span>
        ${job.experience ? `<span class="meta-chip">👤 ${escHtml(job.experience)}</span>` : ''}
      </div>
      ${job.recruiter_email ? `<div style="margin-bottom:0.8rem;font-size:0.82rem;">📧 Recruiter: <a href="mailto:${escHtml(job.recruiter_email)}" style="color:var(--accent2)">${escHtml(job.recruiter_email)}</a></div>` : ''}
      ${job.missing_skills ? `<div style="margin-bottom:0.8rem;font-size:0.8rem;color:var(--yellow);">⚠️ Missing skills: ${escHtml(job.missing_skills)}</div>` : ''}
      ${job.description ? `<div class="modal-desc">${escHtml(job.description)}</div>` : ''}
      <div class="modal-actions">
        ${job.apply_url ? `<a href="${escHtml(job.apply_url)}" target="_blank" rel="noopener" class="btn btn-primary">🚀 Apply Now</a>` : ''}
        <button class="btn btn-tailor" onclick="tailorResume(${job.id})">🎯 Tailor Resume</button>
        <select id="modal-status-select" class="status-select" onchange="updateStatus(${job.id}, this.value)">
          ${statusOptions}
        </select>
        <button class="btn btn-outline" onclick="saveNotes(${job.id})">💾 Save Notes</button>
      </div>
      <textarea class="notes-input" id="modal-notes" placeholder="Add your notes, interview date, contact info...">${escHtml(job.notes || '')}</textarea>
      <div id="tailor-result-panel"></div>
    `;
  } catch (e) {
    document.getElementById('modal-content').innerHTML = `<div class="empty-state">⚠️ Could not load job details.</div>`;
  }
}

// ── Resume Tailoring ────────────────────────────────────────
async function tailorResume(jobId) {
  const panel = document.getElementById('tailor-result-panel');
  if (!panel) return;
  panel.innerHTML = `
    <div class="tailor-panel">
      <div class="tailor-loading">
        <div class="spinner" style="width:24px;height:24px;"></div>
        <span>🤖 AI is analyzing job description vs your resume... (30-60 seconds)</span>
      </div>
    </div>`;
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const res = await fetch(`${API}/api/jobs/${jobId}/tailor`, { method: 'POST' });
    if (!res.ok) throw new Error('Tailoring failed');
    const data = await res.json();
    renderTailoringSuggestions(panel, data.suggestions);
  } catch (e) {
    panel.innerHTML = `<div class="tailor-panel"><div style="color:var(--red);font-size:0.85rem;">⚠️ Tailoring failed. Make sure your resume is uploaded and try again.</div></div>`;
  }
}

function renderTailoringSuggestions(panel, s) {
  if (!s) { panel.innerHTML = ''; return; }

  const missingKw = (s.missing_keywords || []).map(k =>
    `<span class="keyword-chip missing">${escHtml(k)}</span>`).join('');
  const skillsToAdd = (s.skills_to_add || []).map(k =>
    `<span class="keyword-chip missing">${escHtml(k)}</span>`).join('');
  const skillsHighlight = (s.skills_to_highlight || []).map(k =>
    `<span class="keyword-chip">${escHtml(k)}</span>`).join('');
  const quickWins = (s.quick_wins || []).map(w =>
    `<li>${escHtml(w)}</li>`).join('');

  panel.innerHTML = `
  <div class="tailor-panel">
    <div style="font-size:0.9rem;font-weight:700;margin-bottom:1rem;">🎯 Resume Tailoring Report — ${escHtml(s.job_title || '')} @ ${escHtml(s.company_name || '')}</div>

    <div class="tailor-score-row">
      <div class="tailor-score-box score-current">
        <div class="score-val">${s.current_ats_score || '—'}%</div>
        <div class="score-label">Current ATS Score</div>
      </div>
      <div class="score-arrow">→</div>
      <div class="tailor-score-box score-potential">
        <div class="score-val">${s.potential_ats_score || '—'}%</div>
        <div class="score-label">After Tailoring</div>
      </div>
    </div>

    ${missingKw ? `
    <div class="tailor-section">
      <div class="tailor-section-title">❌ Missing Keywords (Add to Resume)</div>
      <div class="keyword-chips">${missingKw}</div>
    </div>` : ''}

    ${skillsToAdd ? `
    <div class="tailor-section">
      <div class="tailor-section-title">➕ Skills to Add</div>
      <div class="keyword-chips">${skillsToAdd}</div>
    </div>` : ''}

    ${skillsHighlight ? `
    <div class="tailor-section">
      <div class="tailor-section-title">⭐ Skills You Have — Highlight These</div>
      <div class="keyword-chips">${skillsHighlight}</div>
    </div>` : ''}

    ${s.suggested_summary ? `
    <div class="tailor-section">
      <div class="tailor-section-title">📝 Suggested Resume Summary</div>
      <div class="tailor-summary-box">${escHtml(s.suggested_summary)}</div>
    </div>` : ''}

    ${s.project_suggestions ? `
    <div class="tailor-section">
      <div class="tailor-section-title">🔨 Projects Section Tip</div>
      <div style="font-size:0.82rem;color:var(--text-muted);line-height:1.6;">${escHtml(s.project_suggestions)}</div>
    </div>` : ''}

    ${quickWins ? `
    <div class="tailor-section">
      <div class="tailor-section-title">⚡ Quick Wins (Highest Impact Changes)</div>
      <ul class="quick-wins-list">${quickWins}</ul>
    </div>` : ''}

    ${s.cover_letter_hint ? `
    <div class="tailor-section">
      <div class="tailor-section-title">✉️ Cover Letter / Email Hint</div>
      <div class="cover-letter-hint">${escHtml(s.cover_letter_hint)}</div>
    </div>` : ''}
  </div>`;

  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeJobModal() {
  document.getElementById('job-modal').classList.add('hidden');
  currentModalJobId = null;
}

function closeModal(e) {
  if (e.target === document.getElementById('job-modal')) closeJobModal();
}

// ── Update Status ────────────────────────────────────────────
async function updateStatus(jobId, newStatus) {
  try {
    const res = await fetch(`${API}/api/jobs/${jobId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) throw new Error('Failed');
    showToast(`Status updated to "${newStatus}"`, 'success');
    // Update in-memory
    [liveJobs, archiveJobs].forEach(arr => {
      const j = arr.find(x => x.id === jobId);
      if (j) j.status = newStatus;
    });
    renderLiveJobs(liveJobs);
    renderArchiveJobs(archiveJobs);
    loadStats();
  } catch (e) {
    showToast('Failed to update status', 'error');
  }
}

// ── Save Notes ───────────────────────────────────────────────
async function saveNotes(jobId) {
  const notes = document.getElementById('modal-notes').value;
  try {
    const res = await fetch(`${API}/api/jobs/${jobId}/notes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes }),
    });
    if (!res.ok) throw new Error('Failed');
    showToast('Notes saved!', 'success');
    [liveJobs, archiveJobs].forEach(arr => {
      const j = arr.find(x => x.id === jobId);
      if (j) j.notes = notes;
    });
  } catch (e) {
    showToast('Failed to save notes', 'error');
  }
}

// ── Run Pipeline ─────────────────────────────────────────────
async function runPipeline() {
  const btn = document.getElementById('btn-run-pipeline');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-icon">⏳</span> Running...';
  showToast('Pipeline started — scraping LinkedIn + career pages...', 'info');

  try {
    const res = await fetch(`${API}/pipeline/run`, { method: 'POST' });
    if (!res.ok) throw new Error('Pipeline failed');
    const data = await res.json();
    const scraped = data?.steps?.scrape_jobs?.jobs_scraped ?? 0;
    const matched = data?.steps?.ats_match?.jobs_matched ?? 0;
    showToast(`✅ Done! ${scraped} new jobs scraped, ${matched} AI-matched.`, 'success');
    loadStats();
    loadLiveJobs();
  } catch (e) {
    showToast('Pipeline failed. Check API logs.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">⚡</span> Refresh Jobs';
  }
}

// ── Download Report ──────────────────────────────────────────
function downloadReport() {
  window.open(`${API}/api/reports/download`, '_blank');
}

// ── Upload Resume ────────────────────────────────────────────
async function uploadResume(input) {
  if (!input.files.length) return;
  const formData = new FormData();
  formData.append('file', input.files[0]);
  showToast('Uploading resume...', 'info');
  try {
    const res = await fetch(`${API}/api/resume/upload`, { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Upload failed');
    const data = await res.json();
    showToast(`Resume parsed (${data.parsed_version})`, 'success');
  } catch (e) {
    showToast('Resume upload failed', 'error');
  }
  input.value = '';
}

// ── Search Debounce ──────────────────────────────────────────
function debounceSearch(tab) {
  clearTimeout(searchTimers[tab]);
  searchTimers[tab] = setTimeout(() => {
    if (tab === 'live') loadLiveJobs();
    else loadArchiveJobs();
  }, 350);
}

// ── Utility ──────────────────────────────────────────────────
function atsScoreClass(score) {
  if (!score) return 'ats-none';
  if (score >= 80) return 'ats-high';
  if (score >= 50) return 'ats-medium';
  return 'ats-low';
}

function timeAgo(dateStr) {
  if (!dateStr) return '—';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type}`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.className = 'toast hidden'; }, 4000);
}
