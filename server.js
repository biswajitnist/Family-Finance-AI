const express = require('express');
const cors = require('cors');
const multer = require('multer');
const path = require('path');
const crypto = require('crypto');
const { initDb, run, all, get } = require('./db');
const { extractText } = require('./extract');
const { ollamaStatus, extractTransactionsWithAI, askAI } = require('./ai');

const app = express();
const PORT = process.env.PORT || 3000;
const upload = multer({ dest: path.join(__dirname, 'uploads') });

app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.static(path.join(__dirname, 'public')));

function normalizeMerchant(s='') { return String(s).replace(/\s+/g,' ').trim(); }
function monthFromDate(date) { return String(date).slice(0,7); }
const CATEGORIES = [
  'Income', 'Housing', 'Utilities', 'Groceries', 'Indian Staples', 'Household',
  'Family Food', 'Family Activity', 'Kids', 'Transport', 'Insurance', 'Pension',
  'Investments', 'Loan / Banking', 'Telecom', 'India Transfer', 'Shopping',
  'Health', 'Subscriptions', 'Misc / Review', 'Uncategorized'
];
function fingerprint(tx) {
  return crypto.createHash('sha1').update(`${tx.date}|${normalizeMerchant(tx.merchant).toUpperCase()}|${Number(tx.amount).toFixed(2)}|${tx.source||''}`).digest('hex');
}
async function applyRules(tx) {
  const merchantUpper = normalizeMerchant(tx.merchant).toUpperCase();
  const rules = await all('SELECT * FROM merchant_rules ORDER BY LENGTH(pattern) DESC');
  for (const r of rules) {
    if (merchantUpper.includes(String(r.pattern).toUpperCase())) {
      return { ...tx, merchant: r.merchant_clean || tx.merchant, category: r.category, subcategory: r.subcategory, essential: !!r.essential, avoidable: !!r.avoidable, confidence: Math.max(tx.confidence || 0.5, 0.9) };
    }
  }
  return tx;
}
async function saveTransactions(transactions, uploadId) {
  let inserted = 0, skipped = 0;
  const saved = [];
  for (let tx of transactions) {
    if (!tx.date || !tx.merchant || tx.amount === undefined || tx.amount === null) { skipped++; continue; }
    tx = await applyRules(tx);
    const amount = Number(tx.amount);
    if (!Number.isFinite(amount)) { skipped++; continue; }
    const fp = fingerprint(tx);
    try {
      const result = await run(`INSERT INTO transactions
        (tx_date, month, merchant, description, amount, currency, source, account, category, subcategory, essential, avoidable, confidence, upload_id, fingerprint)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`, [
          tx.date, monthFromDate(tx.date), normalizeMerchant(tx.merchant), tx.description || '', amount, tx.currency || 'EUR', tx.source || 'AI Extracted', tx.account || '', tx.category || 'Uncategorized', tx.subcategory || '', tx.essential ? 1 : 0, tx.avoidable ? 1 : 0, tx.confidence || 0.5, uploadId, fp
        ]);
      inserted++; saved.push({ id: result.id, ...tx });
    } catch (e) {
      if (String(e.message).includes('UNIQUE')) skipped++; else throw e;
    }
  }
  return { inserted, skipped, saved };
}

async function savePendingTransactions(transactions, uploadId) {
  let staged = 0, skipped = 0;
  const pending = [];
  for (let tx of transactions) {
    if (!tx.date || !tx.merchant || tx.amount === undefined || tx.amount === null) { skipped++; continue; }
    tx = await applyRules(tx);
    const amount = Number(tx.amount);
    if (!Number.isFinite(amount)) { skipped++; continue; }
    const result = await run(`INSERT INTO pending_transactions
      (upload_id, tx_date, merchant, description, amount, currency, source, account, category, subcategory, essential, avoidable, confidence, selected)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)`, [
        uploadId, tx.date, normalizeMerchant(tx.merchant), tx.description || '', amount, tx.currency || 'EUR', tx.source || 'AI Extracted', tx.account || '', tx.category || 'Uncategorized', tx.subcategory || '', tx.essential ? 1 : 0, tx.avoidable ? 1 : 0, tx.confidence || 0.5
      ]);
    staged++;
    pending.push({ id: result.id, ...tx });
  }
  return { staged, skipped, pending };
}

app.get('/api/status', async (req,res) => res.json(await ollamaStatus()));

