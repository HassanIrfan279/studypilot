# 📘 StudyPilot

> **StudyPilot doesn't do your homework. It makes sure you're never unprepared.**

StudyPilot is an AI agent, built on **Google Gemini** and **Google ADK**, that connects to a student's **Google Classroom** and **Google Calendar**. It reads every lecture and plans the student's study time on its own. When a teacher changes something, it re-plans and tells the student out loud.

Built for **Google AI Agent-a-thon 2026, FAST University (CFD campus).**

## What it does

| Feature | How |
|---|---|
| Google sign-in | OAuth 2.0 with read-only Classroom/Drive scopes |
| Classroom sync | Courses, assignments, quizzes, announcements and lecture files, polled every 30s |
| Hidden deadlines | Gemini reads announcement text ("submit by next Monday") and pulls out due dates |
| Deadline dashboard | Sorted by urgency, colour per course, days-left badges |
| Lecture breakdown | Gemini reads the PDF, Google Slides or PPTX and returns a summary, concepts in simple words, and likely exam points |
| Urdu toggle | One click turns any explanation into simple Urdu |
| Quiz prep pack | Practice MCQs grounded in the lectures, plus the top YouTube explainers |
| Auto study planning | Finds free time with Calendar freebusy, then books colour-coded 45–90 min sessions that finish a day early |
| Change detection + re-planning | Quiz postponed? It moves only its own Calendar events and explains why |
| Agent speaks first | Announces changes out loud |
| Voice assistant | Gemini Live API in English or Urdu, with tool calling (deadlines, quiz me, move a session…) |
| Readiness score | 50% study sessions done + 50% best practice-quiz score |
| Panic mode | 20-minute cram sheet plus a 5-question rapid quiz |
| Agent activity log | Live feed of every decision the agents make |

## Agent architecture

```
             ┌──────────── Coordinator (root) ─────────────┐
 Classroom ─▶│ Sync agent ─▶ detect_changes ─▶ decide order │─▶ Activity log (WebSocket)
             │   Tutor agent: analyze, quiz, prep pack, Urdu │─▶ "Agent speaks first"
             │   Planner agent: freebusy, plan, replan       │─▶ Google Calendar
             └──────────────────────────────────────────────┘
 Student ─▶ ADK chat agent / Gemini Live voice agent ─▶ same tools
```

**Safety:** Classroom and Drive access is read-only. It never submits work and never sends email. It only edits Calendar events tagged `extendedProperties.private.studypilot=true`.

**Reliability:** every Google or Gemini call retries with exponential backoff. If Classroom is unreachable, it shows cached data. Invalid JSON gets one stricter retry. Missing due dates are asked of the student, never guessed. All analyses are cached in SQLite, so no file is analyzed twice.

## Run it locally (Windows)

1. **Google Cloud:** enable the Classroom, Drive, Calendar and YouTube Data v3 APIs. Create an OAuth **Web** client with redirect `http://localhost:8000/auth/callback` and save it as `backend/credentials.json`. Add your Gmail as a test user.
2. **Keys:** copy `backend/.env.example` to `backend/.env` and fill in `GEMINI_API_KEY` and `YOUTUBE_API_KEY`.
3. **Backend:**
   ```powershell
   cd backend
   py -3.11 -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   .\.venv\Scripts\uvicorn main:app --reload --port 8000
   ```
4. **Frontend** (new terminal):
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
5. Open http://localhost:5173 and click **Sign in with Google**.

## Tech
Python · FastAPI · Google ADK · google-genai (Gemini Flash + Gemini Live) · Classroom / Drive / Calendar / YouTube APIs · SQLite · React · Vite · Tailwind

## Roadmap
Gmail parsing, weak-topic tracking, teacher dashboard, WhatsApp reminders, group study, mobile app.
