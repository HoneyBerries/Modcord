# Moderation AI Stabilization
- [x] Normalize image-only message payloads so the model receives a concise, descriptive summary instead of raw URLs (`src/modcord/util/moderation_datatypes.py`, `src/modcord/ai/ai_moderation_processor.py`).
- [x] Harden batch action parsing to discard contradictory durations, fall back to safe reasons, and downgrade unsupported severe actions (`src/modcord/util/moderation_parsing.py`).
- [x] Guard final action consolidation against escalations that lack matching message evidence (`src/modcord/ai/ai_moderation_processor.py`).
