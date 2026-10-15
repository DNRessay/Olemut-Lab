# SciLab — Stack Overflow for Scientists

FastAPI on Lambda (SAM) + Neon Postgres + Groq, static frontend on Cloudflare Pages.

## Deploy

```bash
# 1. DB schema (Neon connection string)
cd backend && pip install -r requirements.txt
DATABASE_URL="postgres://user:pass@host/db?sslmode=require" python migrate.py && cd ..

# 2. API
sam build
sam deploy --guided   # asks for DatabaseUrl, JwtSecret (any long random string), GroqApiKey, AllowedOrigin
# copy the ApiUrl output

# 3. Frontend: put ApiUrl in frontend/config.js, then
npx wrangler pages deploy frontend --project-name scilab
# re-run `sam deploy` with AllowedOrigin=https://scilab.pages.dev (your Pages URL)
```

Local: `cd backend && DATABASE_URL=... JWT_SECRET=x GROQ_API_KEY=... uvicorn app.main:app --reload`, then serve `frontend/` with `python -m http.server` and point `config.js` at `http://localhost:8000`.

## Notes

- Emails ending in `.edu` / `.ac.xx` are auto-marked **verified academic**; extend `ACADEMIC` in `main.py` for other domains or add ORCID checks.
- Reputation: question vote ±5, answer vote ±10, article vote ±10, accepted answer +15. Badges are awarded in `main.py` (`award`).
- AI (Groq, `GROQ_MODEL` env to change model): thread summaries, proposed answers (stored, labelled AI-generated), PDF paper summary + extracted reference list + "ask this paper". Papers are private to the uploader. The assistant is told not to invent citations, so "cross-referencing" means matching paper keywords to questions/articles on the platform.
- PDFs go through API Gateway, so they're capped at 5 MB; scanned PDFs without a text layer are rejected.
