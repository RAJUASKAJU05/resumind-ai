"""Resumind AI - compact full-stack app (FastAPI + SQLite). Run: uvicorn app:app"""
import os, re, io, json, hmac, time, base64, hashlib, secrets, sqlite3
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Response, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field

DB = os.getenv("DB_PATH", "resumind.db")
SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)  # set JWT_SECRET to keep sessions across restarts
AI_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-4-6")
MAX_MB = 5
app = FastAPI(title="Resumind AI")

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c

def init():
    c = db(); c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, pw TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS resumes(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      filename TEXT, text TEXT, parsed TEXT, analysis TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      title TEXT, description TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY, resume_id INTEGER REFERENCES resumes(id) ON DELETE CASCADE,
      job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE, score INTEGER, result TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, role TEXT, content TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX IF NOT EXISTS ix_res_user ON resumes(user_id);""")
    c.commit(); c.close()
init()

# ---------- auth ----------
def hash_pw(p, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode(), 200_000).hex()
def check_pw(p, h):
    return hmac.compare_digest(hash_pw(p, h.split("$")[0]), h)
def make_token(uid):
    body = base64.urlsafe_b64encode(json.dumps({"u": uid, "e": int(time.time()) + 7*86400}).encode()).decode()
    return body + "." + hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
def user(request: Request):
    t = request.cookies.get("session", "")
    try:
        body, sig = t.split(".")
        if not hmac.compare_digest(sig, hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()): raise ValueError
        d = json.loads(base64.urlsafe_b64decode(body))
        if d["e"] < time.time(): raise ValueError
        return d["u"]
    except Exception:
        raise HTTPException(401, "Please log in.")

_hits = {}
def limit(key, n=10, per=60):
    now = time.time(); h = [t for t in _hits.get(key, []) if now - t < per]
    if len(h) >= n: raise HTTPException(429, "Too many attempts. Please wait a minute.")
    _hits[key] = h + [now]

class Reg(BaseModel):
    name: str = Field(min_length=1, max_length=80); email: EmailStr; password: str = Field(min_length=8, max_length=128)
class Login(BaseModel):
    email: str; password: str

def set_cookie(resp, uid):
    resp.set_cookie("session", make_token(uid), httponly=True, samesite="lax", max_age=7*86400, secure=os.getenv("COOKIE_SECURE") == "1")

@app.post("/api/auth/register", status_code=201)
def register(b: Reg, request: Request, resp: Response):
    limit("r" + request.client.host)
    c = db()
    try:
        cur = c.execute("INSERT INTO users(name,email,pw) VALUES(?,?,?)", (b.name.strip(), b.email.lower(), hash_pw(b.password))); c.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists.")
    set_cookie(resp, cur.lastrowid); return {"id": cur.lastrowid, "name": b.name}

@app.post("/api/auth/login")
def login(b: Login, request: Request, resp: Response):
    limit("l" + request.client.host)
    r = db().execute("SELECT * FROM users WHERE email=?", (b.email.lower(),)).fetchone()
    if not r or not check_pw(b.password, r["pw"]): raise HTTPException(401, "Incorrect email or password.")
    set_cookie(resp, r["id"]); return {"id": r["id"], "name": r["name"]}

@app.post("/api/auth/logout")
def logout(resp: Response): resp.delete_cookie("session"); return {"ok": True}

@app.get("/api/auth/me")
def me(uid=Depends(user)):
    r = db().execute("SELECT id,name,email FROM users WHERE id=?", (uid,)).fetchone()
    if not r: raise HTTPException(401, "Please log in.")
    return dict(r)

# ---------- parsing ----------
SKILLS = """python java javascript typescript c c++ c# go rust php ruby kotlin swift sql mysql postgresql mongodb redis sqlite html css react angular vue nextjs node express django flask fastapi spring docker kubernetes aws azure gcp git github linux bash rest api graphql tensorflow pytorch pandas numpy scikit-learn nlp machine-learning deep-learning data-analysis excel power-bi tableau plc scada arduino raspberry-pi embedded iot matlab autocad jenkins ci/cd agile scrum testing selenium jira figma communication teamwork leadership problem-solving""".split()
ALIASES = {"machine learning": "machine-learning", "deep learning": "deep-learning", "data analysis": "data-analysis", "power bi": "power-bi",
           "scikit learn": "scikit-learn", "node.js": "node", "next.js": "nextjs", "react.js": "react", "raspberry pi": "raspberry-pi", "problem solving": "problem-solving", "ci/cd": "ci/cd"}
HEADINGS = {"summary": r"summary|objective|profile|about", "skills": r"skills|technical skills|technologies", "education": r"education|academic",
            "experience": r"experience|employment|work history|internship", "projects": r"projects?", "certifications": r"certifications?|courses|licenses",
            "achievements": r"achievements|awards|honou?rs"}

def ocr_image(img_bytes):
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(img_bytes)))
    except Exception:
        raise HTTPException(422, "We couldn't read text from this image. Try a clearer, higher-resolution scan.")

