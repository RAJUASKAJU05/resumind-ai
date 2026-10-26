import os, io, tempfile
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
from fastapi.testclient import TestClient
import docx, app as A
c = TestClient(A.app)

import pytest
@pytest.fixture(autouse=True)
def _reset_rate_limits():
    A._hits.clear()
    yield
RESUME = ["Asha Patil","asha@example.com  +91 98765 43210  github.com/asha","Summary","Diploma student in electronics and computer engineering.","Skills","Python, SQL, Git, Docker, Linux, React, REST API, PLC",
 "Education","Diploma in Electronics and Computer Engineering","Experience","Built a PLC monitoring tool that reduced manual checks by 30%","Automated data entry reports using Python scripts","Projects","Developed a resume analyzer using FastAPI and React"]
def mk():
    d = docx.Document()
    for l in RESUME * 3: d.add_paragraph(l)
    b = io.BytesIO(); d.save(b); return b.getvalue()

def register(client, name, email, password="password1"):
    """Solves the real CAPTCHA, like an actual client must."""
    cap = client.get("/api/auth/captcha").json()
    a, b = [int(x) for x in cap["question"].replace("=", "").replace("?", "").split("+")]
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password,
                                                     "captcha_token": cap["token"], "captcha_answer": str(a + b)})
def test_flow():
    assert c.post("/api/resumes/upload", files={"file": ("a.docx", mk())}).status_code == 401
    r = r = register(c, "A", "a@x.com"); assert r.status_code == 201
    assert register(c, "A", "a@x.com").status_code == 409
    assert c.post("/api/resumes/upload", files={"file": ("a.txt", b"hello")}).status_code == 400
    assert c.post("/api/resumes/upload", files={"file": ("a.docx", b"PKnotreal")}).status_code == 422
    r = c.post("/api/resumes/upload", files={"file": ("a.docx", mk())}); assert r.status_code == 201, r.text
    rid = r.json()["id"]; d = c.get(f"/api/resumes/{rid}").json()
    assert "python" in d["parsed"]["skills"] and d["parsed"]["email"] == "asha@example.com" and 0 < d["analysis"]["ats_score"] <= 100
    j = c.post("/api/jobs", json={"title": "Dev", "description": "Looking for Python, SQL, AWS and Kubernetes experience with Docker and Git."}).json()["id"]
    m = c.post(f"/api/jobs/{j}/match?resume_id={rid}").json()
    assert "aws" in m["missing_skills"] and "python" in m["matching_skills"]
    assert c.post("/api/ai/improve", json={"text": "Worked on Python"}).status_code in (200, 503)
    c2 = TestClient(A.app); register(c2, "B", "b@x.com", "password2")
    assert c2.get(f"/api/resumes/{rid}").status_code == 404  # authorization
    assert c.delete(f"/api/resumes/{rid}").status_code == 204 and c.get(f"/api/resumes/{rid}").status_code == 404

def test_ocr_image_and_extras():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1400, 900), "white"); d = ImageDraw.Draw(img)
    f = ImageFont.load_default(size=34)
    y = 30
    for l in ["Ravi Kumar", "ravi@example.com 9876543210", "Skills", "Python SQL Git Docker Linux React", "Education", "Diploma in Computer Engineering", "Experience", "Built a Python tool for automated reports", "Projects", "Developed a web app using React and FastAPI"]:
        d.text((40, y), l, fill="black", font=f); y += 70
    b = io.BytesIO(); img.save(b, "PNG")
    register(c, "O", "o@x.com")
    r = c.post("/api/resumes/upload", files={"file": ("scan.png", b.getvalue())}); assert r.status_code == 201, r.text
    d = c.get(f"/api/resumes/{r.json()['id']}").json()
    assert "python" in d["parsed"]["skills"]
    rid = r.json()["id"]; dup = c.post(f"/api/resumes/{rid}/duplicate").json()["id"]
    cm = c.get(f"/api/resumes/{rid}/compare/{dup}").json(); assert cm["only_in_a"] == [] and cm["shared"]
    assert c.get("/api/ai/history").status_code == 200
    assert c.post("/api/auth/reset-password", json={"email": "o@x.com", "new_password": "newpass123", "code": "x"}).status_code == 403
    assert c.delete("/api/auth/account").status_code == 204 and c.get("/api/auth/me").status_code == 401


