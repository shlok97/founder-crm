PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES('schema_version','2');
-- Where a relationship came from: an event, a public list, a referral, inbound.
-- A new channel is a row here, never a new column.
CREATE TABLE IF NOT EXISTS sources(
 id INTEGER PRIMARY KEY,slug TEXT NOT NULL UNIQUE,label TEXT NOT NULL,
 category TEXT NOT NULL DEFAULT 'other' CHECK(category IN ('event','public_list','referral','inbound','outbound','partner','network','other')),
 is_public INTEGER NOT NULL DEFAULT 0,url TEXT,notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS accounts(
 id INTEGER PRIMARY KEY,name TEXT NOT NULL,slug TEXT UNIQUE,
 relationship TEXT NOT NULL DEFAULT 'unknown' CHECK(relationship IN ('prospect','customer','investor','partner','adviser','vendor','other','unknown')),
 lifecycle TEXT NOT NULL DEFAULT 'new' CHECK(lifecycle IN ('new','engaged','qualified','pilot','active','churned','lost','dormant','not_a_fit','internal','closed')),
 segment TEXT,tier TEXT,website TEXT,city TEXT,region TEXT,country TEXT,
 source_id INTEGER REFERENCES sources(id),source_detail TEXT,referred_by TEXT,owner TEXT,
 tags TEXT NOT NULL DEFAULT '[]',notes TEXT,first_touch_at TEXT,last_touch_at TEXT,
 next_action TEXT,next_action_date TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT);
CREATE TABLE IF NOT EXISTS contacts(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),
 name TEXT NOT NULL,email TEXT COLLATE NOCASE UNIQUE,
 title TEXT,seniority TEXT,
 decision_role TEXT NOT NULL DEFAULT 'unknown' CHECK(decision_role IN ('economic_buyer','champion','user','influencer','blocker','gatekeeper','unknown')),
 phone TEXT,whatsapp TEXT,linkedin_url TEXT,city TEXT,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','left','bounced','do_not_contact','unverified')),
 source_id INTEGER REFERENCES sources(id),source_detail TEXT,consent_basis TEXT,
 is_primary INTEGER NOT NULL DEFAULT 0,tags TEXT NOT NULL DEFAULT '[]',notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT);
CREATE TABLE IF NOT EXISTS opportunities(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),title TEXT NOT NULL,
 stage TEXT NOT NULL CHECK(stage IN ('discovery','qualified','demo','pilot','proposal','negotiation','won','lost','parked')),
 primary_contact_id INTEGER REFERENCES contacts(id),product TEXT,value REAL,currency TEXT,
 billing TEXT CHECK(billing IN ('monthly','annual','one_time','free_pilot') OR billing IS NULL),
 seats INTEGER,probability INTEGER CHECK(probability BETWEEN 0 AND 100 OR probability IS NULL),
 opened_at TEXT,expected_close TEXT,closed_at TEXT,outcome_reason TEXT,owner TEXT,
 source_id INTEGER REFERENCES sources(id),next_action TEXT,next_action_date TEXT,notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT);
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
-- occurred_at is when it happened; created_at is when it was written down.
CREATE TABLE IF NOT EXISTS interactions(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),
 intake_id INTEGER REFERENCES intake(id),proposal_id INTEGER UNIQUE REFERENCES proposals(id),
 summary TEXT NOT NULL,direction TEXT NOT NULL,
 contact_id INTEGER REFERENCES contacts(id),opportunity_id INTEGER REFERENCES opportunities(id),
 kind TEXT NOT NULL DEFAULT 'note' CHECK(kind IN ('note','message_sent','message_received','call','meeting_scheduled','meeting_held','meeting_canceled','demo','feedback','stage_change','card_collected','onboarded','support','event','signup','update_sent')),
 channel TEXT CHECK(channel IN ('whatsapp','email','call','in_person','video','linkedin','app','chat','sms','internal','other') OR channel IS NULL),
 occurred_at TEXT,body TEXT,outcome TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tasks(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),title TEXT NOT NULL,
 due_date TEXT,status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done')),
 proposal_id INTEGER UNIQUE REFERENCES proposals(id),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
