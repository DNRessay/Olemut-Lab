import io
import json
import os
import re
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel, Field
from pypdf import PdfReader

from . import ai, db
from .security import check_pw, current_user, hash_pw, make_token, optional_user

app = FastAPI(title="SciLab API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGIN", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

ACADEMIC = re.compile(r"(\.edu(\.[a-z]{2})?|\.ac\.[a-z]{2}(\.[a-z]{2})?)$")
TARGETS = {"question": ("questions", 5), "answer": ("answers", 10), "article": ("articles", 10)}
Target = Literal["question", "answer", "article"]


# ---------- helpers ----------
def clean_tags(raw):
    tags = [re.sub(r"[^a-z0-9\-+.]", "", t.lower().lstrip("#")) for t in raw]
    return list(dict.fromkeys(t for t in tags if t))[:6]


def award(uid, code):
    if uid:
        db.run("INSERT INTO badges (user_id, code) VALUES (:u,:c) ON CONFLICT DO NOTHING", u=uid, c=code)


def add_rep(uid, delta):
    if not uid or not delta:
        return
    row = db.one("UPDATE users SET reputation=GREATEST(reputation+:d,0) WHERE id=:u RETURNING reputation",
                 d=delta, u=uid)
    if row and row["reputation"] >= 100:
        award(uid, "contributor")
    if row and row["reputation"] >= 500:
        award(uid, "trusted_voice")


def get_or_404(sql, **p):
    row = db.one(sql, **p)
    if not row:
        raise HTTPException(404, "Not found")
    return row


@app.get("/health")
def health():
    return {"ok": True}


# ---------- auth & profiles ----------
class Register(BaseModel):
    email: str = Field(max_length=200)
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,30}$")
    password: str = Field(min_length=8, max_length=200)
    affiliation: Optional[str] = Field(None, max_length=200)
    field: Optional[str] = Field(None, max_length=100)


class Login(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100)
    affiliation: Optional[str] = Field(None, max_length=200)
    field: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    orcid: Optional[str] = Field(None, max_length=40)


@app.post("/auth/register")
def register(b: Register):
    email = b.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Invalid email")
    verified = bool(ACADEMIC.search(email.split("@")[1]))
    try:
        u = db.one(
            "INSERT INTO users (email, username, password_hash, affiliation, field, verified) "
            "VALUES (:e,:u,:p,:a,:f,:v) RETURNING id",
            e=email, u=b.username, p=hash_pw(b.password), a=b.affiliation, f=b.field, v=verified)
    except Exception as e:
        if "23505" in str(e):
            raise HTTPException(409, "Email or username already taken")
        raise
    if verified:
        award(u["id"], "verified_academic")
    return {"token": make_token(u["id"])}