def test_flow_features():
    k = TestClient(A.app); register(k, "F", "f@x.com")
    assert [s["done"] for s in k.get("/api/flow").json()] == [False] * 7
    rid = k.post("/api/resumes/upload", files={"file": ("a.docx", mk())}).json()["id"]
    jid = k.post("/api/jobs", json={"title": "Dev", "description": "We need Python, SQL, AWS, Kubernetes and Docker experience for this role."}).json()["id"]
    k.post(f"/api/jobs/{jid}/match?resume_id={rid}")
    gaps = k.get("/api/skill-gaps").json(); assert {g["skill"] for g in gaps} >= {"aws", "kubernetes"}
    q = k.post("/api/interview/questions", json={"resume_id": rid, "job_id": jid}).json()
    assert len(q["questions"]) >= 6 and any("aws" in x.lower() for x in q["questions"])
    good = "At my internship I built a Python script to automate reports, which reduced manual checking by 30% and I learned to test it carefully before handing it to the team. " * 2
    assert k.post("/api/interview/feedback", json={"question": q["questions"][0], "answer": good}).json()["score"] >= 60
    assert k.post("/api/interview/feedback", json={"question": q["questions"][0], "answer": "yes"}).json()["score"] < 40
    assert k.post("/api/applications", json={"company": "Acme", "role": "Dev", "status": "Bogus"}).status_code == 422
    aid = k.post("/api/applications", json={"company": "Acme", "role": "Dev", "resume_id": rid, "job_id": jid}).json()["id"]
    assert k.patch(f"/api/applications/{aid}", json={"status": "Applied"}).status_code == 200
    assert k.get("/api/applications").json()[0]["status"] == "Applied"
    other = TestClient(A.app); register(other, "G", "g@x.com")
    assert other.patch(f"/api/applications/{aid}", json={"status": "Offer"}).status_code == 404
    assert other.post("/api/applications", json={"company": "X", "role": "Y", "resume_id": rid}).status_code == 404
    assert [s["done"] for s in k.get("/api/flow").json()] == [True, True, True, True, False, True, True]
    assert k.delete(f"/api/applications/{aid}").status_code == 204


def test_parser_regressions():
    """Bugs found by running real-world resumes through the parser."""
    p = A.parse(A.clean("Priya Sharma\npriya@x.com (+91) 98765-43210\nGitHub: @priya\nWork Experience\nBuilt tools\nTECHNICAL SKILLS\nPython\nHonors & Awards\nWon a prize\nProject Manager\nLed a team"))
    assert p["phone"].startswith("(+91)") and p["has_profile_link"]
    assert {"experience", "skills", "achievements"} <= set(p["sections"]) and "projects" not in p["sections"]  # 'Project Manager' is a job title, not a heading
    assert A.find_skills("Let us go to the rest of the express lane in spring") == []  # ordinary English words are not skills
    assert A.find_skills("Go (golang), Node.js, Spring Boot and REST APIs") == ["golang", "node", "rest-api", "spring-boot"]
    assert "\xad" not in A.clean("high\xadimpact") and A.is_action("Developed") and A.is_action("Built") and not A.is_action("Responsible")
    ok = A.analyse("Zoë Ünal José naïve résumé " * 60, p, {"tables": 0, "images": 0})
    assert next(c for c in ok["ats_checks"] if "icon" in c["label"])["pass"]  # accented letters are fine
    bad = A.analyse("Phone \u2706 mail \u2709 " * 60, p, {"tables": 0, "images": 0})
    assert not next(c for c in bad["ats_checks"] if "icon" in c["label"])["pass"]

def test_keywords_clean_and_errors():
    k = TestClient(A.app); register(k, "K", "k@x.com")
    rid = k.post("/api/resumes/upload", files={"file": ("a.docx", mk())}).json()["id"]
    jid = k.post("/api/jobs", json={"title": "Dev", "description": "Need CI pipelines. Knowledge of Terraform and Python is a plus. Strong ownership."}).json()["id"]
    m = k.post(f"/api/jobs/{jid}/match?resume_id={rid}").json()
    assert not any(w.endswith(".") for w in m["missing_keywords"] + m["matching_keywords"]) and "plus" not in m["missing_keywords"]
    assert k.post("/api/jobs", json={"title": "", "description": "x"}).status_code == 422
    import fitz
    e = fitz.open(); e.new_page().insert_text((50, 80), "Secret " * 40); b = e.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    r = k.post("/api/resumes/upload", files={"file": ("p.pdf", b)}); assert r.status_code == 422 and "password" in r.json()["detail"]
    assert k.post("/api/resumes/upload", files={"file": ("x.pdf", b"not a pdf")}).status_code == 400
    assert k.post("/api/resumes/upload", files={"file": ("big.pdf", b"%PDF-" + b"0" * (6 * 1024 * 1024))}).status_code == 413

def test_captcha_and_honeypot():
    """CAPTCHA must actually be solved, tokens are one-time-use, and the honeypot blocks bots."""
    cap = c.get("/api/auth/captcha").json()
    a, b = [int(x) for x in cap["question"].replace("=", "").replace("?", "").split("+")]
    # wrong answer rejected
    assert c.post("/api/auth/register", json={"name": "X", "email": "capbad@x.com", "password": "password1",
                   "captcha_token": cap["token"], "captcha_answer": str(a + b + 1)}).status_code == 400
    # missing/invalid token rejected
    assert c.post("/api/auth/register", json={"name": "X", "email": "capmiss@x.com", "password": "password1"}).status_code == 400
    # honeypot filled -> rejected even with a correct answer
    cap2 = c.get("/api/auth/captcha").json()
    a2, b2 = [int(x) for x in cap2["question"].replace("=", "").replace("?", "").split("+")]
    assert c.post("/api/auth/register", json={"name": "Bot", "email": "bot@x.com", "password": "password1",
                   "captcha_token": cap2["token"], "captcha_answer": str(a2 + b2), "website": "http://spam.example"}).status_code == 400
    # a real solve succeeds
    assert register(c, "Real", "realcap@x.com").status_code == 201
    # the same token cannot be reused (replay protection)
    cap3 = c.get("/api/auth/captcha").json()
    a3, b3 = [int(x) for x in cap3["question"].replace("=", "").replace("?", "").split("+")]
    body = {"name": "R2", "email": "replay1@x.com", "password": "password1", "captcha_token": cap3["token"], "captcha_answer": str(a3 + b3)}
    assert c.post("/api/auth/register", json=body).status_code == 201
    body["email"] = "replay2@x.com"
    assert c.post("/api/auth/register", json=body).status_code == 400  # token already consumed

