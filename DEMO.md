# 🎤 StudyPilot demo runbook (3 minutes)

## 30 minutes before

1. **Use your phone hotspot.** If you plan to use venue Wi-Fi, test it first.
2. Start everything from the `studypilot` folder: `.\start.ps1`
3. Check that http://localhost:8000/health shows `{"status":"ok"}`.
4. **Pre-warm** so nothing is slow on stage. Gemini reads every lecture and builds the prep packs now:
   `Invoke-WebRequest -Method POST http://localhost:8000/api/warmup`
   Wait for "✅ All set" in the activity log.
5. Open **Google Calendar** in a second browser tab, on week view.
6. Sign in to the **teacher** Classroom account on the second screen. Have these ready **as drafts** (don't post them yet):
   - A new announcement: *"Quiz on Chapter 2 this Friday in class."*
   - Later: *"The Chapter 2 quiz is postponed to next Wednesday."*
7. Click **🎙 Talk to StudyPilot** once to allow the microphone, then stop it.
8. `DEMO_MODE=true` in `backend/.env` means StudyPilot checks Classroom every **10 s**.

## On stage

| Time | Do | What judges see |
|---|---|---|
| 0:00 | Hook: *"Every student here has missed a deadline… nobody plans for them."* | Dashboard, daily brief |
| 0:30 | Teacher screen: **post** "Quiz on Chapter 2 this Friday" | Activity log: Sync finds a hidden deadline → Tutor builds the prep pack → Planner books sessions. StudyPilot announces it out loud. |
| 1:00 | Open **Study Plan** and the Google Calendar tab | Colour-coded 📘 sessions in real Calendar |
| 1:30 | Teacher screen: **post** "Chapter 2 quiz postponed to next Wednesday" | StudyPilot **speaks first**: "Heads up… moved… I've rearranged your plan." Calendar updates. |
| 2:10 | 🎙 *"Am I ready for the Chapter 2 quiz?"* then *"Quiz me on it"* | Readiness %, voice quiz, quiz opens on screen |
| 2:35 | (optional) Click **🚨 Panic mode** | Cram sheet + 5 rapid questions in ~10 s |
| 2:45 | Close: *"StudyPilot doesn't do your homework. It makes sure you're never unprepared."* | |

Urdu works too. Say *"Mujhe Prim's algorithm samjhao"*, or click **اردو میں سمجھائیں** on any explanation.

## If something goes wrong

- **Voice doesn't answer:** use the text chat box. It has the same agent and the same tools.
- **Gemini is slow or busy:** it automatically switches to a backup model. Lectures and prep packs are already cached from the warm-up.
- **Wi-Fi drops:** the app keeps showing the last synced data. Switch to your hotspot.
- **Backend window closed:** run `.\start.ps1` again.
- **Last resort:** play the backup demo video.

## Judge questions

- **Isn't this cheating?** It explains and quizzes. It never writes or submits work.
- **Privacy?** Read-only Classroom and Drive. It only edits Calendar events it created itself, which are tagged `studypilot=true`.
- **Why an agent?** It notices changes on its own, reasons over a whole announcement thread (a postponement, then a cancellation), decides priorities, acts in Calendar, and recovers from failures.
- **What if a due date is unclear?** It asks the student instead of guessing.
- **FAST accounts?** A university admin can approve it domain-wide. Today it runs in Google testing mode.
