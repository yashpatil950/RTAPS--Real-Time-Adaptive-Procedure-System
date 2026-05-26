# RTAPS — Real-Time Adaptive Procedure System
## A presentation for the Shell facility team

Each section below is one slide. Bullet points are what appears on the slide.
The italicised "Speaker note" tells you what to say out loud. The
"📷 Screenshot" line tells you which of the screenshots to use as the
visual on that slide.

---

## Slide 1 — Title

**RTAPS**
**Procedures that adapt to your operators**

*Real-Time Adaptive Procedure System*

📷 No screenshot — use a clean cover slide with the RTAPS logo and the
title.

*Speaker note (10–15 seconds):* "Today I want to show you a system we
call RTAPS. The simple idea behind it: the manual that an operator
follows should adapt to how hard they're concentrating, instead of
showing the same instructions to everyone every time."

---

## Slide 2 — The challenge today

**Every operator is different. Every step is different.**

- Some procedure steps are routine; others demand intense focus
- The same operator can struggle on Step 6 today and breeze through it tomorrow
- New operators need more detail; experienced ones don't want clutter
- Current displays show the **same instructions to everyone, every time**

📷 No screenshot — a simple slide with these bullets is fine.

*Speaker note:* "Picture this — your most experienced operator and a
brand-new operator both pick up the same procedure today. The screen
shows them the exact same text. The expert finds it patronising; the
newcomer is overwhelmed. And even the same person on different days
can find the same step easy or hard depending on fatigue, distractions,
how their shift is going. We've all seen this. Today's systems don't
respond to it."

---

## Slide 3 — The RTAPS idea, in one sentence

**The screen quietly senses when the operator is working hard,
and shows them more help right at that moment.**

- No buttons to press
- No questions to answer
- No interruptions

📷 No screenshot — a single big sentence on the slide.

*Speaker note:* "That's it. That's the pitch. Everything else in this
deck is just *how* we do this. The operator never has to ask for help —
the screen offers it when they need it, and gets out of the way when
they don't."

---

## Slide 4 — How does the system know?

**It watches the eyes.**

The eyes give away how hard the mind is working:

- **Pupil size grows** when concentration goes up
  (like a camera lens opening in dim light)
- **Blinking slows down** during deep focus
- **Eye movements become longer and steadier** on hard tasks
- **Gaze becomes shakier** when the operator is searching or confused

This is well-established science — pilots, surgeons, and air-traffic
controllers have been measured this way for over 40 years.

📷 No screenshot — could use a simple cartoon of an eye with arrows.

*Speaker note:* "When you read something difficult, your pupils dilate
a tiny amount — about 5 to 15%. You don't notice, but a small camera
can. When you're really focused on one thing, you blink less often.
These are involuntary responses; you can't fake them and you can't
suppress them. We just measure them."

---

## Slide 5 — The hardware

**A pair of eye-tracking glasses.**

- Off-the-shelf product from Pupil Labs (research-grade, lightweight)
- Looks like ordinary safety glasses with two small cameras
- Plugs into a laptop via USB
- Operator can walk, move, talk normally

📷 **Screenshot 1** (the Pupil Capture software — shows the world view
from the glasses, with hands typing on a keyboard). Caption it
"What the glasses see — but the operator never has to look at this."

*Speaker note:* "These aren't custom-built. They're the same glasses
researchers and clinicians have been using for years. From the
operator's point of view, they're a slightly bulky pair of glasses.
That's all. Everything else happens on a laptop they don't have to
touch."

---

## Slide 6 — What the operator sees, step 1: the home screen

**RTAPS Dashboard**

- Picks a Train (Train 1 or Train 2)
- Picks a Procedure (Centrifuge, Column Flushing, or Pressure Testing)
- One-click start

