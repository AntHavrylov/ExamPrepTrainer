# UX Improvement Ideas

Quick wins already implemented below each item where applicable.

---

## Implemented in this session

### 1. Quiz — highlight the correct answer green after a wrong pick
**Problem:** when you pick the wrong option, only your choice turns red. The correct answer is shown as text below but not highlighted in the options list, making it hard to visually anchor.
**Fix:** set `correct` class on the correct option too once `result` is available.
File: `TrainingScreen.jsx`

### 2. Select All / Deselect All for sections
**Problem:** with many sections, picking them all for a training session or question bank generation requires clicking every card individually.
**Fix:** added "Select all" / "Deselect all" toggle button above the section list.
Files: `StartTrainingScreen.jsx`, `QuestionBankScreen.jsx`

### 3. Question count in Question Bank
**Problem:** there is no at-a-glance count of how many questions are visible vs total loaded, especially when filtering or searching.
**Fix:** added "X of Y questions" label between the filter bar and the list.
File: `QuestionBankScreen.jsx`

### 4. Hint button toggle (click to hide)
**Problem:** clicking "Show Hint" reveals it but you can't click to hide again — only the `h` keyboard shortcut works for toggling.
**Fix:** changed the button to call `setShowHint(h => !h)` and updates its label to "Hide hint" when the hint is visible.
File: `TrainingScreen.jsx`

### 5. Persist last training settings
**Problem:** every time you start a new session you have to re-select mode, format, difficulty, and sections from scratch.
**Fix:** saved the last used configuration to `localStorage` and reloaded on mount.
File: `StartTrainingScreen.jsx`

---

## Suggested next improvements (not yet implemented)

### "Train this topic" on Progress weakest topics
Clicking a topic in the weakest-topics list could navigate straight to Start Training with that section pre-selected.
**Effort:** medium — requires lifting the `navigate` callback and passing the pre-selected section id into `StartTrainingScreen`.

### Success toast after Settings saves
The API key, language, and session-length saves succeed silently. A brief "Saved ✓" inline confirmation (auto-dismiss after 2 s) would reassure users that the change took.
**Effort:** small — local `savedAt` state + `setTimeout` to clear it.

### "Train again" button on Summary screen
After finishing a session the user lands on the summary but must manually navigate back to Train and re-pick the same settings. A "Train again with same settings" button would reduce friction.
**Effort:** small — pass `session.mode / format / section_ids` back from Summary to App and pre-fill Start Training.

### Session length "custom" input
The current options are fixed at 5 / 10 / 15 questions. A small number input for arbitrary lengths (bounded, say 1–50) would suit users who want a quick 3-question warmup or a 20-question deep dive.
**Effort:** small — swap the `<select>` for a `<input type="number">` with min/max.

### Document preview in Sections list
The Sections screen shows full document content which can be very long. A truncated preview (first 150 chars) with a "Show more" toggle would keep the list scannable.
**Effort:** small — CSS line-clamp + a local `expanded` state per document.

### Progress filtering by time range
The score chart always shows the full history. A simple "Last 30 days / All time" toggle would help users who have been using the app for months see recent momentum.
**Effort:** medium — filter `score_history` client-side by a date cutoff.

### Question Bank — bulk delete
Currently questions can only be deleted one at a time. Checkboxes + a "Delete selected" button would help with cleaning up stale batches.
**Effort:** medium — adds selection state and a bulk delete API call.
