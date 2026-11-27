// The StudyPilot agent team: who they are, what they do, and how to spot them in the live log.
export const AGENTS = [
  {
    id: 'atlas', name: 'Atlas', role: 'Coordinator · the brain', color: '#6366f1', accent: '#a5b4fc', gear: 'brain',
    mission: 'Decides what to do whenever something changes, then checks its own work.',
    does: ['Reads every change and plans a response', 'Calls the other agents as tools', 'Speaks first when something important happens'],
    uses: ['Gemini', 'All agents'],
    match: (l) => l.agent === 'Coordinator' && !/^🌙|Habits|Goal|Workload|Nightly/.test(l.message),
  },
  {
    id: 'scout', name: 'Scout', role: 'Sync · the watcher', color: '#0ea5e9', accent: '#7dd3fc', gear: 'radar',
    mission: 'Watches Classroom and your class emails every few seconds for anything new.',
    does: ['Spots new and postponed deadlines', 'Reads teacher announcements for hidden dates', 'Pulls deadlines out of class emails'],
    uses: ['Classroom', 'Gmail'],
    match: (l) => l.agent === 'Sync',
  },
  {
    id: 'chrono', name: 'Chrono', role: 'Planner · the scheduler', color: '#10b981', accent: '#6ee7b7', gear: 'clock',
    mission: 'Turns deadlines into study sessions in your free time.',
    does: ['Estimates how long each deadline needs', 'Books sessions around your classes', 'Re-plans when dates move'],
    uses: ['Google Calendar'],
    match: (l) => l.agent === 'Planner',
  },
  {
    id: 'sage', name: 'Sage', role: 'Tutor · the teacher', color: '#8b5cf6', accent: '#c4b5fd', gear: 'cap',
    mission: 'Reads your real lecture slides and teaches you what matters for the exam.',
    does: ['Writes study notes and prep packs', 'Makes quizzes that never repeat', 'Brings weak topics back after 1, 3 and 7 days'],
    uses: ['Drive', 'Gemini', 'YouTube'],
    match: (l) => l.agent === 'Tutor' || l.agent === 'Drive',
  },
  {
    id: 'aegis', name: 'Aegis', role: 'Reviewer · the guardian', color: '#14b8a6', accent: '#5eead4', gear: 'shield',
    mission: 'Checks every calendar change before it happens, and can say no.',
    does: ['Blocks clashes and late-night sessions', 'Keeps breaks and a 6-hour daily limit', 'Sends bad plans back to be redone'],
    uses: ['Google Calendar'],
    match: (l) => l.agent === 'Reviewer',
  },
  {
    id: 'luna', name: 'Luna', role: 'Coach · the night owl', color: '#7c3aed', accent: '#ddd6fe', gear: 'moon',
    mission: 'Reviews your day every night and keeps you on track for your goals.',
    does: ['Learns when you actually study', 'Escalates deadlines you are not ready for', 'Asks before trading off sessions'],
    uses: ['Calendar', 'Gmail drafts'],
    match: (l) => l.agent === 'Coordinator' && /^🌙|Habits|Goal|Workload|Nightly/.test(l.message),
  },
  {
    id: 'nova', name: 'Nova', role: 'Career · the talent scout', color: '#f59e0b', accent: '#fcd34d', gear: 'briefcase',
    mission: 'Finds internships that fit you, writes the applications and tracks replies.',
    does: ['Builds your CV by interviewing you', 'Picks the best postings and explains why', 'Watches Gmail for interview invites'],
    uses: ['Gmail', 'Drive', 'Bayt.com'],
    match: (l) => l.agent === 'Career',
  },
  {
    id: 'echo', name: 'Echo', role: 'Voice · the companion', color: '#ec4899', accent: '#f9a8d4', gear: 'headset',
    mission: 'Talks with you in English or Urdu and can act while it talks.',
    does: ['Answers questions out loud', 'Moves sessions and starts quizzes by voice', 'Reads alerts to you'],
    uses: ['Gemini Live'],
    match: (l) => l.agent === 'Voice',
  },
]

export const agentFor = (log) => AGENTS.find((a) => a.match(log))
