CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  affiliation TEXT,
  field TEXT,
  bio TEXT,
  orcid TEXT,
  verified BOOLEAN NOT NULL DEFAULT FALSE,
  reputation INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS questions (
  id SERIAL PRIMARY KEY,
  author_id INT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}',
  views INT NOT NULL DEFAULT 0,
  score INT NOT NULL DEFAULT 0,
  accepted_answer_id INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS questions_tags_idx ON questions USING GIN (tags);

CREATE TABLE IF NOT EXISTS answers (
  id SERIAL PRIMARY KEY,
  question_id INT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  author_id INT REFERENCES users(id),
  body TEXT NOT NULL,
  score INT NOT NULL DEFAULT 0,
  ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS answers_q_idx ON answers (question_id);

CREATE TABLE IF NOT EXISTS articles (
  id SERIAL PRIMARY KEY,
  author_id INT NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL CHECK (kind IN ('blog','hypothesis','preprint')),
  title TEXT NOT NULL,
  abstract TEXT,
  body TEXT NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}',
  score INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS articles_tags_idx ON articles USING GIN (tags);

CREATE TABLE IF NOT EXISTS comments (
  id SERIAL PRIMARY KEY,
  target_type TEXT NOT NULL CHECK (target_type IN ('question','answer','article')),
  target_id INT NOT NULL,
  author_id INT NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS comments_target_idx ON comments (target_type, target_id);

CREATE TABLE IF NOT EXISTS votes (
  user_id INT NOT NULL REFERENCES users(id),
  target_type TEXT NOT NULL,
  target_id INT NOT NULL,
  value SMALLINT NOT NULL,
  PRIMARY KEY (user_id, target_type, target_id)
);

CREATE TABLE IF NOT EXISTS badges (
  user_id INT NOT NULL REFERENCES users(id),
  code TEXT NOT NULL,
  awarded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, code)
);

CREATE TABLE IF NOT EXISTS follows (
  follower_id INT NOT NULL REFERENCES users(id),
  followee_id INT NOT NULL REFERENCES users(id),
  PRIMARY KEY (follower_id, followee_id)
);

CREATE TABLE IF NOT EXISTS messages (
  id SERIAL PRIMARY KEY,
  sender_id INT NOT NULL REFERENCES users(id),
  recipient_id INT NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_rcpt_idx ON messages (recipient_id, created_at DESC);

CREATE TABLE IF NOT EXISTS papers (
  id SERIAL PRIMARY KEY,
  owner_id INT NOT NULL REFERENCES users(id),
  filename TEXT NOT NULL,
  text TEXT NOT NULL,
  summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
