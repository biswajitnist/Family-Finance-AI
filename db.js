const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
const dbPath = path.join(dataDir, 'finance.db');
const db = new sqlite3.Database(dbPath);

function run(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function (err) {
      if (err) reject(err);
      else resolve({ id: this.lastID, changes: this.changes });
    });
  });
}
function all(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => (err ? reject(err) : resolve(rows)));
  });
}
function get(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => (err ? reject(err) : resolve(row)));
  });
}

async function initDb() {
  await run(`CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    original_name TEXT,
    source_type TEXT,
    extracted_text TEXT,
    ai_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  )`);

  await run(`CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_date TEXT NOT NULL,
    month TEXT NOT NULL,
    merchant TEXT NOT NULL,
    description TEXT,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'EUR',
    source TEXT DEFAULT 'Unknown',
    account TEXT,
    category TEXT DEFAULT 'Uncategorized',
    subcategory TEXT,
    essential INTEGER DEFAULT 1,
    avoidable INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.5,
    upload_id INTEGER,
    fingerprint TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(upload_id) REFERENCES uploads(id)
  )`);

  await run(`CREATE TABLE IF NOT EXISTS pending_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER,
    tx_date TEXT NOT NULL,
    merchant TEXT NOT NULL,
    description TEXT,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'EUR',
    source TEXT DEFAULT 'Unknown',
    account TEXT,
    category TEXT DEFAULT 'Uncategorized',
    subcategory TEXT,
    essential INTEGER DEFAULT 1,
    avoidable INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.5,
    selected INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(upload_id) REFERENCES uploads(id)
  )`);

  await run(`CREATE TABLE IF NOT EXISTS merchant_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT UNIQUE NOT NULL,
    merchant_clean TEXT,
    category TEXT NOT NULL,
    subcategory TEXT,
    essential INTEGER DEFAULT 1,
    avoidable INTEGER DEFAULT 0,
    notes TEXT
  )`);

  await run(`CREATE TABLE IF NOT EXISTS monthly_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT UNIQUE NOT NULL,
    savings_goal REAL DEFAULT 0,
    grocery_budget REAL DEFAULT 0,
    restaurant_budget REAL DEFAULT 0,
    amazon_budget REAL DEFAULT 0,
    notes TEXT
  )`);

  await run(`CREATE TABLE IF NOT EXISTS ai_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT,
    question TEXT,
    answer TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  )`);

  const rules = [
    ['EDEKA', 'EDEKA', 'Groceries', 'German Supermarket', 1, 0],
    ['PENNY', 'Penny', 'Groceries', 'German Supermarket', 1, 0],
    ['REWE', 'REWE', 'Groceries', 'German Supermarket', 1, 0],
    ['KAUFLAND', 'Kaufland', 'Groceries', 'German Supermarket', 1, 0],
    ['ALDI', 'Aldi', 'Groceries', 'German Supermarket', 1, 0],
    ['KABUL', 'Kabul Markt', 'Indian Staples', 'Indian/Asian Grocery', 1, 0],
    ['VAGHANI', 'GbR Vaghani Limbachiya', 'Indian Staples', 'Indian Grocery', 1, 0],
    ['NAMASTE', 'Namaste Deutschland', 'Indian Staples', 'Indian Online Grocery', 1, 0],
    ['DM DROGERIE', 'DM', 'Household', 'Drugstore', 1, 0],
    ['ROSSMANN', 'Rossmann', 'Household', 'Drugstore', 1, 0],
    ['MUELLER', 'Müller', 'Household', 'Drugstore / Household', 1, 0],
    ['MÜLLER', 'Müller', 'Household', 'Drugstore / Household', 1, 0],
    ['VODAFONE', 'Vodafone', 'Telecom', 'Phone/Internet', 1, 0],
    ['LSW ENERGIE', 'LSW Energie', 'Utilities', 'Energy', 1, 0],
    ['EINHUNDERT', 'Einhundert Energie', 'Utilities', 'Energy', 1, 0],
    ['NEULAND', 'Neuland', 'Housing', 'Rent', 1, 0],
    ['COMMERZBANK AG', 'Commerzbank', 'Loan / Banking', 'Loan or Banking', 1, 0],
    ['SCALABLE', 'Scalable Capital', 'Investments', 'Broker', 1, 0],
    ['SWISS LIFE', 'Swiss Life', 'Pension', 'Private Pension', 1, 0],
    ['ALLIANZ', 'Allianz', 'Insurance', 'Insurance', 1, 0],
    ['AXA', 'AXA', 'Insurance', 'Life Insurance', 1, 0],
    ['STADT WOLFSBURG', 'Stadt Wolfsburg', 'Kids', 'School Meals', 1, 0],
    ['TURNVEREIN', 'Turnverein Jahn', 'Kids', 'Sports', 1, 0],
    ['TSV', 'TSV Ehmen', 'Kids', 'Sports', 1, 0],
    ['DB VERTRIEB', 'DB Vertrieb', 'Transport', 'Public Transport', 1, 0],
    ['BMOOVD', 'Bmoovd Sportsbar Bowl', 'Family Activity', 'Kids Food/Activity', 1, 0],
    ['BADELAND', 'Badeland Wolfsburg', 'Family Activity', 'Swimming/Kids', 1, 0],
    ['KFC', 'KFC', 'Family Food', 'Kids Food', 0, 1],
    ['CREPES', 'Crepes', 'Family Food', 'Kids Snack', 0, 1],
    ['EISCAFE', 'Eiscafe', 'Family Food', 'Kids Snack', 0, 1],
    ['LIEFERANDO', 'Lieferando', 'Family Food', 'Delivery', 0, 1],
    ['AMAZON', 'Amazon', 'Shopping', 'Amazon', 0, 1],
    ['AMZN', 'Amazon', 'Shopping', 'Amazon Marketplace', 0, 1],
    ['PAYPAL', 'PayPal', 'Mixed / Review', 'Needs Review', 0, 1],
    ['XE, AMSTERDAM', 'XE', 'India Transfer', 'Transfer', 1, 0]
  ];

  for (const r of rules) {
    await run(`INSERT OR IGNORE INTO merchant_rules(pattern, merchant_clean, category, subcategory, essential, avoidable)
      VALUES (?, ?, ?, ?, ?, ?)`, r);
  }
}

module.exports = { db, initDb, run, all, get };