📷 **Screenshot 4** (the RTAPS Simple welcome page with "System Status —
Ready for procedure execution" and the Train 1 / Train 2 cards).

*Speaker note:* "The operator's first screen. Notice how little text
there is. A status light — green, ready. Two trains. Three procedures.
That's everything they need to choose. They tap one and we go."

---

## Slide 7 — Available procedures

**Three procedures supported today, both trains:**

| Procedure | Steps |
|---|---|
| **Centrifuge testing** (oil sample BSW analysis) | 8 |
| **Column flushing** (maintenance) | 14 |
| **Pressure testing** (system validation) | 14 |

Adding a new procedure is a configuration change, not new software.

📷 **Screenshot 3** (the Available Procedures - Train 1 page with the
three cards: Centrifuge, Column Flushing, Pressure Testing).

*Speaker note:* "These are real Shell procedures. The system is loaded
with the actual step text, the actual tools, the actual instruments
your operators know. If tomorrow Shell wants to add a fourth procedure,
it's a configuration file, not a software release."

---

## Slide 8 — Step 2: the 2-minute calibration

**Before the procedure starts, the system learns what "calm you" looks like.**

- A black screen with a single white cross
- Operator sits and looks at the cross for 2 minutes
- The glasses measure their resting pupil size
- This is the "you on a good day" baseline

It's like tuning a guitar before playing a song — without this baseline,
the system can't tell the difference between "this person is stressed"
and "this person just has bigger pupils than average."

📷 No screenshot — sketch a black screen with a white "+" in the middle
and a "1:47 / 2:00" timer below it.

*Speaker note:* "This is a small but important step. Every person has
a different resting pupil size. Some people just naturally have more
dilated pupils than others. The 2-minute calibration captures *their*
normal — so when the system later sees their pupils grow by 10%, it
knows that's 10% relative to *them*, not relative to some textbook
average. The operator doesn't have to do anything — just look at the
cross. The screen counts down so they know how long is left."

---

## Slide 9 — Step 3: doing the procedure (the normal view)

**A familiar step-by-step checklist.**

- Each step has a number, a clear title, and a short description
- Tap the box to mark a step complete
- Time spent on the step is shown in the corner
- The next step lights up when the previous is done

📷 **Screenshot 2** (the Procedure Steps page showing Step 1 of
Centrifuge with the instructions and the Adaptive Guidance panel).
Use this same screenshot for the next 2 slides as well.

*Speaker note:* "From the operator's point of view, this looks like
any other tablet-based procedure guide. They've seen this kind of
checklist before. What's different is the box below the step — the
'Additional Guidance' panel. That panel appears and disappears based
on how hard the operator is working."

---

## Slide 10 — The adaptive guidance, in three levels

**Three levels of help, chosen automatically by the system:**

| Workload | What the operator sees |
|---|---|
| **Low** (operator is comfortable) | Just the step name and short description — no extra panel |
| **Medium** (some effort) | A small panel with key reminders, e.g., "Sample location upstream of LCV ensures representative oil" |
| **High** (operator is struggling) | A full Why / What / How explanation — the same Key Points, plus the reasoning behind them |

The operator does **nothing** to switch levels — the system does it for them.

📷 **Screenshot 2** again, pointing at the "Adaptive guidance" badge and
the "Additional Guidance" + "Detailed Explanation" boxes.

*Speaker note:* "Here's the magic. When the operator is breezing
through, the screen stays clean — just the step description. When
the system sees their pupils dilate or their blink rate drop, it
quietly adds the Key Points panel. If the operator keeps struggling,
the system upgrades to the full Why/What/How. None of this requires
the operator to click anything. They just keep working. The screen
adapts to them."

---

## Slide 11 — Cumulative — once we've shown it, it stays

**A safety feature: previously-shown guidance never disappears.**

- If the system shows Medium-level help, then later shows High-level
  help, **both stay on screen**
- An operator who needed the Medium reminder doesn't have it pulled
  out from under them when things get harder
- They see all the help they've earned

📷 No screenshot — a simple diagram with three rectangles stacked,
showing "Low: nothing → Medium: + Key Points → High: + Key Points + Why/What/How".

*Speaker note:* "One important design choice. If the system flipped
help on and off second by second, the operator would feel like the
screen was unstable. So once help appears, it stays for the rest of
that step. If we show 'Medium' and then it gets harder and we show
'High', they see both. Never less help than they've already seen."

---

## Slide 12 — What's happening behind the scenes (just a peek)

**The system checks four things every second, silently:**

1. **Pupil size** — how dilated are the eyes right now, compared to
   the calibration baseline?
2. **Blink rate** — how often is the operator blinking?
3. **Fixation length** — how long are their eyes holding still on one spot?
4. **Fixation steadiness** — how much is their gaze wandering?

These four signals are combined into one number: workload level.

📷 **Screenshot 5** (the Live ML page showing "Workload: Low" with the
horizontal bar chart and the features list below).

*Speaker note:* "This view is for trainers and safety engineers — not
the operator. It shows the four signals we measure, the system's
confidence in its prediction, and the resulting workload level. The
operator never sees this. They just see the procedure screen we showed
earlier."

---

## Slide 13 — The trainer / admin view

**For your trainers and safety auditors:**

- Live view of every operator's workload while they work
- Probability bars for Low / Medium / High
- Lifetime counts of pupil samples, blinks, fixations received
- Warns if any sensor stops responding

📷 **Screenshot 7** (the Live ML page showing Right Eye / Left Eye
diameter, Pupil samples / Blinks / Fixations counts).

*Speaker note:* "Your training and safety teams can pull up this
dashboard for any active session. They can see at a glance whether
the system is healthy, how the operator is doing, and whether any
sensor needs attention. Operators don't see this — it's a back-office
view."

---

## Slide 14 — Why this matters for Shell

| Benefit | What it means in practice |
|---|---|
| **Fewer mistakes** | Operators get help right when they need it, before they make an error |
| **Faster onboarding** | New operators get more detail automatically; experienced operators get less clutter automatically |
| **Hands-off** | Nothing to click, no pop-ups to dismiss, no menus to navigate |
| **Auditable** | Every step, every workload reading, recorded for compliance review |
| **Personalised** | Adapts to *this* operator on *this* day — not a one-size-fits-all manual |
| **Non-disruptive** | The screen is calmer when the operator is comfortable; busier only when they need it |

📷 No screenshot — a bulleted table is fine.

*Speaker note:* "Here's the value to Shell. Fewer mistakes, faster
training, hands-off, auditable, personalised, non-disruptive. If I
were going to pick one to emphasise to your safety team: a system
that automatically gives more help during high-load moments could
catch the exact errors that happen when an operator is overwhelmed."

---

## Slide 15 — How it actually works, in one picture

```
   ┌──────────────────────┐
   │  Operator wearing    │
   │  eye-tracker glasses │
   └──────────┬───────────┘
              │  (eye signals: pupil, blinks, fixations)
              ▼
   ┌──────────────────────┐
   │ Pupil Capture        │  (already-existing software from the glasses vendor)
   │ on a laptop          │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ RTAPS backend        │  (our system — analyses the signals in real time)
   │ Workload detector    │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Procedure screen     │  (what the operator sees — adapts automatically)
   │ on the tablet/laptop │
   └──────────────────────┘
```

📷 No screenshot — a clean diagram (you can draw the boxes in
PowerPoint). The text inside the boxes is exactly what's above.

*Speaker note:* "Four pieces. The operator wears the glasses. The
glasses send eye signals to the laptop. The laptop figures out the
workload level. The screen updates the guidance. End to end, under
one second from the eyes opening wider to the panel appearing on
screen."

---

## Slide 16 — What we'd love to do next

**A pilot at Shell would look like:**

1. **Three to five operators**, each doing the existing procedures
2. **Two weeks** of side-by-side comparison
3. We measure:
   - Error rates with vs. without adaptive guidance
   - Time to complete a procedure
   - Operator feedback (did they find it helpful? Distracting?)
4. We tune the system to your operators

**Bigger picture:**
- Add more procedures (any procedure can be loaded with the same approach)
- Operator-specific learning over time
- Integration with your existing training and compliance systems

📷 No screenshot — a simple roadmap visual.

*Speaker note:* "We'd love to do a small pilot. Three to five
operators, two weeks, on the procedures you've already seen in this
deck. We measure errors, completion times, and operator feedback. If
the numbers look good, we expand. If they don't, we tune. Either way
Shell ends up with concrete data about whether adaptive guidance
moves the needle for your specific operators."

---

## Slide 17 — Questions

**We're happy to dig into any part of this.**

Common questions we get:

- *"Does it work for operators who wear contacts/glasses?"* — Yes,
  the eye-tracker works over contacts and standard prescription
  glasses (we can show you).
- *"What if the operator isn't looking at the screen?"* — The system
  detects this and pauses the workload reading until they are.
- *"Does Shell IT have to install anything?"* — A small program on the
  laptop. No cloud connection required; all processing is local to
  the operator's laptop.
- *"What about privacy?"* — No video is recorded by default. Only
  numeric signals (pupil size, blink rate, etc.) are kept, and only
  for the duration of the session.

📷 No screenshot.

*Speaker note:* "Happy to answer any questions. The ones above are
the ones we hear most often. Anything else?"

---

## Appendix — for the technical team if asked

If anyone in the room is technical and wants more depth, here are
the slides you can pull up. **Don't show these by default.**

### A1: The four eye signals we use

- **Pupil PCPS (percent change from baseline)** — the canonical
  cognitive-load marker (Beatty, 1982)
- **Blink rate over 30 seconds** — cognitive blink suppression
  (Stern et al., 1984)
- **Mean fixation duration** — longer fixations = deeper processing
- **Fixation dispersion** — gaze steadiness

### A2: How the workload level is decided

- Trained on real recorded sessions from your existing operators
- Random Forest classifier
- Two outputs: Low or High workload
- Output is smoothed over 30 seconds so the guidance doesn't flicker

### A3: System architecture

- Eye-tracker glasses → ZMQ → Capture bridge → FastAPI backend →
  React frontend
- All running locally on the operator's laptop
- No cloud, no internet required after initial setup

---

## Speaker tips

1. **Don't read the slides.** The bullets are anchors; the speaker
   notes are the actual script.
2. **Demo if you can.** Even a recorded video of an operator session
   beats any slide. Show the panel appearing when a step gets hard.
3. **The five-minute version**: slides 1, 3, 4, 9, 10, 14, 16. Skip
   everything else if you're tight on time.
4. **The ten-minute version**: slides 1, 2, 3, 4, 5, 6, 9, 10, 11, 12,
   14, 16, 17.
5. **The full 30-minute version**: all slides plus a live demo
   between slides 10 and 11.
6. **Anchor everything to safety.** Shell cares about safety more than
   about technology. Every benefit ties back to "fewer mistakes" or
   "faster onboarding."
7. **Don't use the words** *machine learning*, *AI*, *model*,
   *algorithm*, *classifier*. Say "smart system that learns,"
   "the system recognises," "the software decides." If asked
   directly, you can use the technical terms.
8. **The screenshots are your visual aid.** Reference them by what
   they show ("here's the operator's home screen"), not by their
   role in the codebase.
