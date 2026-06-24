---
name: api-key
description: Let each user optionally supply their own OpenRouter API key and choose an LLM model, falling back to the app's default key and model when unset.
---

# Context

The app currently makes every LLM call with a single developer-owned API key and a
hardcoded default model. All users share that key and model.

# Goal

Let each user *optionally*:
1. Provide their own API key (OpenRouter for now).
2. Choose which LLM model to use.

If a user has not configured their own key/model, the app keeps using the existing
developer key + default model. Existing behavior must not change for users who do nothing.

# Requirements

## Functional
- Add a settings area where a user can enter, save, and remove an OpenRouter API key.
- Let the user pick a model (fetch the live list from OpenRouter's models endpoint, or
  use a curated list — see Open questions).
- When a user key is present, route *that user's* LLM requests through their key + chosen model.
- When absent, fall back to the developer key + default model.
- Validate the key with a lightweight test call before saving; show a clear error if invalid.
- Let the user remove their saved API key:
  - Show a "Remove key" action in settings, visible only when a key is configured.
  - On removal, delete the stored key (don't just hide it) and clear the saved model choice.
  - Ask for confirmation before deleting, since the action can't be undone.
  - After removal, the user immediately reverts to the developer key + default model, with no broken state mid-request.

## Architecture / future-proofing
- Provider is OpenRouter today, but route key/model handling through a small provider
  abstraction (e.g. a `Provider` interface with `listModels()` / `createCompletion()`),
  so a future "choose your provider" feature can be added without rework.
- Do NOT implement other providers now — just avoid hardcoding OpenRouter in a way that blocks it.

## Security (treat as hard requirements)
- Never log API keys (not in app logs, not in error messages, not in analytics).
- Store user keys securely — encrypted at rest, not in plaintext config. (Confirm storage location.)
- Never send a user's key to the client or expose it to other users.
- Keep keys out of source control and stack traces.

# Out of scope (for now)
- Providers other than OpenRouter.
- Usage/billing tracking for user-supplied keys.
- Per-request model switching (a single saved preference is enough for v1 — confirm).

# Acceptance criteria
- A user who configures nothing sees behavior identical to today.
- A user can add a valid OpenRouter key, pick a model, and subsequent requests use them.
- An invalid key is rejected with a helpful message and is not saved.
- A user can remove their key (with confirmation); the stored key is deleted, the saved model is cleared, and the user reverts to the developer key + default model.
- Keys are stored encrypted and never logged or leaked.

# Open questions to resolve before/while building
- Where should keys be stored (DB column encrypted at rest / platform secret store / other)?
- Live model list from OpenRouter, or a curated subset?
- Is one saved model preference enough, or do users need to switch model per request?

# Approach
First explore the codebase to find: where LLM calls are made, how the current key and
default model are configured, the user/settings model, and the storage layer. Then
summarize the plan and the exact files you intend to change. Implement only after that.