def test_rate_limiting():
    k = TestClient(A.app); register(k, "RL", "rl@x.com")
    rid = k.post("/api/resumes/upload", files={"file": ("a.docx", mk())}).json()["id"]
    hit = False
    for _ in range(25):
        r = k.post(f"/api/resumes/{rid}/ai-review")
        if r.status_code == 429: hit = True; break
    assert hit, "AI route should rate-limit a burst of requests from one user"

def test_auth_required_on_every_protected_route():
    """Every data-bearing endpoint must reject an unauthenticated caller with 401 — a permanent
    regression test so a future route can't accidentally be added without Depends(user)."""
    anon = TestClient(A.app)
    protected = [
        ("get", "/api/resumes"), ("get", "/api/resumes/1"), ("patch", "/api/resumes/1"), ("delete", "/api/resumes/1"),
        ("post", "/api/resumes/1/duplicate"), ("get", "/api/resumes/1/compare/2"), ("post", "/api/resumes/1/ai-review"),
        ("post", "/api/jobs"), ("get", "/api/jobs"), ("post", "/api/jobs/1/match"),
        ("post", "/api/ai/improve"), ("post", "/api/ai/chat"), ("get", "/api/ai/history"),
        ("delete", "/api/auth/account"), ("get", "/api/matches"), ("post", "/api/applications"),
        ("get", "/api/applications"), ("patch", "/api/applications/1"), ("delete", "/api/applications/1"),
        ("get", "/api/skill-gaps"), ("post", "/api/interview/questions"), ("post", "/api/interview/feedback"),
        ("get", "/api/flow"), ("get", "/api/auth/security-log"),
    ]
    for method, path in protected:
        kwargs = {"json": {}} if method in ("post", "patch") else {}
        r = getattr(anon, method)(path, **kwargs)
        assert r.status_code == 401, f"{method.upper()} {path} returned {r.status_code}, expected 401 without login"

def test_idor_blocked_everywhere():
    """One user must never read or modify another user's resumes, jobs, matches, applications or interviews."""
    k = TestClient(A.app); register(k, "Owner", "owner@x.com")
    other = TestClient(A.app); register(other, "Stranger", "stranger@x.com")
    rid = k.post("/api/resumes/upload", files={"file": ("a.docx", mk())}).json()["id"]
    jid = k.post("/api/jobs", json={"title": "Dev", "description": "Python, SQL, AWS, Docker and Kubernetes experience needed here."}).json()["id"]
    aid = k.post("/api/applications", json={"company": "Acme", "role": "Dev", "resume_id": rid}).json()["id"]
    assert other.get(f"/api/resumes/{rid}").status_code == 404
    assert other.patch(f"/api/resumes/{rid}", json={"filename": "hacked.docx"}).status_code == 404
    assert other.delete(f"/api/resumes/{rid}").status_code == 404
    assert other.post(f"/api/resumes/{rid}/duplicate").status_code == 404
    assert other.post(f"/api/jobs/{jid}/match?resume_id={rid}").status_code == 404
    assert other.post("/api/interview/questions", json={"resume_id": rid, "job_id": jid}).status_code == 404
    assert other.patch(f"/api/applications/{aid}", json={"status": "Offer"}).status_code == 404
    assert other.delete(f"/api/applications/{aid}").status_code == 404
    # owner's own data is untouched after all the attempted attacks
    assert k.get(f"/api/resumes/{rid}").status_code == 200
    assert k.get("/api/applications").json()[0]["id"] == aid

def test_audit_log_records_sensitive_actions():
    k = TestClient(A.app)
    assert register(k, "Aud", "aud@x.com").status_code == 201
    k2 = TestClient(A.app); k2.post("/api/auth/login", json={"email": "aud@x.com", "password": "wrongpass"})
    k.post("/api/auth/login", json={"email": "aud@x.com", "password": "password1"})
    rid = k.post("/api/resumes/upload", files={"file": ("a.docx", mk())}).json()["id"]
    k.delete(f"/api/resumes/{rid}")
    log = k.get("/api/auth/security-log").json()
    events = {e["event"] for e in log}
    assert {"register", "login", "login_failed", "resume_deleted"} <= events

def test_cors_headers_present():
    r = c.options("/api/auth/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    allow = r.headers.get("access-control-allow-origin", "")
    assert allow != "https://evil.example" and allow != "*"