def extract_text(name, data):
    ext = Path(name).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg"):
        if not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")): raise HTTPException(400, "Please upload a PDF, DOCX, PNG or JPG file.")
        return ocr_image(data), {"pages": 1, "images": 0, "tables": 0, "ocr": True}
    if ext == ".pdf":
        if not data.startswith(b"%PDF"): raise HTTPException(400, "Please upload a PDF or DOCX file.")
        import fitz
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception:
            raise HTTPException(422, "We couldn't read this PDF.")
        text = "\n".join(p.get_text() for p in doc)
        meta = {"pages": len(doc), "images": sum(len(p.get_images()) for p in doc), "tables": sum(len(p.find_tables().tables) for p in doc)}
        if len(text.strip()) < 100:  # scanned PDF: OCR the first pages
            text = "\n".join(ocr_image(p.get_pixmap(dpi=200).tobytes("png")) for p in list(doc)[:3]); meta.update(images=0, ocr=True)
        return text, meta
    if ext == ".docx":
        if not data.startswith(b"PK"): raise HTTPException(400, "Please upload a PDF or DOCX file.")
        import docx
        try:
            d = docx.Document(io.BytesIO(data))
        except Exception:
            raise HTTPException(422, "We couldn't read this DOCX.")
        return "\n".join(p.text for p in d.paragraphs), {"pages": None, "images": len(d.inline_shapes), "tables": len(d.tables)}
    raise HTTPException(400, "Please upload a PDF, DOCX, PNG or JPG file.")

def find_skills(text):
    t = " " + text.lower() + " "
    for a, k in ALIASES.items(): t = t.replace(a, k)
    return sorted({s for s in SKILLS if re.search(r"(?<![\w+#/-])" + re.escape(s) + r"(?![\w+#-])", t)})

