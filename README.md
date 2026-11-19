# Resume Matcher

A free AI career assistant. Paste your resume and a job description to get:

| Feature | What you get |
|---|---|
| Match score | Score out of 100, matched and missing skills, stronger resume lines, a new summary and a cover letter |
| ATS check | Whether resume-screening software (ATS) can read your resume properly |
| New resume | A full resume tailored to the job, downloadable as PDF. It asks for missing details instead of inventing them |
| Mock interview | 5 questions for this role, with a score, feedback and a model answer after each one |
| Learning plan | A 7-day plan for your missing skills, with YouTube searches and a portfolio project |
| Messages | LinkedIn connection note, recruiter message and a post-interview thank-you email |
| Job link import | Paste a job link instead of the description (sites that need a login won't work) |
| History | Past results are saved in your own browser only |

Powered by the Google Gemini free tier.

## Run locally

```bash
cd ~/Desktop/ai
source .venv/bin/activate
pip install -r resume-matcher/requirements.txt
python resume-matcher/app.py
```

Open **http://localhost:8000**.

Put your Gemini key in `~/Desktop/ai/.env` as `GEMINI_API_KEY=...`
(get a free key at https://aistudio.google.com/apikey).

## Deploy for free (Render.com)

1. Create a repository on https://github.com (it can be private).
2. Upload the files in this `resume-matcher` folder. Do **not** upload `.env`; it is ignored automatically.
3. Sign in to https://render.com with GitHub, then choose **New + → Blueprint** and select your repository.
4. Render will ask for two values:
   - `GEMINI_API_KEY`: your Gemini key.
   - `ACCESS_CODE`: a password visitors must enter. It stops strangers from using up your free AI quota. If you leave it empty, anyone with the link can use the app.
5. Click **Apply**. After 3–5 minutes you get a link like `https://resume-matcher-xxxx.onrender.com`.

On the free plan the app sleeps after 15 minutes without use. The next visit takes about a minute to wake it.

## Files

- `app.py`: the server, AI prompts and the ATS check.
- `templates/index.html`: the web page (light and dark mode, works on mobile).
- `render.yaml`: the Render deployment settings.
