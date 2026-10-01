CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS issues (
  id SERIAL PRIMARY KEY,
  issue_date DATE NOT NULL UNIQUE,
  filename TEXT,
  pdf_sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'processing',   -- processing | done | partial
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS articles (
  id SERIAL PRIMARY KEY,
  issue_id INT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  page_no INT NOT NULL,
  section TEXT,
  headline TEXT NOT NULL,
  body TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  incomplete BOOLEAN NOT NULL DEFAULT FALSE,
  prefilter_passed BOOLEAN,
  prefilter_score REAL,
  classify_status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | skipped | failed
  relevant BOOLEAN,
  category TEXT,
  exam_tags TEXT[] NOT NULL DEFAULT '{}',
  relevance_score REAL,
  reason TEXT,
  UNIQUE (issue_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_articles_issue ON articles(issue_id);

CREATE TABLE IF NOT EXISTS extractions (
  article_id INT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  validation_status TEXT NOT NULL,                  -- verified | partial | needs_review
  warnings JSONB NOT NULL DEFAULT '[]',
  model TEXT,
  prompt_version TEXT,
  search_text TEXT NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
  embedding vector(768),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_extractions_tsv ON extractions USING GIN (tsv);