-- A ticket is something a customer is waiting on. fixed_at, closed_at and notified_at
-- are separate on purpose: a fix the customer never heard about was not delivered.
CREATE TABLE IF NOT EXISTS tickets(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),title TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','triaged','in_progress','waiting_on_client','fixed','closed','wont_do','duplicate')),
 fixed_at TEXT,notified_at TEXT,proposal_id INTEGER UNIQUE REFERENCES proposals(id),
 contact_id INTEGER REFERENCES contacts(id),
 kind TEXT NOT NULL DEFAULT 'bug' CHECK(kind IN ('bug','data_defect','feature_request','question','performance','access','billing','onboarding','other')),
 severity TEXT NOT NULL DEFAULT 'normal' CHECK(severity IN ('blocker','high','normal','low')),
 area TEXT,reported_at TEXT,
 reported_via TEXT CHECK(reported_via IN ('whatsapp','email','call','in_person','video','linkedin','app','chat','sms','internal','other') OR reported_via IS NULL),
 body TEXT,expected TEXT,resolution TEXT,evidence TEXT,commit_ref TEXT,release_ref TEXT,owner TEXT,
 next_action TEXT,next_action_date TEXT,closed_at TEXT,
 notified_via TEXT CHECK(notified_via IN ('whatsapp','email','call','in_person','video','linkedin','app','chat','sms','internal','other') OR notified_via IS NULL),
 notified_note TEXT,notification_verified INTEGER NOT NULL DEFAULT 0,
 tags TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT);
-- Qualification (commercial KYC): whether an account can and will buy. One row per account.
-- The generic fields below always count toward completeness; custom fields defined with
-- qualification=1 count too, so each business adds its own questions without code.
CREATE TABLE IF NOT EXISTS qualification(
 account_id INTEGER PRIMARY KEY REFERENCES accounts(id),as_of TEXT,
 entity_type TEXT,team_size INTEGER,current_tools TEXT,pain_points TEXT,use_case TEXT,
 buying_trigger TEXT,decision_process TEXT,decision_contact_id INTEGER REFERENCES contacts(id),
 budget_authority TEXT CHECK(budget_authority IN ('yes','no','influencer','unknown') OR budget_authority IS NULL),
 budget_band TEXT,fit_score INTEGER CHECK(fit_score BETWEEN 1 AND 5 OR fit_score IS NULL),
 fit_rationale TEXT,risk_flags TEXT,
 confidence TEXT NOT NULL DEFAULT 'low' CHECK(confidence IN ('low','medium','high')),
 verified_by TEXT,verified_at TEXT,notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT);
-- Every qualification claim that matters says where it came from.
CREATE TABLE IF NOT EXISTS qualification_evidence(
 id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES accounts(id),
 claim TEXT NOT NULL,source TEXT NOT NULL,url TEXT,observed_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY,slug TEXT NOT NULL UNIQUE,name TEXT NOT NULL,organizer TEXT,
 start_date TEXT,end_date TEXT,city TEXT,venue TEXT,role TEXT,cost REAL,currency TEXT,notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS event_contacts(
 event_id INTEGER NOT NULL REFERENCES events(id),contact_id INTEGER NOT NULL REFERENCES contacts(id),
 met_at TEXT,met_context TEXT,followed_up INTEGER NOT NULL DEFAULT 0,notes TEXT,
 PRIMARY KEY(event_id,contact_id));
-- Custom fields: your business's own data on any record, without a schema change.
CREATE TABLE IF NOT EXISTS field_definitions(
 id INTEGER PRIMARY KEY,
 object_type TEXT NOT NULL CHECK(object_type IN ('account','contact','opportunity','ticket','interaction','event')),
 key TEXT NOT NULL,label TEXT NOT NULL,
 type TEXT NOT NULL DEFAULT 'text' CHECK(type IN ('text','number','integer','date','boolean','choice','json')),
 choices TEXT,qualification INTEGER NOT NULL DEFAULT 0,help TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(object_type,key));
CREATE TABLE IF NOT EXISTS custom_values(
 object_type TEXT NOT NULL,object_id INTEGER NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(object_type,object_id,key),
 FOREIGN KEY(object_type,key) REFERENCES field_definitions(object_type,key));
-- Where an imported record came from, so a re-run updates instead of duplicating.
CREATE TABLE IF NOT EXISTS import_ids(
 source TEXT NOT NULL,source_table TEXT NOT NULL,source_id TEXT NOT NULL,
 object_type TEXT NOT NULL,object_id INTEGER NOT NULL,
 imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(source,source_table,source_id));
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,object_type TEXT NOT NULL,
 object_id INTEGER,detail TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_intake_contact ON intake(contact_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(status,due_date);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_contacts_account ON contacts(account_id);
CREATE INDEX IF NOT EXISTS idx_interactions_account ON interactions(account_id,occurred_at);
CREATE INDEX IF NOT EXISTS idx_tickets_account ON tickets(account_id,status);
CREATE INDEX IF NOT EXISTS idx_opportunities_account ON opportunities(account_id);
CREATE INDEX IF NOT EXISTS idx_evidence_account ON qualification_evidence(account_id);
CREATE INDEX IF NOT EXISTS idx_import_object ON import_ids(object_type,object_id);
