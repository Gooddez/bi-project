// ── State ─────────────────────────────────────────────────────────────────────
let queryCount    = 0;
let isRecording   = false;
let recognition   = null;
let lastChartType = null;

const API = 'http://127.0.0.1:8000';

// ── Pipeline steps definition ─────────────────────────────────────────────────
const PIPE_STEPS = ['sql', 'validate', 'execute', 'chart', 'insight', 'explain'];

function setPipeStep(step, state) {
  // state: 'idle' | 'active' | 'done' | 'error'
  const dot = document.getElementById(`pipe-${step}`);
  const lbl = document.getElementById(`pipe-${step}-lbl`);
  dot.className = `pipe-dot ${state === 'idle' ? '' : state}`;
  lbl.className = `pipe-label ${state === 'idle' ? '' : state}`;
}

function resetPipeline() {
  PIPE_STEPS.forEach(s => setPipeStep(s, 'idle'));
}

async function animatePipeline(stepIndex) {
  // Mark all previous as done, current as active
  for (let i = 0; i < PIPE_STEPS.length; i++) {
    if (i < stepIndex)  setPipeStep(PIPE_STEPS[i], 'done');
    else if (i === stepIndex) setPipeStep(PIPE_STEPS[i], 'active');
    else                setPipeStep(PIPE_STEPS[i], 'idle');
  }
}

function completePipeline(success = true) {
  PIPE_STEPS.forEach(s => setPipeStep(s, success ? 'done' : 'error'));
}

// ── Submit Handler ─────────────────────────────────────────────────────────────
async function handleSubmit() {
  const input    = document.getElementById('questionInput');
  const question = input.value.trim();
  if (!question) return;

  const submitBtn = document.getElementById('submitBtn');
  submitBtn.disabled  = true;
  submitBtn.innerText = '...';
  input.disabled = true;

  resetPipeline();
  clearResults();

  // Animate pipeline steps with slight delays to give visual feedback
  animatePipeline(0);
  await delay(400);
  animatePipeline(1);

  try {
    // Show SQL + validate active during request
    animatePipeline(2);

    const res  = await fetch(`${API}/api/query`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ question }),
    });

    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();

    // Animate remaining steps
    animatePipeline(3); await delay(250);
    animatePipeline(4); await delay(250);
    animatePipeline(5); await delay(250);
    completePipeline(!data.error);

    // Render everything
    renderSQL(data.sql, data.error);
    renderTable(data.data, data.columns);
    renderChart(data.chart_spec);
    renderInsights(data.insights || []);
    renderExplanation(data.explanation);
    updateStats(data);

    queryCount++;
    const badge = document.getElementById('queryBadge');
    badge.style.display = 'flex';
    document.getElementById('queryCount').innerText = queryCount;

  } catch (err) {
    completePipeline(false);
    document.getElementById('sqlBox').innerText = `-- Error: ${err.message}`;
    document.getElementById('explanationBox').innerText = 'Failed to connect to the backend server.';
    console.error(err);
  } finally {
    submitBtn.disabled  = false;
    submitBtn.innerText = 'Analyze →';
    input.disabled = false;
    input.focus();
  }
}

// ── Render Functions ───────────────────────────────────────────────────────────

function renderSQL(sql, error) {
  const box = document.getElementById('sqlBox');
  box.innerText = sql || '-- No SQL generated';
  if (error) {
    box.innerText += `\n\n-- ⚠ Execution error: ${error}`;
  }
}

function renderExplanation(text) {
  const box = document.getElementById('explanationBox');
  box.innerText = text || 'No summary available for this query.';
}

