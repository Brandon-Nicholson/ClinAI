-- db/schema.sql
-- ClinAI database schema

-- Drop existing tables
-- DROP TABLE IF EXISTS analytics CASCADE;
-- DROP TABLE IF EXISTS prior_auth_intake CASCADE;
-- DROP TABLE IF EXISTS refill_requests CASCADE;
-- DROP TABLE IF EXISTS appointment_requests CASCADE;
-- DROP TABLE IF EXISTS tasks CASCADE;
-- DROP TABLE IF EXISTS transcripts CASCADE;
-- DROP TABLE IF EXISTS calls CASCADE;
-- DROP TABLE IF EXISTS patients CASCADE;

CREATE TABLE patients (
  id SERIAL PRIMARY KEY,
  phone VARCHAR(32) UNIQUE,
  first_name TEXT,
  last_name TEXT,
  dob DATE,
  mrn TEXT
);

CREATE TABLE calls (
  id SERIAL PRIMARY KEY,
  started_at TIMESTAMPTZ DEFAULT now(),
  ended_at TIMESTAMPTZ,
  patient_id INT REFERENCES patients(id),
  from_number VARCHAR(32),
  intent TEXT,                 -- 'schedule','refill','prior_auth', etc
  confidence NUMERIC(4,3),
  resolved BOOLEAN DEFAULT false,
  escalated BOOLEAN DEFAULT false,
  notes TEXT
);

CREATE TABLE transcripts (
  id SERIAL PRIMARY KEY,
  call_id INT REFERENCES calls(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('user','assistant')),
  text TEXT,
  ts TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE tasks (
  id SERIAL PRIMARY KEY,
  call_id INT REFERENCES calls(id) ON DELETE CASCADE,
  task_type TEXT,              -- 'schedule','refill','prior_auth','callback'
  payload JSONB,               -- structured info captured from the call
  status TEXT DEFAULT 'open',  -- 'open','in_progress','done','canceled'
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- ========== Optional Specialized Tables ==========
CREATE TABLE appointment_requests (
  id SERIAL PRIMARY KEY,
  call_id INT UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
  specialty TEXT,
  preferred_datetime TIMESTAMPTZ,
  reason TEXT
);

CREATE TABLE refill_requests (
  id SERIAL PRIMARY KEY,
  call_id INT UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
  drug_name TEXT,
  dosage TEXT,
  pharmacy TEXT,
  last_fill_date DATE
);

CREATE TABLE prior_auth_intake (
  id SERIAL PRIMARY KEY,
  call_id INT UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
  payer TEXT,
  cpt_codes TEXT,
  icd_codes TEXT,
  free_text TEXT
);

CREATE TABLE analytics (
  id SERIAL PRIMARY KEY,
  call_id INT REFERENCES calls(id) ON DELETE CASCADE,
  metric TEXT,     -- 'latency_ms','turns','words','interrupts'
  value NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);