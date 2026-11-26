# 📘 StudyPilot

> **StudyPilot doesn't do your homework. It makes sure you're never unprepared.**

StudyPilot is an AI agent, built on **Google Gemini** and **Google ADK**, that connects to a student's **Google Classroom** and **Google Calendar**. It reads every lecture and plans the student's study time on its own. When a teacher changes something, it re-plans and tells the student out loud.

Built for **Google AI Agent-a-thon 2026, FAST University (CFD campus).**

## What it does

| Feature | How |
|---|---|
| Google sign-in | OAuth 2.0. Classroom, Drive and Gmail are read-only. Calendar is limited to StudyPilot's own events. Drive writing is `drive.file`, so it can only touch files it created. |
| Onboarding interview | Gemini interviews the student about goals, study hours, sleep and distractions, and reads a **photo of their timetable**. Classes become weekly Calendar events, and the planner uses the student's real study window. |
| Classroom sync | Courses, assignments, quizzes, announcements and lecture files, polled every 30 s (10 s in demo mode) |
| Hidden deadlines | Gemini reads each course's announcement thread in order ("quiz Monday", then "cancelled", then "moved to next week") and keeps the *current* deadlines, quoting the teacher as evidence |
| Class emails (Gmail) | Gemini reads recent class emails (read-only) and adds deadlines a teacher only emailed, mapped to the right course. Anything already on Classroom is skipped. |
| Auditor | Before it trusts a deadline, Gemini opens the full context (description, announcements, the attached PDF) and flags contradictions. Example: Classroom says 28 Nov but the PDF says 27 Nov. It also flags past dates, Sunday quizzes, odd hours and duplicates. |
| Gemini "brain" | Every change starts an agent run: Gemini decides which tools to call (plan, move, prioritize, add a session, flag, ask, notify), then verifies the result in Calendar. Every step is streamed to the **Agent runs** panel. |
| Auto study planning | Free time from Calendar, booked as colour-coded sessions that finish a day early, plus a 🎯 deadline marker per item. If it can't fit, it moves less-urgent sessions or falls back to Panic mode. |
| Closing the loop | If you add an event that clashes, the agent moves the session. If you skip a session, it gets rescheduled. A weak quiz gets an extra focused session **and rewritten notes**. |
| In-app calendar | Week view synced both ways with Google Calendar. Drag to move, select to add, and the agent re-plans around what you add. |
| Study notes | Detailed notes written from the **actual lecture files**: big idea, intuition, worked example, common mistakes and a quick check for each topic, plus an exam cheat sheet. You can edit them by hand or ask the AI ("make it simpler", "add an example"). They have version history with undo and download as a **PDF**. |
| Drive folder | `StudyPilot / <Subject> / <Topic>` with shortcuts to that topic's lectures and the notes as a Google Doc, updated on every edit |
| Strict teacher | A session only counts as done after 3 fresh check questions (≥ 66%). Retakes never repeat a question and target past mistakes. |
| Lecture breakdown + Urdu | Summary, concepts in simple words and likely exam points for PDF, Slides and PPTX. One click turns any explanation into simple Urdu. |
| Prep pack + Panic mode | Practice MCQs, YouTube explainers and a readiness score. Panic mode gives a 20-minute cram sheet and 5 rapid questions. |
| Voice + chat | Gemini Live (English/Urdu) and an ADK chat agent, both with the same tools. The agent speaks first when something changes. |
| Phone alerts | A private Discord channel webhook, with Meta WhatsApp Cloud API, ntfy, CallMeBot, Twilio and Telegram as drivers (whichever works where you are) |

## Agent architecture

```
 Classroom ─┐                 ┌──────────── Coordinator ─────────────┐
 Gmail ─────┼─▶ Sync agent ──▶│ instant deadline markers in Calendar │
 Calendar ──┘   (changes)     │ Auditor: full-context check, flags   │
                              │ Brain: Gemini function-calling loop  │──▶ Google Calendar
 Student ─▶ Watcher ─────────▶│   plan · move · prioritize · verify  │──▶ Drive notes folder
 (clashes, missed sessions,   │   rewrite notes · flag · ask · notify│──▶ Voice / Discord alert
  weak quizzes)               └──────────────────────────────────────┘
 Student ─▶ ADK chat agent / Gemini Live voice agent ─▶ same tools
```

**Safety:** Classroom, Drive and Gmail are read-only. It never submits work and never sends email. It only edits Calendar events tagged `extendedProperties.private.studypilot=true`, plus events the student edits themselves in the in-app calendar. In Drive it only writes inside its own StudyPilot folder.

**Reliability:** every Google or Gemini call retries with exponential backoff. If Classroom is unreachable, it shows cached data. Invalid JSON gets one stricter retry. Missing due dates are asked of the student, never guessed. All analyses are cached in SQLite, so no file is analyzed twice.

## Run it locally (Windows)

1. **Google Cloud:** enable the Classroom, Drive, Calendar, Gmail and YouTube Data v3 APIs. Create an OAuth **Web** client with redirect `http://localhost:8000/auth/callback` and save it as `backend/credentials.json`. Add your Gmail as a test user.
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

After the first setup, `.\start.ps1` starts both servers in one go. Before a demo, run `POST /api/warmup` to pre-analyze lectures and build the prep packs. See [DEMO.md](DEMO.md) for the full runbook.

### Models
- Text: `gemini-3.5-flash-lite`, with automatic fallback to other Flash models when Google returns 503/429/504.
- Voice: `gemini-3.8-live` (native audio, tool calling), falling back to `gemini-3.1-flash-live-preview`.
- All model IDs live in `backend/.env`, never in code.

## Tech
Python · FastAPI · Google ADK · google-genai (Gemini Flash + Gemini Live) · Classroom / Drive / Calendar / YouTube APIs · SQLite · React · Vite · Tailwind

## Roadmap
WhatsApp alerts once Meta verifies the business, a teacher dashboard, group study, and a mobile app.