function renderChart(chartSpecJson) {
  const container = document.getElementById('chartContainer');
  const label     = document.getElementById('chartTypeLabel');

  if (!chartSpecJson) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📊</div>
        <div class="empty-text">No visualization for this result</div>
      </div>`;
    label.innerText = '';
    document.getElementById('stat-chart').innerText = '—';
    return;
  }

  try {
    const spec = JSON.parse(chartSpecJson);

    // Extract chart type for label
    const mark = spec.mark?.type || spec.mark || 'chart';
    const typeMap = {
      bar: 'Bar', line: 'Line', area: 'Area', point: 'Scatter',
      circle: 'Bubble', arc: 'Pie', rect: 'Heatmap', boxplot: 'Box Plot',
    };
    const chartLabel = typeMap[mark] || mark;
    label.innerText = chartLabel;
    document.getElementById('stat-chart').innerText = chartLabel;

    container.innerHTML = '';
    vegaEmbed(container, spec, {
      actions: false,
      renderer: 'svg',
      config: { background: 'transparent' },
    }).catch(e => {
      container.innerHTML = `<p style="color:#dc2626;font-size:.8rem;padding:16px">Chart render error: ${e.message}</p>`;
    });

  } catch (e) {
    container.innerHTML = `<p style="color:#dc2626;font-size:.8rem;padding:16px">Chart parse error: ${e.message}</p>`;
  }
}

function renderInsights(insights) {
  const grid = document.getElementById('insightsGrid');
  document.getElementById('stat-insights').innerText = insights.length || '—';

  if (!insights.length) {
    grid.innerHTML = `
      <div class="empty-state" style="padding:20px 0">
        <div class="empty-icon">✨</div>
        <div class="empty-text">No insights found for this result</div>
      </div>`;
    return;
  }

  grid.innerHTML = insights.map((ins, i) => `
    <div class="insight-card ${ins.severity || 'low'}" style="animation-delay:${i * 0.08}s">
      <div>
        <span class="insight-type-badge">${ins.type || 'insight'}</span>
      </div>
      <div>
        <div class="insight-title">${escHtml(ins.title || '')}</div>
        <div class="insight-detail">${escHtml(ins.detail || '')}</div>
      </div>
    </div>
  `).join('');
}

function renderTable(data, columns) {
  const table = document.getElementById('dataTable');
  const label = document.getElementById('rowCountLabel');

  if (!data || !data.length) {
    table.innerHTML = `<tr><td style="padding:20px;color:var(--text-soft);font-size:.8rem;">No data returned.</td></tr>`;
    label.innerText = '';
    return;
  }

  label.innerText = `${data.length.toLocaleString()} rows`;

  const hdrs = columns || Object.keys(data[0]);
  let html = `<thead><tr>${hdrs.map(h => `<th>${escHtml(h)}</th>`).join('')}</tr></thead><tbody>`;
  data.forEach(row => {
    html += `<tr>${hdrs.map(h => `<td>${escHtml(String(row[h] ?? ''))}</td>`).join('')}</tr>`;
  });
  html += '</tbody>';
  table.innerHTML = html;
}

function updateStats(data) {
  document.getElementById('stat-rows').innerText = (data.row_count ?? 0).toLocaleString();
  document.getElementById('stat-cols').innerText = (data.columns?.length ?? 0);
}

function clearResults() {
  document.getElementById('sqlBox').innerText         = '-- Generating query...';
  document.getElementById('explanationBox').innerText  = 'Analysing results...';
  document.getElementById('insightsGrid').innerHTML    = `<div class="empty-state" style="padding:20px 0"><div class="empty-icon">✨</div><div class="empty-text">Finding insights...</div></div>`;
  document.getElementById('chartContainer').innerHTML  = `<div class="empty-state"><div class="empty-icon">📊</div><div class="empty-text">Building chart...</div></div>`;
  document.getElementById('dataTable').innerHTML       = '';
  document.getElementById('stat-rows').innerText       = '—';
  document.getElementById('stat-cols').innerText       = '—';
  document.getElementById('stat-insights').innerText   = '—';
  document.getElementById('stat-chart').innerText      = '—';
  document.getElementById('rowCountLabel').innerText   = '';
  document.getElementById('chartTypeLabel').innerText  = '';
}

// ── Voice Input (MediaRecorder → backend Gemini transcription) ─────────────────
//
// Flow:
//   1. Click 🎤  → MediaRecorder starts, button pulses red
//   2. Speak     → audio recorded locally (no external API calls)
//   3. Click ⏹   → recording stops, audio sent to /api/transcribe
//   4. Gemini transcribes → text appears in input box
//   5. User reviews, clicks Analyze manually
//

let mediaRecorder   = null;
let audioChunks     = [];

function toggleVoice() {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

async function startRecording() {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    showVoiceError('MediaRecorder not supported. Use Chrome or Edge.');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    // Pick best supported format
    const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg']
      .find(t => MediaRecorder.isTypeSupported(t)) || '';

    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      // Stop all mic tracks
      stream.getTracks().forEach(t => t.stop());
      await transcribeAndFill();
    };

    mediaRecorder.start(250); // collect chunks every 250ms
    isRecording = true;
    setVoiceUI('recording');

  } catch (err) {
    if (err.name === 'NotAllowedError') {
      showVoiceError('Microphone permission denied.');
    } else {
      showVoiceError(`Mic error: ${err.message}`);
    }
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    isRecording = false;
    setVoiceUI('transcribing');
    mediaRecorder.stop(); // triggers onstop → transcribeAndFill
  }
}

async function transcribeAndFill() {
  if (!audioChunks.length) {
    setVoiceUI('idle');
    return;
  }

  const mimeType = mediaRecorder?.mimeType || 'audio/webm';
  const blob      = new Blob(audioChunks, { type: mimeType });
  audioChunks     = [];

  try {
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');

    const res = await fetch(`${API}/api/transcribe`, {
      method: 'POST',
      body:   formData,
    });

    if (!res.ok) throw new Error(`Transcription failed (${res.status})`);
    const { transcript, error } = await res.json();

    if (error)      throw new Error(error);
    if (!transcript) throw new Error('Empty transcript returned');

    const input = document.getElementById('questionInput');
    input.value = transcript;
    input.focus();
    input.setSelectionRange(transcript.length, transcript.length);

  } catch (err) {
    console.error('Transcription error:', err);
    showVoiceError(err.message);
  } finally {
    setVoiceUI('idle');
  }
}

function setVoiceUI(state) {
  const btn   = document.getElementById('voiceBtn');
  const label = document.getElementById('voiceBtnLabel');
  const ind   = document.getElementById('voiceIndicator');
  const indTxt = document.getElementById('voiceIndicatorText');

  btn.classList.remove('recording', 'transcribing');

  if (state === 'recording') {
    btn.classList.add('recording');
    btn.title          = 'Click to stop recording';
    label.innerText    = '⏹';
    ind.classList.add('show');
    if (indTxt) indTxt.innerText = 'Recording — click ⏹ to stop';
  } else if (state === 'transcribing') {
    btn.classList.add('transcribing');
    btn.title          = 'Transcribing...';
    label.innerText    = '⏳';
    ind.classList.add('show');
    if (indTxt) indTxt.innerText = 'Transcribing...';
  } else {
    btn.title          = 'Click to start voice input';
    label.innerText    = '🎤';
    ind.classList.remove('show');
  }
}

function showVoiceError(msg) {
  const ind    = document.getElementById('voiceIndicator');
  const indTxt = document.getElementById('voiceIndicatorText');
  if (indTxt) indTxt.innerText = `⚠ ${msg}`;
  ind.classList.add('show');
  setTimeout(() => {
    ind.classList.remove('show');
    if (indTxt) indTxt.innerText = 'Recording — click ⏹ to stop';
  }, 3500);
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Keyboard ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('questionInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) handleSubmit();
  });
});