const eur = n => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format(Number(n||0));
async function json(url, opts){ const r = await fetch(url, opts); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function checkStatus(){ const s = await json('/api/status'); document.getElementById('ollama').textContent = s.ok ? `Ollama OK: ${s.model}` : `Ollama offline: ${s.error}`; }
function setUploadStatus(message, type = 'info') {
  const el = document.getElementById('uploadResult');
  el.className = type;
  el.textContent = message;
}
function formatUploadResult(data) {
  const lines = [
    `Processed ${data.fileName || 'file'} (${data.sourceType || 'unknown'})`,
    `OCR text: ${data.ocrChars || 0} characters`,
    `Saved: ${data.inserted || 0} transactions`,
    `Skipped duplicates/invalid rows: ${data.skipped || 0}`
  ];
  if (data.aiOk) {
    lines.push('AI extraction: OK');
  } else {
    lines.push('AI extraction: unavailable, used OCR fallback');
    if (data.aiError) lines.push(`AI detail: ${data.aiError}`);
  }
  return lines.join('\n');
}
async function uploadFile(){
  const f = document.getElementById('file').files[0]; if(!f) return alert('Select a file first');
  const fd = new FormData(); fd.append('file', f); fd.append('year', document.getElementById('year').value || '2026');
  setUploadStatus('Scanning OCR/text, sending to local Ollama, saving to SQLite...');
  try {
    const data = await json('/api/upload', { method:'POST', body: fd });
    setUploadStatus(formatUploadResult(data), data.aiOk ? 'success' : 'warning');
    await loadAll();
  } catch(e) {
    setUploadStatus(e.message, 'error');
  }
}
async function loadAll(){ await Promise.all([loadSummary(), loadTransactions(), loadForecast()]); }
async function loadSummary(){
  const m = document.getElementById('month').value; const s = await json('/api/summary?month='+encodeURIComponent(m));
  income.textContent = eur(s.totals.income); expenses.textContent = eur(s.totals.expenses); net.textContent = eur(s.totals.net);
  fill('catTable', s.byCat.map(r=>[r.category, r.count, eur(r.total)]));
  fill('shopTable', s.byShop.map(r=>[r.merchant, r.category, eur(r.total)]));
}
async function loadTransactions(){ const m = document.getElementById('month').value; const rows = await json('/api/transactions?month='+encodeURIComponent(m)); fill('txTable', rows.map(r=>[r.tx_date, r.merchant, r.category, `<span class="${r.amount>=0?'amount-pos':'amount-neg'}">${eur(r.amount)}</span>`, Math.round((r.confidence||0)*100)+'%'])); }
async function loadForecast(){ const f = await json('/api/forecast'); forecast.textContent = eur(f.simpleAverageNet); }
function fill(tableId, rows){ const tbody = document.querySelector(`#${tableId} tbody`); tbody.innerHTML = rows.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join(''); }
async function askAI(q){
  const question = q || document.getElementById('question').value; const month = document.getElementById('month').value;
  aiAnswer.textContent = 'Asking local Ollama...';
  try {
    const a = await json('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,month})});
    aiAnswer.textContent = a.answer;
  } catch (e) {
    aiAnswer.textContent = e.message;
  }
}
async function saveRule(){
  await json('/api/rules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pattern:rulePattern.value,merchant_clean:ruleMerchant.value,category:ruleCategory.value,subcategory:ruleSub.value,essential:true,avoidable:false})});
  alert('Rule saved. Future imports will use it.');
}
checkStatus(); loadAll();
