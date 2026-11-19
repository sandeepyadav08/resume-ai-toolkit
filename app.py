"""
Resume Matcher - job preparation toolkit (free, uses Google Gemini free tier).

Features
  1. Match score, missing skills, better resume lines, summary, cover letter
  2. Full rewritten resume (download as PDF from the browser)
  3. Mock interview for this job, with feedback on every answer
  4. 7-day learning plan for missing skills
  5. Recruiter / LinkedIn / thank-you messages
  6. ATS (resume-scanner) check
  7. Read a job description from a link
  History of results is stored in the user's own browser.

Run locally:  python app.py   ->  http://localhost:8000
"""

import ipaddress
import os
import re
import socket
import urllib.request
from html import unescape
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel
from pypdf import PdfReader

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")  # also accept the key from the parent folder

# First model is tried first; if it is busy, slow or missing, the next one is used.
# The "lite" models are lighter and usually answer fast even when Google is busy.
MODELS = list(dict.fromkeys(m for m in [
    os.environ.get("GEMINI_MODEL", "").strip(),
    "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-flash-lite"] if m))
RETRY_CODES = (404, 500, 502, 503, 504)
AI_TIMEOUT_MS = 45_000  # per model; then the next model is tried
ACCESS_CODE = os.environ.get("ACCESS_CODE", "").strip()  # optional password when online

# Without a key the site still opens; AI requests return a clear error instead of crashing.
_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
gemini = genai.Client(api_key=_api_key, http_options=types.HttpOptions(
    timeout=AI_TIMEOUT_MS)) if _api_key else None
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB (Vercel allows at most 4.5 MB per request)


class UserError(Exception):
    """An error message that can be shown to the user as-is."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@app.errorhandler(UserError)
def user_error(e: UserError):
    return jsonify(error=str(e)), e.status


@app.errorhandler(413)
def too_big(_):
    return jsonify(error="The file is larger than 4 MB."), 413


@app.before_request
def check_access_code():
    if ACCESS_CODE and request.method == "POST" \
            and request.headers.get("X-Access-Code", "") != ACCESS_CODE:
        return jsonify(error="ACCESS_CODE", message="Wrong access code."), 401


def ask_ai(contents, schema: type[BaseModel]):
    """Call Gemini, get back a `schema` object. Tries the next model if one is busy."""
    config = types.GenerateContentConfig(response_mime_type="application/json",
                                         response_schema=schema)
    if gemini is None:
        raise UserError("The server has no GEMINI_API_KEY set. "
                        "Add it in the hosting settings and redeploy.", 500)
    try:
        for i, model in enumerate(MODELS):
            last = i == len(MODELS) - 1
            try:
                response = gemini.models.generate_content(model=model, contents=contents,
                                                          config=config)
                break
            except genai_errors.APIError as e:
                if e.code in RETRY_CODES and not last:
                    print(f"{model} not available ({e.code}), trying next model...")
                    continue
                raise
            except Exception as e:  # network timeout / connection problem
                if not last:
                    print(f"{model} timed out ({type(e).__name__}), trying next model...")
                    continue
                raise UserError("The AI is taking too long to respond. "
                                "Please try again in a minute.", 504)
    except genai_errors.APIError as e:
        if e.code == 429:
            raise UserError("The free AI limit has been reached. Please try again in 1-2 minutes.", 429)
        if e.code in (500, 502, 503, 504):
            raise UserError("Google's AI is busy right now. Please try again in a minute.", 503)
        if e.code in (400, 403) and "API key" in str(e):
            raise UserError("The Gemini API key is invalid. Please check the .env file.", 500)
        raise UserError(f"The AI did not respond: {e.message or e}", 502)

    if response.parsed is not None:
        return response.parsed
    try:
        return schema.model_validate_json(response.text or "")
    except ValueError:
        raise UserError("Could not read the AI's response. Please try again.", 502)


def field(name: str, min_len: int, message: str) -> str:
    data = request.get_json(silent=True) or {}
    value = str(data.get(name) or request.form.get(name) or "").strip()
    if len(value) < min_len:
        raise UserError(message)
    return value[:20000]


HONESTY_RULES = """Honesty rules (very important):
- NEVER invent experience, companies, numbers, tools or skills the resume does not show.
- Do NOT add new activities or claims (e.g. "optimised", "designed schema", "led", "critical",
  "scalable", "cross-functional", "improved performance") unless the resume says so."""


# ------------------------------------------------------------ 1. ANALYZE + ATS
class BulletFix(BaseModel):
    original: str
    improved: str
    why: str


class Analysis(BaseModel):
    job_title: str
    match_score: int
    verdict: str
    matched_skills: list[str]
    missing_skills: list[str]
    keywords_to_add: list[str]
    bullet_fixes: list[BulletFix]
    summary_rewrite: str
    cover_letter: str
    interview_tips: list[str]


ANALYZE_PROMPT = """You are an expert technical recruiter and resume coach in India.
Compare the candidate's RESUME with the JOB DESCRIPTION{company}.

