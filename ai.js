const OLLAMA_URL = process.env.OLLAMA_URL || 'http://127.0.0.1:11434';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || 'llama3.2';
const OLLAMA_TIMEOUT_MS = Number(process.env.OLLAMA_TIMEOUT_MS || 90000);

function selectedModel(model) {
  return String(model || OLLAMA_MODEL).trim() || OLLAMA_MODEL;
}

function ollamaError(e) {
  const cause = e && e.cause ? ` (${e.cause.code || e.cause.message || e.cause})` : '';
  return `${e.message || e}${cause}`;
}

async function ollamaFetch(path, body, { timeoutMs = OLLAMA_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${OLLAMA_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal
    });
    if (!res.ok) throw new Error(`Ollama HTTP ${res.status}: ${await res.text()}`);
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function ollamaStatus() {
  try {
    const res = await fetch(`${OLLAMA_URL}/api/tags`);
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const data = await res.json();
    return { ok: true, model: OLLAMA_MODEL, models: data.models || [] };
  } catch (e) {
    return { ok: false, error: ollamaError(e), model: OLLAMA_MODEL };
  }
}

function fallbackExtract(text, defaultYear = new Date().getFullYear()) {
  const monthMap = { Jan:'01', Feb:'02', Mar:'03', Apr:'04', May:'05', Jun:'06', Jul:'07', Aug:'08', Sep:'09', Oct:'10', Nov:'11', Dec:'12' };
  const lines = text.split(/\n+/).map(l => l.trim()).filter(Boolean);
  const txs = [];
  let currentDate = null;
  for (let i=0; i<lines.length; i++) {
    const l = lines[i];
    const d1 = l.match(/(\d{1,2})[\.\/\-](\d{1,2})[\.\/\-](20\d{2})/);
    const d2 = l.match(/(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i);
    if (d1) currentDate = `${d1[3]}-${String(d1[2]).padStart(2,'0')}-${String(d1[1]).padStart(2,'0')}`;
    if (d2) currentDate = `${defaultYear}-${monthMap[d2[2].slice(0,3)]}-${String(d2[1]).padStart(2,'0')}`;
    const amt = l.match(/([+-]?\d{1,3}(?:[\.\s]\d{3})*,\d{2}|[+-]?\d+,\d{2})\s*€?/);
    if (amt && currentDate && !/Amazon points|Points Debit|Dashboard|Movements|Financing|Settings|Account/i.test(l)) {
      const amount = parseFloat(amt[1].replace(/\./g,'').replace(/\s/g,'').replace(',','.'));
      let merchant = l.replace(amt[0], '').replace(/Compra en|Purchase at|Authorized/gi,'').trim();
      if (!merchant && i>0) merchant = lines[i-1].replace(/Compra en|Purchase at/gi,'').trim();
      if (merchant && Math.abs(amount) > 0) txs.push({ date: currentDate, merchant, description: l, amount, source: 'OCR/AI Fallback' });
    }
  }
  return txs;
}

async function extractTransactionsWithAI(text, options = {}) {
  const defaultYear = options.year || new Date().getFullYear();
  const model = selectedModel(options.model);
  const prompt = `You are a private finance OCR parser for Biswajit. Extract transactions from OCR/bank statement text.\n\nReturn ONLY valid JSON. No markdown. No explanations.\nSchema:\n{ "transactions": [ { "date":"YYYY-MM-DD", "merchant":"clean merchant", "description":"short original detail", "amount": -12.34, "source":"Commerzbank|Amazon Visa|OCR|PDF|CSV", "category":"one of: Income, Housing, Utilities, Groceries, Indian Staples, Household, Family Food, Family Activity, Kids, Transport, Insurance, Pension, Investments, Loan / Banking, Telecom, India Transfer, Shopping, Health, Subscriptions, Misc / Review", "subcategory":"short", "essential": true, "avoidable": false, "confidence": 0.0 } ] }\n\nRules:\n- Ignore Amazon points lines and 0.00 point debit rows.\n- Amounts with minus are expenses. Salary/Kindergeld are positive income.\n- Convert comma decimals to dot decimals.\n- For dates like 25 Mar use year ${defaultYear}.\n- Vaghani, Kabul Markt, Namaste Deutschland, Indian stores = Indian Staples.\n- EDEKA, Penny, REWE, Aldi, Kaufland = Groceries.\n- Badeland, Bmoovd, kids activity food = Family Activity or Family Food, not luxury restaurant.\n- Vodafone = Telecom. LSW/Einhundert = Utilities. Neuland = Housing. Scalable = Investments. Swiss Life = Pension.\n\nTEXT:\n${text.slice(0, 12000)}`;

  try {
    const data = await ollamaFetch('/api/generate', { model, prompt, stream: false, format: 'json' }, { timeoutMs: 120000 });
    const raw = data.response || '{}';
    const parsed = JSON.parse(raw);
    return { ok: true, model, transactions: parsed.transactions || [], raw };
  } catch (e) {
    return { ok: false, model, error: ollamaError(e), transactions: fallbackExtract(text, defaultYear), raw: null };
  }
}

async function askAI(question, context) {
  const model = selectedModel(context && context.model);
  const prompt = `You are Biswajit's local finance assistant. Give practical, accurate finance analysis from the local SQLite data. Be concise.\n\nContext JSON:\n${JSON.stringify(context).slice(0, 14000)}\n\nQuestion: ${question}`;
  try {
    const data = await ollamaFetch('/api/generate', { model, prompt, stream: false });
    return { ok: true, model, answer: data.response };
  } catch (e) {
    return { ok: false, model, answer: `Ollama not available: ${ollamaError(e)}` };
  }
}

module.exports = { ollamaStatus, extractTransactionsWithAI, askAI };
