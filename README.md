# Resume Matcher

A free AI career assistant. Paste your resume (or upload a PDF) and a job description, and it helps you prepare for that job.

## Features

| Feature | What you get |
|---|---|
| Match score | A score out of 100, matched and missing skills, stronger resume lines, a new summary and a cover letter |
| ATS check | Whether resume-screening software (ATS) can read your resume properly |
| Tailored resume | A full resume rewritten for the job, downloadable as PDF. It asks for missing details instead of inventing them |
| Mock interview | 5 questions for this role, with a score, feedback and a model answer after each one |
| Learning plan | A 7-day plan for your missing skills, with YouTube searches and a portfolio project |
| Messages | A LinkedIn connection note, a recruiter message and a post-interview thank-you email |
| Job link import | Paste a job link instead of the description (sites that need a login won't work) |
| History | Past results are saved in your own browser only, never on the server |

## Run locally

You need Python 3.10 or newer and a free Gemini API key from https://aistudio.google.com/apikey.

```bash
cd resume-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "GEMINI_API_KEY=your-key-here" > .env
python app.py
```

Open **http://localhost:8000**.

Next time, you only need:

```bash
cd resume-matcher
source .venv/bin/activate
python app.py
```

## Settings

Put these in a `.env` file in this folder (or in its parent folder). `.env` is git-ignored, so your key is never committed.

| Variable | Required | What it does |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Your Gemini key. The app will not start without it. |
| `GEMINI_MODEL` | No | The model to try first. If it is busy or slow, the app falls back to other Gemini Flash models automatically. |
| `ACCESS_CODE` | No | A password visitors must enter before using the AI. Use it when the app is online so strangers don't use up your free quota. |
| `PORT` | No | The port to run on. Default: `8000`. |

## Deploy for free (Vercel)

Recommended: the app stays awake, so pages open in a second or two.

1. Push this folder to a GitHub repository (it can be private). Do **not** upload `.env`.
2. Sign in to https://vercel.com with GitHub, choose **Add New → Project**, and import your repository. Vercel detects the Flask app in `app.py` automatically.
3. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: your Gemini key.
   - `ACCESS_CODE`: a password for visitors. If you leave it empty, anyone with the link can use the app.
4. Click **Deploy**. After a few minutes you get a link like `https://resume-ai-toolkit.vercel.app`.

Every new push to GitHub redeploys the app automatically. If you change a variable later, redeploy from the Vercel dashboard so the change takes effect.

## Deploy for free (Render.com)

1. Push this folder to a GitHub repository (it can be private). Do **not** upload `.env`.
2. Sign in to https://render.com with GitHub, choose **New + → Blueprint**, and select your repository. Render reads the settings from `render.yaml`.
3. Enter the two values Render asks for:
   - `GEMINI_API_KEY`: your Gemini key.
   - `ACCESS_CODE`: a password for visitors. If you leave it empty, anyone with the link can use the app.
4. Click **Apply**. After 3–5 minutes you get a link like `https://resume-matcher-xxxx.onrender.com`.

On the free plan the app sleeps after 15 minutes without use. The next visit takes about a minute to wake it.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ValueError: No API key was provided` at start-up | `GEMINI_API_KEY` is missing. Add it to `.env` in this folder. |
| `Address already in use` | Another copy is already running on port 8000. Stop it (`lsof -ti:8000 \| xargs kill`) or run on another port: `PORT=8001 python app.py`. |
| "Wrong access code" | `ACCESS_CODE` is set. Enter the same value in the page when it asks. |
| AI answers are slow or fail | The AI service is sometimes busy. Wait a minute and try again. |
| A job link can't be read | The site needs a login or blocks bots. Copy and paste the description instead. |

## Files

| File | Purpose |
|---|---|
| `app.py` | The Flask server, AI prompts, ATS check and job-link reader |
| `templates/index.html` | The web page (light and dark mode, works on mobile) |
| `requirements.txt` | Python packages |
| `render.yaml` | Render.com deployment settings |
