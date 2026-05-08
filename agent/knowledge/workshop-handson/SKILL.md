---
name: workshop-handson
description: Plan hands-on workshops, GameDays, Immersion Days, and labs where participants actively build or do things. Use when designing a session with participant exercises, team activities, or technical labs.
---

# Workshop / Hands-On Session Planning

## Scope

Sessions where participants are **active builders**, not passive listeners:
- AWS GameDay (team-based competitive troubleshooting)
- Immersion Day (guided labs with instructor support)
- Technical workshops (build something from scratch)
- Hackathons and build sprints
- Training sessions with exercises
- Design thinking workshops

## What Makes Workshops Different

| Presentation | Workshop |
|---|---|
| Speaker does 90% of talking | Participants do 70%+ of the work |
| Success = audience learned something | Success = audience BUILT something |
| Slides are the medium | Hands-on exercises are the medium |
| Q&A at the end | Questions throughout |
| Fixed pacing | Adaptive pacing (wait for slowest) |

## Planning Process

1. **Define learning outcomes** — what can participants DO after the workshop?
2. **Design the exercises** — progressive difficulty, clear instructions
3. **Plan the infrastructure** — accounts, environments, prerequisites
4. **Build the facilitator guide** — timing, common issues, helper allocation
5. **Create participant materials** — step-by-step guide, starter code, reference docs
6. **Test everything** — run through as a participant yourself

## Session Structure

### Pre-Workshop
- Send prerequisites 1+ week ahead (install X, create account Y, etc.)
- Provide a "pre-check" script participants can run to verify setup
- Have a backup plan for participants who didn't prepare

### Opening (10-15 min)
- Welcome + logistics (wifi, restrooms, schedule, breaks)
- Quick intro of facilitators and helpers
- Set expectations: "You will build X by the end of today"
- Icebreaker that relates to the topic (quick, low-stakes)
- Verify prerequisites: "Everyone open terminal and run this command"

### Instruction Blocks (alternate with exercises)
- **Explain** (10-15 min) — concept, demo, context for what's next
- **Exercise** (20-40 min) — participants do the thing
- **Debrief** (5-10 min) — common issues, interesting solutions, reinforce key points
- Repeat 3-5 cycles

### Closing (15-20 min)
- Group showcase — teams present what they built
- Recap learning outcomes (check: did we achieve them?)
- Next steps — how to continue learning
- Cleanup instructions (delete resources to avoid charges)
- Feedback survey

## Best Practices

### Exercise Design
- **Progressive difficulty** — start with a guided walkthrough, end with open-ended challenge
- **Clear success criteria** — participants must know when they've "done it"
- **Bite-sized steps** — each step should take 2-5 minutes max
- **Include checkpoints** — "at this point you should see X"
- **Provide escape hatches** — if stuck > 10 min, offer the solution to keep pace
- **Bonus challenges** — for fast finishers (don't let them get bored)

### Pacing
- The slowest participant sets the pace for group instruction
- Fast finishers need bonus tasks or can help neighbors
- Use a visible timer for exercises ("you have 15 minutes")
- Build in 20% buffer time — exercises ALWAYS take longer than you think
- "Raise your hand when done" or use green/red sticky notes for status

### Infrastructure & Setup
- **Test on the morning of** — AWS consoles change, services break
- Pre-create resources that take long (CloudFormation stacks, large datasets)
- Have a "gold image" — pre-provisioned environment for participants who failed setup
- Use AWS Workshop Studio, Cloud9, or shared accounts if possible
- Consider rate limits — 30 people deploying simultaneously in one account = throttling

### Facilitation
- **Helper ratio** — 1 helper per 8-10 participants minimum
- Circulate the room during exercises — don't sit down
- Watch for confused faces, not just raised hands (many won't ask)
- Use a Slack/Teams channel for async questions during exercises
- If 3+ people have the same issue: stop and address it for everyone
- Never touch someone's keyboard without asking

### Participant Materials
- Step-by-step guide with screenshots (at the resolution they'll see)
- Commands must be copy-pasteable (no special characters from PDF formatting)
- Include "what you should see" screenshots after each major step
- Provide a troubleshooting section for common errors
- Version-pin all dependencies (npm versions, AMI IDs, etc.)

## Common Mistakes

- ❌ Too much lecture, not enough hands-on (the "presentation disguised as workshop")
- ❌ Assuming everyone has the same setup (OS, permissions, network)
- ❌ Not testing exercises on a clean machine (works on my machine ≠ works for everyone)
- ❌ Single point of failure — one AWS account for 30 people
- ❌ No buffer time (running over because exercises take 2x expected)
- ❌ Ignoring struggling participants (they disengage silently)
- ❌ Instructions that depend on specific UI layouts (AWS console changes weekly)
- ❌ No cleanup instructions (participants get surprise AWS bills)
- ❌ Skipping the pre-check ("just install it during the workshop")

## Checklist

### 2 Weeks Before
- [ ] Learning outcomes defined (3-5 specific things participants will DO)
- [ ] Exercises designed and written (step-by-step)
- [ ] Infrastructure provisioned and tested
- [ ] Prerequisites document sent to participants
- [ ] Helpers recruited and briefed
- [ ] Backup/recovery plan for common failures

### 1 Week Before
- [ ] Full dry-run of all exercises on a clean environment
- [ ] Test with 1-2 guinea pig participants
- [ ] Prepare "escape hatch" solutions for each exercise
- [ ] Create bonus challenges for fast finishers
- [ ] Verify all links, downloads, and accounts work

### Day Of
- [ ] Test infrastructure FIRST THING in the morning
- [ ] Wifi verified (bandwidth for N participants)
- [ ] Power strips / extension cords available
- [ ] Whiteboard + markers ready for ad-hoc explanations
- [ ] Timer visible to all
- [ ] Participant materials accessible (URL, not email attachment)
- [ ] Feedback survey ready

### After
- [ ] Clean up cloud resources (avoid surprise bills)
- [ ] Share materials + recording (if applicable)
- [ ] Review feedback
- [ ] Document what worked / what broke for next time

## AWS GameDay Specifics

- Teams of 3-5 (mix skill levels within teams)
- Competitive scoring via dashboard — keeps energy high
- Inject failures progressively (start easy, escalate)
- Have a "hint" system — teams can buy hints at a score penalty
- Celebrate/recognize top teams AND "best recovery" stories
- Debrief is critical — share the intended solution paths

## Immersion Day Specifics

- Follow the official AWS Immersion Day content when available
- Supplement with customer-relevant context
- Typically 4-6 hours (with breaks)
- Mix lecture (30%) + lab (70%)
- Use AWS Workshop Studio for account provisioning
- End with "how this applies to YOUR environment" discussion