""" + HONESTY_RULES + """
- Improved lines keep EXACTLY the same facts; only make them clearer and stronger (better
  action verb, clearer wording, tech already named in the resume). If an extra detail would
  help, write it as a question in square brackets for the candidate to confirm, e.g.
  "[Did you optimise the queries?]". Unknown numbers: use [X%] or [N users].
- The cover letter follows the same rule: only facts that are in the resume.

Fields:
- job_title: short job title from the job description.
- match_score: honest 0-100 based on must-have skills, experience level and domain.
- matched_skills / missing_skills: short skill names from the job description.
- keywords_to_add: job keywords the candidate could add IF they truly have them.
- bullet_fixes: pick the 4-6 weakest or most relevant resume lines and improve them.
- summary_rewrite: 2-3 line professional summary in English targeted at this job.
- cover_letter: 150-220 words, English, signed with the candidate's name from the resume.
- verdict, why, interview_tips: simple, clear English.
- interview_tips: 4-5 likely interview topics for this job and how to prepare.

JOB DESCRIPTION:
{job}

RESUME:
{resume}
"""


def pdf_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:6]).strip()
    except Exception:
        raise UserError("This PDF could not be opened. Try another PDF or paste the text.")


def ats_check(resume: str, from_pdf: bool, matched: int, missing: int) -> dict:
    """Simple, explainable checks that resume-scanning software (ATS) cares about."""
    words = len(resume.split())
    lower = resume.lower()
    odd = sum(1 for ch in resume if ord(ch) > 0x2000 and not ch.isalpha())
    coverage = round(100 * matched / (matched + missing)) if matched + missing else 0
    tokens = resume.split()
    letters = sum(ch.isalpha() for ch in resume)
    readable = (len(resume) >= 100 and letters / max(1, len(resume.replace(" ", ""))) > 0.6
                and sum(len(t) for t in tokens) / max(1, len(tokens)) < 12)
    checks = [
        (readable,
         "Text was read correctly from the PDF" if from_pdf else "Resume text received",
         "The text could not be read cleanly (scanned image, photo or complex layout). An ATS may misread it - export a simple PDF from Word or Google Docs."),
        (bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", resume)), "Email address found", "No email address found - add one at the top"),
        (bool(re.search(r"(\+?\d[\d\s-]{8,}\d)", resume)), "Phone number found", "No phone number found"),
        (bool(re.search(r"\b(experience|employment|work history|internship)", lower)),
         "Experience section found", "Add a section titled 'Experience' (ATS looks for this heading)"),
        (bool(re.search(r"\beducation\b", lower)), "Education section found", "Add a section titled 'Education'"),
        (bool(re.search(r"\b(skills|technical skills)\b", lower)), "Skills section found", "Add a section titled 'Skills'"),
        (250 <= words <= 900, f"Good length ({words} words)",
         f"Length is {words} word{'' if words == 1 else 's'} - 1-2 pages (250-900 words) works best"),
        (odd < 15, "No unusual symbols or icons",
         "Too many icons or special symbols - an ATS may misread them; use plain text"),
        (coverage >= 60, f"{coverage}% of the job's skills appear in your resume",
         f"Only {coverage}% of the job's skills appear in your resume - add the ones you genuinely have"),
    ]
    passed = sum(1 for ok, _, _ in checks if ok)
    return {"score": round(100 * passed / len(checks)),
            "checks": [{"ok": ok, "text": good if ok else bad} for ok, good, bad in checks]}


@app.get("/")
def index():
    return render_template("index.html", needs_code=bool(ACCESS_CODE))


@app.post("/analyze")
def analyze():
    job = field("job_text", 50, "Please paste the full job description (at least 2-3 lines).")
    company = (request.form.get("company") or "").strip()[:100]
    resume_file = request.files.get("resume_file")
    from_pdf = bool(resume_file and resume_file.filename)
    if from_pdf:
        if not resume_file.filename.lower().endswith(".pdf"):
            raise UserError("Please upload your resume as a PDF, or paste the text.")
        resume = pdf_to_text(resume_file.read())
        if len(resume) < 100:
            raise UserError("Could not extract text from this PDF (it may be scanned). "
                            "Please copy and paste your resume text instead.")
    else:
        resume = field("resume_text", 100, "Please upload your resume PDF or paste the full text.")

    result = ask_ai(ANALYZE_PROMPT.format(
        job=job, resume=resume, company=f" for the company {company}" if company else ""), Analysis)
    result.match_score = max(0, min(100, result.match_score))
    out = result.model_dump()
    out["ats"] = ats_check(resume, from_pdf, len(result.matched_skills), len(result.missing_skills))
    out["resume_text"] = resume  # browser keeps it for the other tools
    return jsonify(out)


# ---------------------------------------------------------- 2. FULL NEW RESUME
class Experience(BaseModel):
    title: str
    company: str
    dates: str
    bullets: list[str]


class Project(BaseModel):
    name: str
    bullets: list[str]


class ResumeDoc(BaseModel):
    name: str
    headline: str
    contact: str
    summary: str
    skills: list[str]
    experience: list[Experience]
    projects: list[Project]
    education: list[str]
    certifications: list[str]


@app.post("/rewrite")
def rewrite():
    data = request.get_json(silent=True) or {}
    resume = field("resume_text", 100, "Please run an analysis first.")
    job = field("job_text", 50, "Job description is missing.")
    answers = "\n".join(f"- {q} -> {a}" for q, a in (data.get("answers") or {}).items()
                        if str(a).strip())[:5000]
    prompt = f"""Rewrite this candidate's resume so it is targeted at the job below.
{HONESTY_RULES}
- Use the candidate's ANSWERS below for any extra facts/numbers. If a detail was asked
  but not answered, leave that detail out completely. The output must contain NO square
  brackets and NO placeholders.