app.post('/api/upload', upload.single('file'), async (req,res) => {
  try {
    if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
    const extracted = await extractText(req.file.path, req.file.originalname);
    const uploadRow = await run(`INSERT INTO uploads(filename, original_name, source_type, extracted_text) VALUES (?, ?, ?, ?)`, [req.file.filename, req.file.originalname, extracted.type, extracted.text]);
    const ai = await extractTransactionsWithAI(extracted.text, { year: req.body.year || new Date().getFullYear(), model: req.body.model });
    await run('UPDATE uploads SET ai_json=? WHERE id=?', [JSON.stringify(ai), uploadRow.id]);
    const saveFallback = req.body.saveFallback === 'true';
    const shouldStage = ai.ok || saveFallback;
    const result = shouldStage ? await savePendingTransactions(ai.transactions, uploadRow.id) : { staged: 0, skipped: 0, pending: [] };
    res.json({
      ok: true,
      uploadId: uploadRow.id,
      fileName: req.file.originalname,
      sourceType: extracted.type,
      ocrChars: extracted.text.length,
      model: ai.model,
      chunks: ai.chunks || 1,
      aiOk: ai.ok,
      aiError: ai.error || null,
      staged: result.staged,
      inserted: 0,
      skipped: result.skipped,
      pendingCount: result.pending.length,
      savedCount: 0,
      usedFallback: !ai.ok,
      fallbackSaved: false,
      fallbackStaged: !ai.ok && saveFallback,
      saveBlocked: !ai.ok && !saveFallback,
      preview: extracted.text.slice(0, 1000)
    });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.delete('/api/uploads/:id', async (req,res) => {
  await run('DELETE FROM pending_transactions WHERE upload_id=?', [req.params.id]);
  await run('DELETE FROM transactions WHERE upload_id=?', [req.params.id]);
  await run('DELETE FROM uploads WHERE id=?', [req.params.id]);
  res.json({ ok:true });
});

app.get('/api/transactions', async (req,res) => {
  const where = []; const params = [];
  if (req.query.month) { where.push('month=?'); params.push(req.query.month); }
  if (req.query.category) { where.push('category=?'); params.push(req.query.category); }
  const sql = `SELECT * FROM transactions ${where.length?'WHERE '+where.join(' AND '):''} ORDER BY tx_date DESC, id DESC LIMIT 1000`;
  res.json(await all(sql, params));
});

app.delete('/api/transactions/:id', async (req,res)=>{ await run('DELETE FROM transactions WHERE id=?',[req.params.id]); res.json({ok:true}); });

app.patch('/api/transactions/:id', async (req,res) => {
  const category = String(req.body.category || '').trim();
  if (!CATEGORIES.includes(category)) return res.status(400).json({ error: 'Invalid category' });
  const result = await run('UPDATE transactions SET category=? WHERE id=?', [category, req.params.id]);
  res.json({ ok:true, changed: result.changes });
});

app.get('/api/pending', async (req,res) => {
  const where = []; const params = [];
  if (req.query.uploadId) { where.push('upload_id=?'); params.push(req.query.uploadId); }
  const sql = `SELECT * FROM pending_transactions ${where.length?'WHERE '+where.join(' AND '):''} ORDER BY tx_date DESC, id DESC LIMIT 1000`;
  res.json(await all(sql, params));
});

app.patch('/api/pending/:id', async (req,res) => {
  const allowed = ['tx_date', 'merchant', 'description', 'amount', 'category', 'subcategory', 'selected'];
  const updates = [];
  const params = [];
  for (const key of allowed) {
    if (!(key in req.body)) continue;
    if (key === 'category' && !CATEGORIES.includes(String(req.body[key]).trim())) return res.status(400).json({ error: 'Invalid category' });
    if (key === 'amount' && !Number.isFinite(Number(req.body[key]))) return res.status(400).json({ error: 'Invalid amount' });
    updates.push(`${key}=?`);
    params.push(key === 'selected' ? (req.body[key] ? 1 : 0) : req.body[key]);
  }
  if (!updates.length) return res.json({ ok:true, changed: 0 });
  params.push(req.params.id);
  const result = await run(`UPDATE pending_transactions SET ${updates.join(', ')} WHERE id=?`, params);
  res.json({ ok:true, changed: result.changes });
});

app.delete('/api/pending/:id', async (req,res) => {
  await run('DELETE FROM pending_transactions WHERE id=?', [req.params.id]);
  res.json({ ok:true });
});

app.post('/api/pending/commit', async (req,res) => {
  const where = ['selected=1']; const params = [];
  if (req.body.uploadId) { where.push('upload_id=?'); params.push(req.body.uploadId); }
  const rows = await all(`SELECT * FROM pending_transactions WHERE ${where.join(' AND ')} ORDER BY tx_date, id`, params);
  const result = { inserted: 0, skipped: 0, saved: [] };
  for (const r of rows) {
    const saved = await saveTransactions([{
      date: r.tx_date,
      merchant: r.merchant,
      description: r.description,
      amount: r.amount,
      currency: r.currency,
      source: r.source,
      account: r.account,
      category: r.category,
      subcategory: r.subcategory,
      essential: !!r.essential,
      avoidable: !!r.avoidable,
      confidence: r.confidence
    }], r.upload_id);
    result.inserted += saved.inserted;
    result.skipped += saved.skipped;
    result.saved.push(...saved.saved);
  }
  if (rows.length) {
    const ids = rows.map(r => r.id);
    await run(`DELETE FROM pending_transactions WHERE id IN (${ids.map(()=>'?').join(',')})`, ids);
  }
  res.json({ ok:true, reviewed: rows.length, ...result });
});

app.post('/api/pending/discard', async (req,res) => {
  if (req.body.uploadId) await run('DELETE FROM pending_transactions WHERE upload_id=?', [req.body.uploadId]);
  else await run('DELETE FROM pending_transactions');
  res.json({ ok:true });
});

app.post('/api/rules', async (req,res) => {
  const r = req.body;
  await run(`INSERT OR REPLACE INTO merchant_rules(pattern, merchant_clean, category, subcategory, essential, avoidable, notes) VALUES (?, ?, ?, ?, ?, ?, ?)`, [r.pattern, r.merchant_clean || r.pattern, r.category, r.subcategory || '', r.essential ? 1 : 0, r.avoidable ? 1 : 0, r.notes || '']);
  res.json({ ok:true });
});
app.get('/api/rules', async (req,res)=>res.json(await all('SELECT * FROM merchant_rules ORDER BY category, pattern')));

app.get('/api/summary', async (req,res) => {
  const month = req.query.month;
  const params = month ? [month] : [];
  const where = month ? 'WHERE month=?' : '';
  const totals = await get(`SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) income, COALESCE(SUM(CASE WHEN amount<0 THEN amount ELSE 0 END),0) expenses, COALESCE(SUM(amount),0) net FROM transactions ${where}`, params);
  const byCat = await all(`SELECT category, ROUND(SUM(amount),2) total, COUNT(*) count FROM transactions ${where} GROUP BY category ORDER BY total ASC`, params);
  const byShop = await all(`SELECT merchant, category, ROUND(SUM(amount),2) total, COUNT(*) count FROM transactions ${where} AND category IN ('Groceries','Indian Staples','Household') GROUP BY merchant, category ORDER BY total ASC`.replace('WHERE AND','WHERE').replace(' transactions  AND',' transactions WHERE'), params);
  const months = await all(`SELECT month, ROUND(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),2) income, ROUND(SUM(CASE WHEN amount<0 THEN amount ELSE 0 END),2) expenses, ROUND(SUM(amount),2) net FROM transactions GROUP BY month ORDER BY month`);
  res.json({ totals, byCat, byShop, months });
});

app.get('/api/anomalies', async (req,res) => {
  const month = req.query.month;
  if (!month) return res.json([]);
  const current = await all('SELECT category, SUM(amount) total FROM transactions WHERE month=? AND amount<0 GROUP BY category', [month]);
  const avg = await all('SELECT category, AVG(total) avg_total FROM (SELECT month, category, SUM(amount) total FROM transactions WHERE month<>? AND amount<0 GROUP BY month, category) GROUP BY category', [month]);
  const avgMap = Object.fromEntries(avg.map(a=>[a.category, a.avg_total]));
  const anomalies = current.map(c => ({ category:c.category, current: c.total, average: avgMap[c.category] || 0, difference: c.total - (avgMap[c.category] || 0) })).filter(a => a.average && Math.abs(a.difference) > 50).sort((a,b)=>a.difference-a.difference);
  res.json(anomalies);
});

app.get('/api/forecast', async (req,res) => {
  const rows = await all(`SELECT month, SUM(amount) net FROM transactions GROUP BY month ORDER BY month`);
  const avgNet = rows.length ? rows.reduce((s,r)=>s+r.net,0)/rows.length : 0;
  res.json({ historical: rows, simpleAverageNet: Math.round(avgNet*100)/100, message: avgNet >= 0 ? 'Current average cashflow is positive.' : 'Current average cashflow is negative; review avoidable categories.' });
});

app.post('/api/ask', async (req,res) => {
  const month = req.body.month;
  const summary = await get(`SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) income, COALESCE(SUM(CASE WHEN amount<0 THEN amount ELSE 0 END),0) expenses, COALESCE(SUM(amount),0) net FROM transactions ${month?'WHERE month=?':''}`, month?[month]:[]);
  const categories = await all(`SELECT category, merchant, ROUND(SUM(amount),2) total, COUNT(*) count FROM transactions ${month?'WHERE month=?':''} GROUP BY category, merchant ORDER BY total ASC LIMIT 100`, month?[month]:[]);
  const answer = await askAI(req.body.question || 'Analyze my month-end cashflow.', { month, model: req.body.model, summary, categories });
  if (answer.ok) await run('INSERT INTO ai_insights(month, question, answer) VALUES (?, ?, ?)', [month || '', req.body.question || '', answer.answer]);
  res.json(answer);
});

initDb().then(()=>app.listen(PORT, ()=>console.log(`Finance Tracker v3 running on http://localhost:${PORT}`))).catch(err=>{console.error(err); process.exit(1);});
