import os, io, tempfile
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
from fastapi.testclient import TestClient
import docx, app as A
c = TestClient(A.app)
RESUME = ["Asha Patil","asha@example.com  +91 98765 43210  github.com/asha","Summary","Diploma student in electronics and computer engineering.","Skills","Python, SQL, Git, Docker, Linux, React, REST API, PLC",
 "Education","Diploma in Electronics and Computer Engineering","Experience","Built a PLC monitoring tool that reduced manual checks by 30%","Automated data entry reports using Python scripts","Projects","Developed a resume analyzer using FastAPI and React"]
def mk():
    d = docx.Document()
    for l in RESUME * 3: d.add_paragraph(l)
    b = io.BytesIO(); d.save(b); return b.getvalue()
def test_flow():
    assert c.post("/api/resumes/upload", files={"file": ("a.docx", mk())}).status_code == 401
    r = c.post("/api/auth/register", json={"name": "A", "email": "a@x.com", "password": "password1"}); assert r.status_code == 201
    assert c.post("/api/auth/register", json={"name": "A", "email": "a@x.com", "password": "password1"}).status_code == 409
    assert c.post("/api/resumes/upload", files={"file": ("a.txt", b"hello")}).status_code == 400
    assert c.post("/api/resumes/upload", files={"file": ("a.docx", b"PKnotreal")}).status_code == 422
    r = c.post("/api/resumes/upload", files={"file": ("a.docx", mk())}); assert r.status_code == 201, r.text
    rid = r.json()["id"]; d = c.get(f"/api/resumes/{rid}").json()
    assert "python" in d["parsed"]["skills"] and d["parsed"]["email"] == "asha@example.com" and 0 < d["analysis"]["ats_score"] <= 100
    j = c.post("/api/jobs", json={"title": "Dev", "description": "Looking for Python, SQL, AWS and Kubernetes experience with Docker and Git."}).json()["id"]
    m = c.post(f"/api/jobs/{j}/match?resume_id={rid}").json()
    assert "aws" in m["missing_skills"] and "python" in m["matching_skills"]
    assert c.post("/api/ai/improve", json={"text": "Worked on Python"}).status_code in (200, 503)
    c2 = TestClient(A.app); c2.post("/api/auth/register", json={"name": "B", "email": "b@x.com", "password": "password2"})
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
    c.post("/api/auth/register", json={"name": "O", "email": "o@x.com", "password": "password1"})
    r = c.post("/api/resumes/upload", files={"file": ("scan.png", b.getvalue())}); assert r.status_code == 201, r.text
    d = c.get(f"/api/resumes/{r.json()['id']}").json()
    assert "python" in d["parsed"]["skills"]
    rid = r.json()["id"]; dup = c.post(f"/api/resumes/{rid}/duplicate").json()["id"]
    cm = c.get(f"/api/resumes/{rid}/compare/{dup}").json(); assert cm["only_in_a"] == [] and cm["shared"]
    assert c.get("/api/ai/history").status_code == 200
    assert c.post("/api/auth/reset-password", json={"email": "o@x.com", "new_password": "newpass123", "code": "x"}).status_code == 403
    assert c.delete("/api/auth/account").status_code == 204 and c.get("/api/auth/me").status_code == 401