@app.post("/auth/login")
def login(b: Login):
    u = db.one("SELECT id, password_hash FROM users WHERE email=:e", e=b.email.strip().lower())
    if not u or not check_pw(b.password, u["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(u["id"])}


@app.get("/me")
def me(u=Depends(current_user)):
    return u


@app.patch("/me")
def update_me(b: ProfileIn, u=Depends(current_user)):
    db.run("UPDATE users SET display_name=:d, affiliation=:a, field=:f, bio=:b, orcid=:o WHERE id=:i",
           d=b.display_name, a=b.affiliation, f=b.field, b=b.bio, o=b.orcid, i=u["id"])
    return {"ok": True}


@app.get("/users")
def search_users(q: str = "", field: str = "", limit: int = Query(20, le=50)):
    sql = "SELECT username, display_name, affiliation, field, verified, reputation FROM users WHERE TRUE"
    p = {"n": limit}
    if q:
        sql += " AND (username ILIKE :q OR display_name ILIKE :q OR affiliation ILIKE :q)"
        p["q"] = f"%{q}%"
    if field:
        sql += " AND field ILIKE :f"
        p["f"] = f"%{field}%"
    return db.run(sql + " ORDER BY reputation DESC LIMIT :n", **p)


@app.get("/users/{username}")
def profile(username: str, viewer=Depends(optional_user)):
    u = get_or_404(
        "SELECT id, username, display_name, affiliation, field, bio, orcid, verified, reputation, created_at "
        "FROM users WHERE username=:n", n=username)
    uid = u["id"]
    u["badges"] = [r["code"] for r in db.run("SELECT code FROM badges WHERE user_id=:u", u=uid)]
    u["followers"] = db.one("SELECT COUNT(*) AS n FROM follows WHERE followee_id=:u", u=uid)["n"]
    u["following"] = db.one("SELECT COUNT(*) AS n FROM follows WHERE follower_id=:u", u=uid)["n"]
    u["is_following"] = bool(viewer and db.one(
        "SELECT 1 AS x FROM follows WHERE follower_id=:a AND followee_id=:b", a=viewer["id"], b=uid))
    u["questions"] = db.run("SELECT id, title, score FROM questions WHERE author_id=:u ORDER BY id DESC LIMIT 10", u=uid)
    u["articles"] = db.run("SELECT id, title, kind, score FROM articles WHERE author_id=:u ORDER BY id DESC LIMIT 10", u=uid)
    del u["id"]
    return u


@app.post("/users/{username}/follow")
def follow(username: str, u=Depends(current_user)):
    t = get_or_404("SELECT id FROM users WHERE username=:n", n=username)
    if t["id"] == u["id"]:
        raise HTTPException(400, "Cannot follow yourself")
    gone = db.run("DELETE FROM follows WHERE follower_id=:a AND followee_id=:b RETURNING 1 AS x", a=u["id"], b=t["id"])
    if not gone:
        db.run("INSERT INTO follows VALUES (:a,:b)", a=u["id"], b=t["id"])
    return {"following": not gone}


@app.get("/leaderboard")
def leaderboard():
    return db.run("SELECT username, display_name, affiliation, field, verified, reputation FROM users "
                  "ORDER BY reputation DESC, id LIMIT 25")


# ---------- messages ----------
class MessageIn(BaseModel):
    to: str
    body: str = Field(min_length=1, max_length=4000)


@app.post("/messages")
def send_message(b: MessageIn, u=Depends(current_user)):
    t = get_or_404("SELECT id FROM users WHERE username=:n", n=b.to)
    db.run("INSERT INTO messages (sender_id, recipient_id, body) VALUES (:s,:r,:b)", s=u["id"], r=t["id"], b=b.body)
    return {"ok": True}


@app.get("/messages")
def inbox(u=Depends(current_user)):
    return db.run(
        "SELECT m.id, m.body, m.created_at, s.username AS sender, r.username AS recipient "
        "FROM messages m JOIN users s ON s.id=m.sender_id JOIN users r ON r.id=m.recipient_id "
        "WHERE m.sender_id=:u OR m.recipient_id=:u ORDER BY m.id DESC LIMIT 50", u=u["id"])


# ---------- questions & answers ----------
class QuestionIn(BaseModel):
    title: str = Field(min_length=10, max_length=250)
    body: str = Field(min_length=20, max_length=20000)
    tags: list[str] = Field(min_length=1)


class AnswerIn(BaseModel):
    body: str = Field(min_length=10, max_length=20000)


@app.get("/questions")
def list_questions(tag: str = "", q: str = "", sort: str = "new", limit: int = Query(30, le=50), offset: int = 0):
    sql = ("SELECT x.id, x.title, LEFT(x.body, 240) AS excerpt, x.tags, x.score, x.views, "
           "x.accepted_answer_id, x.created_at, u.username, u.verified, "
           "(SELECT COUNT(*) FROM answers a WHERE a.question_id=x.id) AS answer_count "
           "FROM questions x JOIN users u ON u.id=x.author_id WHERE TRUE")
    p = {"n": limit, "o": offset}
    if tag:
        sql += " AND :tag = ANY(x.tags)"
        p["tag"] = tag.lower().lstrip("#")
    if q:
        sql += " AND (x.title ILIKE :q OR x.body ILIKE :q)"
        p["q"] = f"%{q}%"
    if sort == "unanswered":
        sql += " AND NOT EXISTS (SELECT 1 FROM answers a WHERE a.question_id=x.id)"
    order = "x.score DESC, x.id DESC" if sort == "top" else "x.id DESC"
    return db.run(f"{sql} ORDER BY {order} LIMIT :n OFFSET :o", **p)


@app.post("/questions")
def ask(b: QuestionIn, u=Depends(current_user)):
    tags = clean_tags(b.tags)
    if not tags:
        raise HTTPException(400, "Add at least one field tag")
    r = db.one("INSERT INTO questions (author_id, title, body, tags) VALUES (:a,:t,:b,:g) RETURNING id",
               a=u["id"], t=b.title, b=b.body, g=tags)
    return r


def _comments(where, **p):
    return db.run(
        "SELECT c.id, c.target_type, c.target_id, c.body, c.created_at, u.username, u.verified "
        f"FROM comments c JOIN users u ON u.id=c.author_id WHERE {where} ORDER BY c.id", **p)


@app.get("/questions/{qid}")
def question(qid: int):
    db.run("UPDATE questions SET views=views+1 WHERE id=:i", i=qid)
    q = get_or_404(
        "SELECT x.*, u.username, u.verified FROM questions x JOIN users u ON u.id=x.author_id WHERE x.id=:i", i=qid)
    answers = db.run(
        "SELECT a.id, a.body, a.score, a.ai_generated, a.created_at, u.username, u.verified "
        "FROM answers a LEFT JOIN users u ON u.id=a.author_id WHERE a.question_id=:i "
        "ORDER BY (a.id=:acc) DESC, a.score DESC, a.id", i=qid, acc=q["accepted_answer_id"] or 0)
    comments = _comments(
        "(c.target_type='question' AND c.target_id=:i) OR "
        "(c.target_type='answer' AND c.target_id IN (SELECT id FROM answers WHERE question_id=:i))", i=qid)
    return {"question": q, "answers": answers, "comments": comments}


@app.post("/questions/{qid}/answers")
def answer(qid: int, b: AnswerIn, u=Depends(current_user)):
    get_or_404("SELECT id FROM questions WHERE id=:i", i=qid)
    r = db.one("INSERT INTO answers (question_id, author_id, body) VALUES (:q,:a,:b) RETURNING id",
               q=qid, a=u["id"], b=b.body)
    award(u["id"], "first_answer")
    return r


@app.post("/questions/{qid}/accept/{aid}")
def accept(qid: int, aid: int, u=Depends(current_user)):
    q = get_or_404("SELECT author_id, accepted_answer_id FROM questions WHERE id=:i", i=qid)
    if q["author_id"] != u["id"]:
        raise HTTPException(403, "Only the asker can accept an answer")
    a = get_or_404("SELECT author_id FROM answers WHERE id=:a AND question_id=:q", a=aid, q=qid)
    if q["accepted_answer_id"] == aid:
        return {"ok": True}
    if q["accepted_answer_id"]:
        prev = db.one("SELECT author_id FROM answers WHERE id=:a", a=q["accepted_answer_id"])
        if prev:
            add_rep(prev["author_id"], -15)
    db.run("UPDATE questions SET accepted_answer_id=:a WHERE id=:q", a=aid, q=qid)
    if a["author_id"] != u["id"]:
        add_rep(a["author_id"], 15)
        award(a["author_id"], "accepted_answer")
    return {"ok": True}


# ---------- articles / blogs / pre-prints ----------
class ArticleIn(BaseModel):
    kind: Literal["blog", "hypothesis", "preprint"]
    title: str = Field(min_length=5, max_length=250)
    abstract: Optional[str] = Field(None, max_length=3000)
    body: str = Field(min_length=50, max_length=100000)
    tags: list[str] = Field(min_length=1)


@app.get("/articles")
def list_articles(kind: str = "", tag: str = "", limit: int = Query(30, le=50), offset: int = 0):
    sql = ("SELECT a.id, a.kind, a.title, a.abstract, a.tags, a.score, a.created_at, u.username, u.verified "
           "FROM articles a JOIN users u ON u.id=a.author_id WHERE TRUE")
    p = {"n": limit, "o": offset}
    if kind:
        sql += " AND a.kind=:k"
        p["k"] = kind
    if tag:
        sql += " AND :tag = ANY(a.tags)"
        p["tag"] = tag.lower().lstrip("#")
    return db.run(sql + " ORDER BY a.id DESC LIMIT :n OFFSET :o", **p)


@app.post("/articles")
def publish(b: ArticleIn, u=Depends(current_user)):
    r = db.one("INSERT INTO articles (author_id, kind, title, abstract, body, tags) "
               "VALUES (:a,:k,:t,:ab,:b,:g) RETURNING id",
               a=u["id"], k=b.kind, t=b.title, ab=b.abstract, b=b.body, g=clean_tags(b.tags))
    award(u["id"], "published_author")
    return r


@app.get("/articles/{aid}")
def article(aid: int):
    a = get_or_404("SELECT a.*, u.username, u.verified FROM articles a JOIN users u ON u.id=a.author_id "
                   "WHERE a.id=:i", i=aid)
    return {"article": a, "comments": _comments("c.target_type='article' AND c.target_id=:i", i=aid)}


# ---------- votes, comments, tags ----------
class VoteIn(BaseModel):
    target_type: Target
    target_id: int
    value: Literal[-1, 1]


class CommentIn(BaseModel):
    target_type: Target
    target_id: int
    body: str = Field(min_length=2, max_length=3000)


@app.post("/vote")
def vote(b: VoteIn, u=Depends(current_user)):
    table, rep = TARGETS[b.target_type]
    row = get_or_404(f"SELECT author_id, score FROM {table} WHERE id=:i", i=b.target_id)
    if row["author_id"] == u["id"]:
        raise HTTPException(400, "You cannot vote on your own post")
    prev = db.one("SELECT value FROM votes WHERE user_id=:u AND target_type=:t AND target_id=:i",
                  u=u["id"], t=b.target_type, i=b.target_id)
    old = prev["value"] if prev else 0
    new = 0 if old == b.value else b.value  # clicking the same arrow again removes the vote
    delta = new - old
    if new == 0:
        db.run("DELETE FROM votes WHERE user_id=:u AND target_type=:t AND target_id=:i",
               u=u["id"], t=b.target_type, i=b.target_id)
    else:
        db.run("INSERT INTO votes VALUES (:u,:t,:i,:v) ON CONFLICT (user_id,target_type,target_id) "
               "DO UPDATE SET value=:v", u=u["id"], t=b.target_type, i=b.target_id, v=new)
    r = db.one(f"UPDATE {table} SET score=score+:d WHERE id=:i RETURNING score", d=delta, i=b.target_id)
    add_rep(row["author_id"], delta * rep)
    return {"score": r["score"], "my_vote": new}


@app.post("/comments")
def comment(b: CommentIn, u=Depends(current_user)):
    table, _ = TARGETS[b.target_type]
    get_or_404(f"SELECT id FROM {table} WHERE id=:i", i=b.target_id)
    r = db.one("INSERT INTO comments (target_type, target_id, author_id, body) VALUES (:t,:i,:a,:b) RETURNING id",
               t=b.target_type, i=b.target_id, a=u["id"], b=b.body)
    if b.target_type == "article":
        award(u["id"], "peer_reviewer")
    return r


@app.get("/tags")
def tags():
    return db.run("SELECT t AS tag, COUNT(*) AS n FROM (SELECT unnest(tags) AS t FROM questions "
                  "UNION ALL SELECT unnest(tags) FROM articles) s GROUP BY t ORDER BY n DESC LIMIT 40")


# ---------- AI assistant & paper lab ----------
@app.post("/questions/{qid}/ai-answer")
def ai_answer(qid: int, u=Depends(current_user)):
    existing = db.one("SELECT id FROM answers WHERE question_id=:q AND ai_generated", q=qid)
    if existing:
        return existing
    q = get_or_404("SELECT title, body, tags FROM questions WHERE id=:i", i=qid)
    top = db.run("SELECT body FROM answers WHERE question_id=:q AND NOT ai_generated ORDER BY score DESC LIMIT 2", q=qid)
    text = ai.chat(
        f"Question: {q['title']}\nFields: {', '.join(q['tags'])}\n\n{q['body']}\n\n"
        + "".join(f"Existing answer: {a['body'][:1500]}\n" for a in top)
        + "\nPropose a clear, practical answer. List assumptions and what the asker should verify. "
          "Do not cite specific papers unless the question text contains them.")
    return db.one("INSERT INTO answers (question_id, author_id, body, ai_generated) VALUES (:q,NULL,:b,TRUE) "
                  "RETURNING id", q=qid, b=text)


@app.post("/questions/{qid}/summarize")
def summarize_thread(qid: int, u=Depends(current_user)):
    d = question(qid)
    thread = f"Q: {d['question']['title']}\n{d['question']['body']}\n" + "".join(
        f"\nAnswer (score {a['score']}): {a['body'][:2000]}" for a in d["answers"][:8]) + "".join(
        f"\nComment: {c['body'][:400]}" for c in d["comments"][:15])
    return {"summary": ai.chat("Summarize this research discussion: the problem, the consensus (if any), "
                                "points of disagreement, and recommended next steps.\n\n" + thread[:20000])}


@app.post("/papers")
async def upload_paper(file: UploadFile = File(...), u=Depends(current_user)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "PDF too large (max 5 MB)")
    try:
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages).strip()
    except Exception:
        raise HTTPException(400, "Could not read that PDF")
    if len(text) < 200:
        raise HTTPException(400, "No extractable text (scanned PDF?)")
    summary = ai.summarize_paper(text)
    return db.one("INSERT INTO papers (owner_id, filename, text, summary) VALUES (:o,:f,:t,:s) RETURNING id",
                  o=u["id"], f=(file.filename or "paper.pdf")[:200], t=text[:80000], s=json.dumps(summary))


@app.get("/papers")
def my_papers(u=Depends(current_user)):
    return db.run("SELECT id, filename, created_at FROM papers WHERE owner_id=:o ORDER BY id DESC", o=u["id"])


@app.get("/papers/{pid}")
def paper(pid: int, u=Depends(current_user)):
    p = get_or_404("SELECT id, filename, summary, created_at FROM papers WHERE id=:i AND owner_id=:o", i=pid, o=u["id"])
    p["summary"] = json.loads(p["summary"] or "{}")
    return p


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@app.post("/papers/{pid}/ask")
def ask_paper(pid: int, b: AskIn, u=Depends(current_user)):
    p = get_or_404("SELECT text FROM papers WHERE id=:i AND owner_id=:o", i=pid, o=u["id"])
    return {"answer": ai.chat(
        "Answer using ONLY the paper text below. If the paper does not say, reply that it is not stated.\n\n"
        f"PAPER:\n{p['text'][:24000]}\n\nQUESTION: {b.question}")}


@app.get("/papers/{pid}/related")
def related(pid: int, u=Depends(current_user)):
    p = get_or_404("SELECT summary FROM papers WHERE id=:i AND owner_id=:o", i=pid, o=u["id"])
    kws = [k for k in (json.loads(p["summary"] or "{}").get("keywords") or []) if isinstance(k, str)][:5]
    qs, arts, seen = [], [], set()
    for k in kws:
        for r in db.run("SELECT id, title FROM questions WHERE title ILIKE :k OR body ILIKE :k LIMIT 3", k=f"%{k}%"):
            if ("q", r["id"]) not in seen:
                seen.add(("q", r["id"]))
                qs.append(r)
        for r in db.run("SELECT id, title, kind FROM articles WHERE title ILIKE :k OR abstract ILIKE :k LIMIT 3", k=f"%{k}%"):
            if ("a", r["id"]) not in seen:
                seen.add(("a", r["id"]))
                arts.append(r)
    return {"keywords": kws, "questions": qs, "articles": arts}


handler = Mangum(app, lifespan="off")
