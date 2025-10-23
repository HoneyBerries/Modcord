# AI Core Refactoring Summary

## Overview
This refactoring aligns the AI moderation core with the approach used in `test_multi_image.py`, eliminating unnecessary abstraction layers and using synchronous vLLM patterns.

## Key Changes

### 1. Replaced Async Engine with Synchronous LLM
- **Before**: Used `AsyncLLMEngine` with `AsyncEngineArgs` 
- **After**: Uses synchronous `LLM()` class directly
- **Benefit**: Simpler initialization, no async locks needed, matches test_multi_image.py pattern

### 2. Changed Inference Method
- **Before**: Used `engine.generate()` with text prompts and tokenizer template application
- **After**: Uses `llm.chat()` directly with multimodal messages
- **Benefit**: Native chat support, cleaner API, better multimodal handling

### 3. Dynamic Schema Generation
- **Before**: Static schema applied to all requests
- **After**: Schema generated dynamically per request with actual user IDs
- **Benefit**: Prevents AI from hallucinating user IDs - schema constrains to actual users in batch

### 4. Guided Decoding Approach
- **Before**: Used `GuidedDecodingParams` with precompiled grammar cached in instance
- **After**: Uses `StructuredOutputsParams` with grammar generated per request
- **Benefit**: Works with llm.chat(), per-request schema customization

### 5. Image Handling
- **Before**: Images converted to text descriptions or passed as metadata
- **After**: Images downloaded with aiohttp, converted to PIL RGB, passed as `image_pil` content
- **Benefit**: True multimodal processing, matches test_multi_image.py approach

### 6. Removed Abstraction Layers
- **Removed**: `init_lock`, `warmup_completed`, `guided_backend`, `_guided_grammar` caching
- **Removed**: Async initialization complexity with locks
- **Removed**: Tokenizer template application step
- **Benefit**: Simpler code, fewer failure points, easier to understand

### 7. Executor Pattern for Async Compatibility
- Synchronous LLM methods wrapped in `asyncio.run_in_executor()` 
- Maintains async API for Discord bot while using sync LLM underneath
- Clean separation of concerns

## File Changes

### src/modcord/ai/ai_core.py
- Removed: 193 lines
- Added: 287 lines
- Net change: +94 lines (but significantly simpler logic)
- Key changes:
  - `InferenceProcessor` now uses `self.llm` instead of `self.engine`
  - New `_build_dynamic_schema()` method
  - `init_model()` now synchronous, returns bool
  - `generate_chat()` uses `llm.chat()` with dynamic schema
  - Removed all async/await keywords from internal methods

### src/modcord/ai/ai_moderation_processor.py
- Removed: 108 lines  
- Added: 125 lines
- Net change: +17 lines
- Key changes:
  - New `_download_images()` method using aiohttp + PIL
  - `_build_multimodal_messages()` replaces old message formatting
  - Returns both messages and user_ids for dynamic schema
  - `_run_inference()` wraps synchronous call in executor
  - Removed text-only message conversion

## Testing

Added two test files to verify the refactoring:
- `test_ai_refactor.py` - Tests InferenceProcessor structure and dynamic schema
- `test_moderation_processor.py` - Tests ModerationProcessor with mock data

All tests pass, confirming:
- ✓ Correct initialization
- ✓ Dynamic schema generation with user ID constraints
- ✓ Multimodal message building with PIL images
- ✓ API compatibility maintained

## Benefits

1. **Simpler Code**: Removed async complexity, locks, and extra abstraction
2. **Better Image Handling**: Direct PIL image support in multimodal content
3. **Prevents Hallucination**: Dynamic schema constrains AI to actual user IDs
4. **Test-Driven**: Matches working test_multi_image.py pattern exactly
5. **Maintainable**: Clear flow from batch → images → messages → inference → actions
6. **Type Safety**: Fewer "Any" types, clearer data flow

## Migration Notes

No changes required for:
- `ai_lifecycle.py` - Works unchanged with new async interface
- Discord bot cogs - Use same async API as before
- Configuration files - Same config structure
- Database schema - No changes

## Verification

```bash
# All Python files compile
find src -name "*.py" -exec python -m py_compile {} \;

# Tests pass
python test_ai_refactor.py
python test_moderation_processor.py

# Modules import successfully
python -c "from modcord.ai.ai_core import inference_processor"
python -c "from modcord.ai.ai_moderation_processor import moderation_processor"
python -c "from modcord.ai.ai_lifecycle import ai_engine_lifecycle"
```

All verifications pass successfully.