def parse(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    sections, cur = {}, "header"
    for l in lines:
        h = next((k for k, p in HEADINGS.items() if re.fullmatch(rf"({p})\s*:?", l.lower())), None)
        if h: cur = h; sections.setdefault(cur, []); continue
        sections.setdefault(cur, []).append(l)
    g = lambda p: (re.search(p, text, re.I) or [None])[0]
    return {"name": lines[0] if lines else "", "email": g(r"[\w.+-]+@[\w-]+\.[\w.]+"), "phone": g(r"(\+?\d[\d\s().-]{8,}\d)"),
            "linkedin": g(r"linkedin\.com/[\w/-]+"), "github": g(r"github\.com/[\w-]+"),
            "sections": {k: v for k, v in sections.items() if k != "header"}, "skills": find_skills(text)}

# ---------- deterministic scoring + ATS ----------
VERBS = "built developed designed implemented created led managed improved reduced increased automated deployed analyzed optimized integrated maintained tested configured".split()
def analyse(text, parsed, meta):
    s = parsed["sections"]; words = len(text.split())
    bullets = [l for k in ("experience", "projects") for l in s.get(k, []) if len(l.split()) > 3]
    verb_hits = sum(1 for b in bullets if b.lower().split()[0].strip("•-*") in VERBS)
    metrics = sum(1 for b in bullets if re.search(r"\d+\s*%|\d{2,}|\$\d", b))
    checks, recs = [], []
    def chk(ok, label, fix, w):
        checks.append({"label": label, "pass": bool(ok), "weight": w})
        if not ok: recs.append(fix)
    chk(parsed["email"], "Email found", "Add a professional email address in the header.", 10)
    chk(parsed["phone"], "Phone found", "Add a phone number.", 5)
    chk(parsed["linkedin"] or parsed["github"], "LinkedIn or GitHub link", "Add a LinkedIn or GitHub profile link.", 5)
    for k, lab in (("education", "Education"), ("experience", "Experience"), ("skills", "Skills"), ("projects", "Projects")):
        chk(k in s, f"{lab} heading detected", f"Add a clear '{lab}' heading so ATS software can find the section.", 10)
    chk(meta["tables"] == 0, "No tables", "Tables can scramble ATS parsing; use plain lines or bullets.", 8)
    chk(meta["images"] == 0, "No images or graphics", "Remove images, icons and logos.", 6)
    chk(not re.search(r"[^\x00-\x7F•–—‘’“”·]", text), "No unusual symbols", "Replace unusual symbols with plain text.", 5)
    chk(250 <= words <= 1000, "Reasonable length (250-1000 words)", "Aim for 250-1000 words (roughly 1-2 pages).", 6)
    chk(len(parsed["skills"]) >= 6, "At least 6 recognised skills", "List more relevant technical skills.", 10)
    ats = round(100 * sum(c["weight"] for c in checks if c["pass"]) / sum(c["weight"] for c in checks))
    verbs = verb_hits / len(bullets) if bullets else 0
    if bullets and verbs < .5: recs.append("Start more bullet points with strong action verbs (built, automated, led).")
    if bullets and metrics == 0: recs.append("Consider adding a measurable result to some bullets if you have real numbers.")
    if not bullets: recs.append("Describe experience or projects in short bullet points.")
    scores = {"skills": min(100, len(parsed["skills"]) * 9), "experience": round(min(100, (len(s.get("experience", [])) * 8) * .6 + verbs * 40)),
              "projects": min(100, len(s.get("projects", [])) * 12), "education": 90 if "education" in s else 30, "formatting": ats}
    overall = round(.25 * scores["skills"] + .25 * scores["experience"] + .15 * scores["projects"] + .1 * scores["education"] + .25 * ats)
    return {"overall_score": overall, "ats_score": ats, "scores": scores, "ats_checks": checks, "recommendations": recs,
            "stats": {"words": words, "bullets": len(bullets), "action_verb_bullets": verb_hits, "bullets_with_numbers": metrics},
            "note": "ATS score is an internal compatibility indicator, not a guarantee that any specific ATS will accept the resume."}

class AIError(Exception): pass
def llm(system, prompt, max_tokens=1000):
    if not AI_KEY: raise AIError("AI is not configured. Set the AI_API_KEY environment variable.")
    import httpx
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60, headers={"x-api-key": AI_KEY, "anthropic-version": "2023-06-01"},
                       json={"model": AI_MODEL, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status(); return r.json()["content"][0]["text"]
    except Exception:
        raise AIError("AI is temporarily unavailable. Please try again.")
NO_FAKE = "Never invent experience, employers, degrees, certifications, skills or metrics. If a metric is missing, suggest adding one instead of making one up."

# ---------- resumes ----------
def own(c, rid, uid):
    r = c.execute("SELECT * FROM resumes WHERE id=? AND user_id=?", (rid, uid)).fetchone()
    if not r: raise HTTPException(404, "Resume not found.")
    return r

@app.post("/api/resumes/upload", status_code=201)
async def upload(file: UploadFile = File(...), uid=Depends(user)):
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024: raise HTTPException(413, "Your file exceeds the maximum allowed size (5 MB).")
    text, meta = extract_text(file.filename or "", data)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 100: raise HTTPException(422, "We couldn't extract enough text from this resume. If this is a scan, try a clearer, higher-resolution copy.")
    parsed = parse(text); a = analyse(text, parsed, meta)
    c = db(); cur = c.execute("INSERT INTO resumes(user_id,filename,text,parsed,analysis) VALUES(?,?,?,?,?)",
                              (uid, Path(file.filename).name[:120], text, json.dumps(parsed), json.dumps(a))); c.commit()
    return {"id": cur.lastrowid}

@app.get("/api/resumes")
def list_resumes(uid=Depends(user)):
    rows = db().execute("SELECT id,filename,analysis,created FROM resumes WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    return [{"id": r["id"], "filename": r["filename"], "created": r["created"], "overall": json.loads(r["analysis"])["overall_score"],
             "ats": json.loads(r["analysis"])["ats_score"]} for r in rows]

@app.get("/api/resumes/{rid}")
def get_resume(rid: int, uid=Depends(user)):
    r = own(db(), rid, uid)
    return {"id": r["id"], "filename": r["filename"], "created": r["created"], "parsed": json.loads(r["parsed"]), "analysis": json.loads(r["analysis"])}

class Rename(BaseModel): filename: str = Field(min_length=1, max_length=120)
@app.patch("/api/resumes/{rid}")
def rename(rid: int, b: Rename, uid=Depends(user)):
    c = db(); own(c, rid, uid); c.execute("UPDATE resumes SET filename=? WHERE id=?", (b.filename, rid)); c.commit(); return {"ok": True}

@app.delete("/api/resumes/{rid}", status_code=204)
def delete(rid: int, uid=Depends(user)):
    c = db(); own(c, rid, uid); c.execute("DELETE FROM resumes WHERE id=?", (rid,)); c.commit()

@app.post("/api/resumes/{rid}/duplicate", status_code=201)
def duplicate(rid: int, uid=Depends(user)):
    c = db(); r = own(c, rid, uid)
    cur = c.execute("INSERT INTO resumes(user_id,filename,text,parsed,analysis) VALUES(?,?,?,?,?)", (uid, "Copy of " + r["filename"][:100], r["text"], r["parsed"], r["analysis"])); c.commit()
    return {"id": cur.lastrowid}

@app.get("/api/resumes/{a}/compare/{b}")
def compare(a: int, b: int, uid=Depends(user)):
    c = db(); ra, rb = own(c, a, uid), own(c, b, uid)
    A_, B_ = json.loads(ra["analysis"]), json.loads(rb["analysis"])
    sa, sb = set(json.loads(ra["parsed"])["skills"]), set(json.loads(rb["parsed"])["skills"])
    keys = ["overall_score", "ats_score"]
    return {"a": {"name": ra["filename"], **{k: A_[k] for k in keys}, "scores": A_["scores"]}, "b": {"name": rb["filename"], **{k: B_[k] for k in keys}, "scores": B_["scores"]},
            "only_in_a": sorted(sa - sb), "only_in_b": sorted(sb - sa), "shared": sorted(sa & sb)}

@app.post("/api/resumes/{rid}/ai-review")
def ai_review(rid: int, uid=Depends(user)):
    r = own(db(), rid, uid)
    try:
        out = llm("You are a careful resume reviewer. " + NO_FAKE, "Give 3 strengths and 3 weaknesses (short bullets) for this resume:\n\n" + r["text"][:6000])
    except AIError as e: raise HTTPException(503, str(e))
    return {"review": out}

# ---------- jobs ----------
class JobIn(BaseModel):
    title: str = Field(min_length=1, max_length=120); description: str = Field(min_length=40, max_length=20000)
@app.post("/api/jobs", status_code=201)
def add_job(b: JobIn, uid=Depends(user)):
    c = db(); cur = c.execute("INSERT INTO jobs(user_id,title,description) VALUES(?,?,?)", (uid, b.title, b.description)); c.commit(); return {"id": cur.lastrowid}
@app.get("/api/jobs")
def jobs(uid=Depends(user)):
    return [dict(r) for r in db().execute("SELECT id,title,created FROM jobs WHERE user_id=? ORDER BY id DESC", (uid,))]

STOP = set("the and for with you your our are will have has this that from their they who all any can able work team years year experience required preferred strong good knowledge skills ability using use well must should including etc".split())
@app.post("/api/jobs/{jid}/match")
def match(jid: int, resume_id: int, uid=Depends(user)):
    c = db(); r = own(c, resume_id, uid)
    j = c.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (jid, uid)).fetchone()
    if not j: raise HTTPException(404, "Job not found.")
    need, have = set(find_skills(j["description"])), set(json.loads(r["parsed"])["skills"])
    kw = lambda t: {w for w in re.findall(r"[a-z][a-z+#.-]{3,}", t.lower()) if w not in STOP}
    jk, rk = kw(j["description"]), kw(r["text"])
    jk_top = {w for w in jk if w not in need}
    skill_pct = len(need & have) / len(need) if need else None
    kw_pct = len(jk_top & rk) / len(jk_top) if jk_top else 0
    score = round(100 * (.7 * skill_pct + .3 * kw_pct)) if skill_pct is not None else round(100 * kw_pct)
    res = {"score": score, "matching_skills": sorted(need & have), "missing_skills": sorted(need - have),
           "missing_keywords": sorted(jk_top - rk)[:15], "matching_keywords": sorted(jk_top & rk)[:15],
           "confidence": "good" if len(need) >= 4 else "low - few recognisable skills in this job description",
           "note": "Keyword-based estimate. Missing items may be covered by different wording in your resume."}
    c.execute("INSERT INTO matches(resume_id,job_id,score,result) VALUES(?,?,?,?)", (resume_id, jid, score, json.dumps(res))); c.commit()
    return res

