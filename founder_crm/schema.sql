PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES('schema_version','1');
CREATE TABLE IF NOT EXISTS accounts(
 id INTEGER PRIMARY KEY,name TEXT NOT NULL,
 relationship TEXT NOT NULL DEFAULT 'unknown' CHECK(relationship IN ('prospect','customer','investor','partner','adviser','vendor','other','unknown')),
 lifecycle TEXT NOT NULL DEFAULT 'new' CHECK(lifecycle IN ('new','engaged','pilot','active','dormant','closed')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS contacts(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),
 name TEXT NOT NULL,email TEXT COLLATE NOCASE UNIQUE,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS opportunities(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),title TEXT NOT NULL,
 stage TEXT NOT NULL CHECK(stage IN ('discovery','demo','pilot','proposal','won','lost')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS intake(
 id INTEGER PRIMARY KEY,source TEXT NOT NULL,external_id TEXT NOT NULL,subject TEXT NOT NULL,
 sender TEXT NOT NULL DEFAULT '',body TEXT NOT NULL,direction TEXT NOT NULL DEFAULT 'in',
 trusted INTEGER NOT NULL DEFAULT 0,contact_id INTEGER REFERENCES contacts(id),
 received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(source,external_id));
CREATE TABLE IF NOT EXISTS proposals(
 id INTEGER PRIMARY KEY,intake_id INTEGER NOT NULL REFERENCES intake(id),action TEXT NOT NULL,
 payload TEXT NOT NULL,context TEXT NOT NULL,evidence_hash TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','applied','rejected')),
 created_by TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS judgments(
 id INTEGER PRIMARY KEY,proposal_id INTEGER NOT NULL REFERENCES proposals(id),verdict TEXT NOT NULL,
 confidence REAL,model TEXT,provider TEXT,cost_usd REAL,input_tokens INTEGER,output_tokens INTEGER,
 response TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS interactions(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),
 intake_id INTEGER REFERENCES intake(id),proposal_id INTEGER UNIQUE REFERENCES proposals(id),
 summary TEXT NOT NULL,direction TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tasks(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),title TEXT NOT NULL,
 due_date TEXT,status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done')),
 proposal_id INTEGER UNIQUE REFERENCES proposals(id),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tickets(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),title TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','fixed')),
 fixed_at TEXT,notified_at TEXT,proposal_id INTEGER UNIQUE REFERENCES proposals(id),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,object_type TEXT NOT NULL,
 object_id INTEGER,detail TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_intake_contact ON intake(contact_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(status,due_date);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
