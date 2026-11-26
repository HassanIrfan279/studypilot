# 🎤 StudyPilot demo runbook (3 minutes)

## The day before

- **Sign in again.** Google expires sign-ins for testing-mode apps after 7 days. The **Check** page shows the exact expiry time. Sign out and in again the day before, so it can't expire on stage.
- Do one full rehearsal. Rehearsal study sessions can't trigger "you missed it" runs while `DEMO_MODE=true`.

## 30 minutes before

1. **Use your phone hotspot.** If you plan to use venue Wi-Fi, test it first.
2. Start everything from the `studypilot` folder: `.\start.ps1`
3. Open StudyPilot and go to **Check** (top bar), the pre-flight page:
   - Click **Warm up** and wait for "✅ All set" in the agent log (a few minutes). It pre-builds every prep pack and the notes, so nothing is slow on stage.
   - Click **Run checks** until it says **"All systems go"**. Each red row tells you its fix.
   - Click **Send test alert** and check that your phone buzzes.
4. Open **Google Calendar** in a second browser tab, on week view.
5. Sign in to the **teacher** Classroom account on the second screen. Have these ready **as drafts** (don't post them yet):
   - A new announcement: *"Quiz on Chapter 2 this Friday in class."*
   - Later: *"The Chapter 2 quiz is postponed to next Wednesday."*
6. **Click once anywhere on the StudyPilot page.** Browsers only allow spoken announcements after a click. Also click **🎙 Talk** once to allow the microphone, then stop it.
7. Phone: open Discord on the StudyPilot channel, sound on.
8. **Run the stage demo from your laptop** (`localhost`). That is the most reliable setup. Give judges the deployed link separately.

## On stage

| Time | Do | What judges see |
|---|---|---|
| 0:00 | Hook: *"Every student here has missed a deadline… nobody plans for them."* | Dashboard, daily brief |
| 0:30 | Teacher screen: **post** "Quiz on Chapter 2 this Friday" | Activity log: Sync finds a hidden deadline → Tutor builds the prep pack → Planner books sessions. StudyPilot announces it out loud. |
| 1:00 | Open **Study Plan** and the Google Calendar tab | Colour-coded 📘 sessions in real Calendar |
| 1:30 | Teacher screen: **post** "Chapter 2 quiz postponed to next Wednesday" | StudyPilot **speaks first**: "Heads up… moved… I've rearranged your plan." Calendar updates. |
| 2:10 | 🎙 *"Am I ready for the Chapter 2 quiz?"* then *"Quiz me on it"* | Readiness %, voice quiz, quiz opens on screen |
| 2:20 | Open the prep pack → **Study notes**. Click *"Make it simpler"*, then **Download PDF** / **Open in Drive** | Notes rewritten in ~10 s; the `StudyPilot / Subject / Topic` folder in Drive |
| 2:35 | (optional) Click **🚨 Panic mode** | Cram sheet + 5 rapid questions in ~10 s |
| 2:45 | Close: *"StudyPilot doesn't do your homework. It makes sure you're never unprepared."* | |

Urdu works too. Say *"Mujhe Prim's algorithm samjhao"*, or click **اردو میں سمجھائیں** on any explanation.

## Extra demos (if a judge asks "what else?")

- **Clash:** in **Calendar**, drag-select over a booked 📘 session and add "Cricket match". Within ~30 s the agent moves the study session, and the **Agent runs** panel shows its reasoning.
- **Weak quiz → new plan + new notes:** in a prep pack, answer the quiz badly. The agent books an extra focused session on your mistakes. The notes get a **⚠️ Your weak spots** section (version history shows "Rewritten after your weak quiz"), and the next retake has brand-new questions.
- **Auditor:** point at a red "The auditor wants you to check this" box. Example: DAA Assignment 1 says 28 Nov in Classroom but 27 Nov in the PDF.
- **Email:** email yourself "DAA viva next Tuesday 10am" (from another account). The next sync shows it with a **Found in email** badge.
- **Phone alert:** `Invoke-WebRequest -Method POST http://localhost:8000/api/notify/test` (needs `DISCORD_WEBHOOK_URL` in `.env`). WhatsApp Cloud API is built but waits on Meta business verification.

## If something goes wrong

- **Voice doesn't answer:** after 30 s the button says so on its own. Use the text chat box: same agent, same tools.
- **Gemini is slow or busy:** it automatically switches to a backup model. Lectures and prep packs are already cached from the warm-up.
- **Wi-Fi drops:** the app keeps showing the last synced data. Switch to your hotspot.
- **Backend window closed:** run `.\start.ps1` again. Then open **Check** to confirm everything is green.
- **Gemini answers slowly:** each agent run is capped at 90 s, and every Gemini call at about 100 s across backup models. The app shows what it finished and never hangs.
- **Last resort:** play the backup demo video.

## Judge questions

- **Isn't this cheating?** It explains and quizzes. It never writes or submits work.
- **Privacy?** Read-only Classroom, Drive and Gmail. Drive writes are limited to its own StudyPilot folder. It only edits Calendar events it created itself, which are tagged `studypilot=true`.
- **Why an agent?** It notices changes on its own, reasons over a whole announcement thread (a postponement, then a cancellation), decides priorities, acts in Calendar, and recovers from failures.
- **What if a due date is unclear?** It asks the student instead of guessing.
- **FAST accounts?** A university admin can approve it domain-wide. Today it runs in Google testing mode.