- Keep every real job, project, degree and skill from the original resume.
- Put the job's keywords first in skills, but only skills the resume shows.
- Bullets: start with an action verb, one line each, 3-5 per job.
- English only. contact = email | phone | city | LinkedIn/GitHub (only those in resume).
- Leave lists empty if the resume has nothing for them.

JOB DESCRIPTION:
{job}

ORIGINAL RESUME:
{resume}

CANDIDATE'S ANSWERS:
{answers or "(none)"}
"""
    return jsonify(ask_ai(prompt, ResumeDoc).model_dump())


# ------------------------------------------------------------ 3. MOCK INTERVIEW
class Feedback(BaseModel):
    score: int          # 0 = no answer to grade yet
    good: str
    improve: str
    better_answer: str


class InterviewTurn(BaseModel):
    feedback: Feedback
    next_question: str
    done: bool
    final_summary: str


MAX_QUESTIONS = 5


@app.post("/interview")
def interview():
    data = request.get_json(silent=True) or {}
    resume = field("resume_text", 100, "Please run an analysis first.")
    job = field("job_text", 50, "Job description is missing.")
    turns = [t for t in (data.get("turns") or []) if isinstance(t, dict)][:MAX_QUESTIONS]
    transcript = "\n".join(f"Q{i + 1}: {t.get('q', '')}\nA{i + 1}: {t.get('a', '')}"
                           for i, t in enumerate(turns))[:12000]
    finished = len(turns) >= MAX_QUESTIONS
    prompt = f"""You are a friendly but honest interviewer in India for the job below.
The candidate's resume is given. Ask realistic questions: mix of technical (from the job's
must-have skills), project/experience based (from the resume) and 1 behavioural question.

Interview so far:
{transcript or "(not started)"}

Now:
- feedback: {"grade the LAST answer: score 1-10, what was good, what to improve (clear, encouraging English, addressed to the candidate as 'you'), and better_answer = a model answer in English the candidate could say. better_answer must use ONLY facts from the resume and the candidate's own answer - do not add claims like 'scalable', 'secured endpoints', 'improved performance'. For pure technical/concept questions, give a correct concise explanation instead." if turns else "this is the start, so set score 0 and leave the text fields empty."}
- {"done: true. next_question: empty. final_summary: overall feedback in English (strengths, weak areas, what to study), 4-6 lines." if finished else f"done: false. next_question: question number {len(turns) + 1} of {MAX_QUESTIONS}, one question only, do not repeat earlier topics. final_summary: empty."}