# ---------- AI ----------
class Improve(BaseModel): text: str = Field(min_length=3, max_length=2000); kind: str = "bullet"
@app.post("/api/ai/improve")
def improve(b: Improve, uid=Depends(user)):
    try: out = llm("You rewrite resume text. " + NO_FAKE + " Return only the rewritten text.", f"Improve this resume {b.kind}:\n{b.text}", 400)
    except AIError as e: raise HTTPException(503, str(e))
    return {"improved": out.strip()}
class Chat(BaseModel): message: str = Field(min_length=1, max_length=2000); resume_id: int | None = None
@app.post("/api/ai/chat")
def chat(b: Chat, uid=Depends(user)):
    ctx = ""
    if b.resume_id: ctx = "\n\nUser's resume:\n" + own(db(), b.resume_id, uid)["text"][:5000]
    try: out = llm("You are a concise career assistant. " + NO_FAKE, b.message + ctx)
    except AIError as e: raise HTTPException(503, str(e))
    c = db(); c.executemany("INSERT INTO messages(user_id,role,content) VALUES(?,?,?)", [(uid, "user", b.message), (uid, "assistant", out)]); c.commit()
    return {"reply": out}

@app.get("/api/ai/history")
def chat_history(uid=Depends(user)):
    return [dict(r) for r in db().execute("SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 40", (uid,))][::-1]

@app.delete("/api/auth/account", status_code=204)
def delete_account(resp: Response, uid=Depends(user)):
    c = db(); c.execute("DELETE FROM users WHERE id=?", (uid,)); c.commit(); resp.delete_cookie("session")

class Reset(BaseModel): email: str; new_password: str = Field(min_length=8, max_length=128); code: str
@app.post("/api/auth/reset-password")
def reset_password(b: Reset, request: Request):
    """Email isn't wired up, so resets are authorised by a server-side RESET_CODE the admin shares (e.g. with the user in class)."""
    limit("p" + request.client.host, 5)
    code = os.getenv("RESET_CODE")
    if not code or not hmac.compare_digest(b.code, code): raise HTTPException(403, "Reset code is invalid or password reset is not enabled.")
    c = db(); cur = c.execute("UPDATE users SET pw=? WHERE email=?", (hash_pw(b.new_password), b.email.lower())); c.commit()
    if not cur.rowcount: raise HTTPException(404, "No account with this email.")
    return {"ok": True}

@app.get("/health")
def health(): return {"status": "ok", "ai_configured": bool(AI_KEY)}

@app.get("/")
def index(): return FileResponse(Path(__file__).parent / "static" / "index.html")
