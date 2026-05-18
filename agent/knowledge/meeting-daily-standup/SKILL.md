---
name: meeting-daily-standup
description: Plan and run a daily standup (daily scrum). Use when structuring a daily standup ritual for an engineering team, product team, or any group that runs daily check-ins.
---

# Daily Standup Meeting Planning

## Purpose

A daily standup is a **synchronization ritual**, not a status report. Its job is to:
- Surface blockers before they compound
- Align the team on the day's focus
- Create a brief moment of shared context

**It is NOT:** A place to solve problems, debate architecture, or report to a manager.

## Format

| Parameter | Value |
|---|---|
| Duration | 15 minutes — hard cap |
| Frequency | Daily (or 4x/week for async-friendly teams) |
| Time | Same time every day — morning preferred |
| Location | Standing room (in-person) or video call (remote) |
| Attendees | Working team members only; stakeholders observe silently |

Standing up (physically) is the original forcing function for brevity. Remote teams use a visible 15-minute timer instead.

## The Three Questions

Each person answers:
1. **What did I complete yesterday?**
2. **What will I work on today?**
3. **What's blocking me?**

**Hard rules:**
- Answer all three; don't skip "no blockers"
- Be specific: "I finished the login bug fix" not "I worked on stuff"
- Keep each person to **60-90 seconds**
- If a topic sparks a real conversation → "let's take that offline" → move on

## Order of Updates

Options:

| Method | Best For |
|---|---|
| Round-robin by name | Small teams (< 8); predictable pacing |
| Walk the board (Jira/Kanban) | Larger teams; keeps focus on work, not people |
| Volunteer order | Teams with high trust and discipline |

**Walk-the-board** is preferred for engineering teams running sprints — you discuss tickets, not individuals.

## Parking Lot

Any topic that needs > 30 seconds of discussion gets **parked**:
- Write it down (board, Slack, whiteboard)
- Address immediately after standup with only the relevant people
- Never let one conversation block the rest of the team

## Blockers Protocol

When someone has a blocker:
1. They name it clearly in standup
2. Scrum master / team lead assigns an owner to unblock them
3. Unblocking conversation happens AFTER standup, not during

**Never** leave a blocker in standup unassigned. Blockers that aren't assigned get forgotten.

## Async Standup (Remote / Distributed Teams)

For teams across timezones, async standup via Slack/Discord works well:

**Slack workflow or bot (Geekbot, Standuply, etc.):**
- Posts 3 questions to each person at their local morning time
- Collects answers into a shared channel
- Team reads async; synchronous standup is optional or replaced

**Async standup template:**
```
✅ Yesterday: 
🔄 Today: 
🚫 Blocked: 
```

Async standup is NOT a replacement for team connection — still hold a weekly or bi-weekly live sync.

## Facilitation Tips

### Keeping It Under 15 Minutes
- Start on time — no waiting for latecomers
- Use a visible timer (share screen or physical timer)
- Interrupt long updates: "Let's take that offline — what's your blocker?"
- If team consistently runs over: reduce team size or split into sub-teams

### Keeping It Valuable
- Rotate facilitator monthly — builds ownership, prevents stagnation
- Occasionally ask: "Is this standup still serving us? What should we change?"
- Add a brief retro question weekly: "What went well yesterday? What was frustrating?"

### Energy
- Short opener: "Before we start — quick win from yesterday?" (30 sec, builds positivity)
- Don't let standup become a monotone recital — vary who goes first
- Remote standups: cameras on by default to maintain energy

## Anti-Patterns

| Anti-Pattern | Why It Hurts | Fix |
|---|---|---|
| Problem-solving during standup | 15 min becomes 45 min | Parking lot + strict offline rule |
| Reporting to the manager | People give the "right" answer, not the real one | Frame standup as peer-to-peer, not upward |
| Skipping "no blockers" | Real blockers get buried in politeness | Require all 3 questions — even "no blockers today" |
| Going through the motions | Team says words but nobody listens | Walk the board instead of round-robin |
| PM / manager "adds context" after every update | Turns peer sync into a briefing | Manager stays silent unless directly asked |
| Standup creep (grows to 30+ min) | Kills morning productivity | Hard timer; merge into weekly sync if needed |

## When to Change the Format

Signs your standup is broken:
- People give identical updates every day
- Discussion topics are always the same person's topics
- Nobody is blocking, ever (real teams always have blockers)
- People are on their phones / checking email
- The standup consistently runs past 20 minutes

**Fix options:**
- Switch from round-robin to walk-the-board
- Move to async-first standup with optional live check-in 2x/week
- Split into sub-team standups
- Reduce frequency to every other day

## Integration with Sprint Workflow

For Scrum teams:
- Daily standup replaces status updates in all other meetings
- Blockers raised in standup are escalated in the sprint and reflected in Jira
- Sprint review ≠ standup — keep them separate
- If a sprint planning topic surfaces in standup: park it for the next sprint ceremony

## Hebrew / Israeli Context

- Israeli engineering teams often have very informal standups — more of a quick "מה קורה" around the coffee machine
- Directness about blockers is cultural norm — no need to soften "I'm stuck on X and it's blocking me"
- Weekend context: Israeli work week is Sun-Thu; Monday standup covers Thursday + weekend gap
- WhatsApp async updates are common in smaller Israeli teams as a substitute for formal standup bots