JOB DESCRIPTION:
{job}

RESUME:
{resume}
"""
    turn = ask_ai(prompt, InterviewTurn)
    turn.done = finished
    turn.feedback.score = max(0, min(10, turn.feedback.score))
    return jsonify(turn.model_dump())


# ------------------------------------------------------------ 4. LEARNING PLAN
class Day(BaseModel):
    day: int
    focus: str
    tasks: list[str]
    search_queries: list[str]


class LearningPlan(BaseModel):
    days: list[Day]
    mini_project: str
    resume_line: str


@app.post("/plan")
def plan():
    data = request.get_json(silent=True) or {}
    skills = [str(s)[:60] for s in (data.get("skills") or [])][:8]
    if not skills:
        raise UserError("No missing skills - great job! 🎉")
    job = field("job_text", 50, "Job description is missing.")
    prompt = f"""Make a practical 7-day learning plan (1-2 hours per day) for a candidate in
India to learn these missing skills for the job below: {", ".join(skills)}.
Most important (must-have) skills first.
- days: exactly 7 items. focus = skill/topic, tasks = 2-4 concrete steps (English).
- search_queries: 1-2 YouTube search phrases per day (English).
  Do NOT write any URLs.
- mini_project: one small project (English, 2-3 lines) that uses these skills and can go
  on the resume and GitHub.
- resume_line: one English resume bullet the candidate can add AFTER building that project.

JOB DESCRIPTION:
{job}
"""
    return jsonify(ask_ai(prompt, LearningPlan).model_dump())


# ---------------------------------------------------------------- 5. MESSAGES
class Messages(BaseModel):
    linkedin_note: str
    recruiter_message: str
    thank_you_email: str


@app.post("/messages")
def messages():
    data = request.get_json(silent=True) or {}
    resume = field("resume_text", 100, "Please run an analysis first.")
    job = field("job_text", 50, "Job description is missing.")
    company = str(data.get("company") or "the company")[:100]
    prompt = f"""Write three short English messages for this candidate applying to {company}.
{HONESTY_RULES}
- linkedin_note: LinkedIn connection request to the recruiter, MAX 280 characters.
- recruiter_message: LinkedIn/WhatsApp message to the recruiter, 60-100 words, mention the
  role and 2 real matching skills from the resume, ask for a chance to interview.
- thank_you_email: email after the interview, with a "Subject:" line first, 80-120 words,
  use [Interviewer name] as the only placeholder.
Sign with the candidate's name from the resume. Polite, confident, not over-formal.

JOB DESCRIPTION:
{job}

RESUME:
{resume}
"""
    return jsonify(ask_ai(prompt, Messages).model_dump())


# --------------------------------------------------------- 6. JOB FROM A LINK
def _check_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UserError("Please enter a valid link (starting with https://).")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise UserError("Could not find this website. Please check the link.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise UserError("This link is not allowed.")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@app.post("/fetch-job")
def fetch_job():
    url = field("url", 8, "Please enter the job link.")
    _check_public(url)
    opener = urllib.request.build_opener(_SafeRedirect)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with opener.open(req, timeout=15) as r:
            if "html" not in r.headers.get("Content-Type", "") and \
                    "text" not in r.headers.get("Content-Type", ""):
                raise UserError("No job page found at this link.")
            raw = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", "ignore")
    except UserError:
        raise
    except Exception:
        raise UserError("Could not open this page. Please copy and paste the description.")

    raw = re.sub(r"<(script|style|noscript|svg|header|footer|nav)\b.*?</\1>", " ", raw,
                 flags=re.S | re.I)
    raw = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", raw, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", " ", raw))
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if len(ln) > 2)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 300 or re.search(r"\b(sign in|log in|login)\b to (view|continue|apply)",
                                    text, re.I) and len(text) < 1500:
        raise UserError("This site needs a login, or the page could not be read. "
                        "Please copy and paste the job description.")
    return jsonify(text=text[:12000])


if __name__ == "__main__":
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key or "xxxx" in key:
        print("⚠️  GEMINI_API_KEY is not set. Add a free key to the .env file: "
              "https://aistudio.google.com/apikey")
    port = int(os.environ.get("PORT", 8000))
    print(f"👉 Open in your browser: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
