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

## Also implemented in second session

### "Train this topic" on Progress weakest topics
Each topic in the weakest-topics list now has a "Train this topic" link.
Click → writes the section id to a one-shot `localStorage` key → navigates to Start Training → sections load, key is read + cleared → that section is pre-selected.
Files: `App.jsx`, `ProgressScreen.jsx`, `StartTrainingScreen.jsx`, `constants.js`

### Success toast after Settings saves
Language, session-length, and API-key saves all show a brief "Saved ✓" message (green, auto-clears after 2 s).
File: `SettingsScreen.jsx`

### "Train again" button on Summary screen
Summary screen now has a "Train again with same settings" button. It writes the session's `section_ids / mode / format / difficulty` to `lastTrainingSettings` localStorage and navigates to Start Training, which reads them on mount.
Files: `App.jsx`, `SummaryScreen.jsx`

### Session length custom number input
Settings replaced the fixed 5 / 10 / 15 `<select>` with a `<input type="number" min="1" max="50">` plus a Save button.
Backend `SessionLengthUpdate` schema widened from `Literal[5,10,15]` to `int = Field(ge=1, le=50)`.
Files: `SettingsScreen.jsx`, `backend/app/schemas.py`

### Document preview in Sections list
Documents with >150 characters are now truncated. A "Show more / Show less" toggle expands/collapses per document. Expanded state resets when switching to a different section.
File: `SectionsScreen.jsx`

---

## Remaining ideas (not yet implemented)

### Progress filtering by time range
A simple "Last 30 days / All time" toggle on the score chart.
**Effort:** small — filter `score_history` client-side by a date cutoff.

### Question Bank — bulk delete
Checkboxes + a "Delete selected" button to remove stale batches at once.
**Effort:** medium — adds selection state and a bulk delete API call.
