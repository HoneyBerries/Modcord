# Global Batch Processing Implementation

## Overview

This document describes the implementation of global batch processing for moderation messages in Modcord. The new system processes messages from multiple channels simultaneously through a single vLLM inference call, maximizing GPU utilization and throughput.

## Architecture

### Previous Implementation (Per-Channel Batching)

- Each channel had its own 15-second timer
- When a timer expired, that channel's messages were processed individually
- vLLM was called once per channel batch
- Low GPU utilization when processing messages from multiple channels

### New Implementation (Global Batching)

- Single global timer shared across all channels
- Messages from each channel are queued independently
- When the global timer expires, **all pending channel batches** are collected
- All batches are processed together in a **single vLLM call**
- Actions are parsed and routed back to respective channels
- Maximizes GPU utilization and throughput

## Key Components

### 1. GuildSettingsManager (guild_settings.py)

**Changes:**
- Replaced per-channel timers with a single global timer
- `channel_batch_timers` (Dict) → `global_batch_timer` (Optional[Task])
- `batch_timer(channel_id)` → `global_batch_timer_task()`
- Callback signature changed from `ModerationChannelBatch` to `List[ModerationChannelBatch]`

**Flow:**
```python
# When a message arrives
add_message_to_batch(channel_id, message)
  ├─ Add message to channel's queue
  └─ Start global timer if not running

# When global timer expires
global_batch_timer_task()
  ├─ Collect all pending channel batches
  ├─ Enrich each with history context
  ├─ Create List[ModerationChannelBatch]
  └─ Call batch_processing_callback(batches)
```

### 2. ModerationHelper (moderation_helper.py)

**Changes:**
- `process_message_batch(batch)` → `process_message_batches(batches)`
- Now handles multiple batches and routes actions by channel

**Flow:**
```python
process_message_batches(batches)
  ├─ Filter empty batches
  ├─ Call moderation_processor.get_multi_batch_moderation_actions(batches)
  ├─ Receive Dict[channel_id, List[ActionData]]
  └─ For each channel: apply actions to that channel's batch
```

### 3. ModerationProcessor (ai_moderation_processor.py)

**Changes:**
- Added `get_multi_batch_moderation_actions(batches)` as primary method
- Removed backward compatibility methods:
  - `get_batch_moderation_actions()` (legacy single-batch)
  - `_run_inference()` (legacy single inference)

**Flow:**
```python
get_multi_batch_moderation_actions(batches)
  ├─ For each batch:
  │   ├─ Convert to JSON payload with images
  │   ├─ Build dynamic schema for that channel
  │   ├─ Compile xgrammar for guided decoding
  │   └─ Create conversation structure
  ├─ Submit all conversations to vLLM in ONE call
  ├─ Parse responses per conversation
  └─ Return Dict[channel_id, List[ActionData]]
```

### 4. InferenceProcessor (ai_core.py)

**Changes:**
- Added `generate_multi_chat(conversations, grammars)` for batch processing
- Removed backward compatibility methods:
  - `generate_chat()` (legacy single generation)
  - `_generate_chat_sync()` (legacy single sync)

**Flow:**
```python
generate_multi_chat(conversations, grammars)
  ├─ Build sampling params list (one per conversation)
  ├─ Each has its own guided decoding grammar
  ├─ Call llm.chat(messages=conversations, sampling_params=params_list)
  └─ Return List[str] of responses
```

## Benefits

### Performance Improvements

1. **Higher GPU Utilization**
   - Multiple conversations processed in parallel on GPU
   - Better tensor batching efficiency in vLLM

2. **Reduced Latency**
   - All channels processed simultaneously instead of sequentially
   - Single inference call overhead instead of N calls

3. **Better Resource Usage**
   - Fewer context switches
   - More efficient memory usage with batched attention

### Code Simplification

1. **Removed Abstraction Layers**
   - No backward compatibility bloat
   - Direct batch processing only
   - Cleaner call hierarchy

2. **Single Code Path**
   - All processing goes through multi-batch flow
   - Easier to maintain and debug
   - No legacy method duplication

## Implementation Details

### vLLM Batch Processing

The implementation leverages vLLM's native batch processing capability:

```python
# vLLM batch call (similar to test_multi_image.py)
all_outputs = llm.chat(
    messages=conversations,           # List of conversation lists
    sampling_params=sampling_params_list,  # List of SamplingParams
    use_tqdm=False,
)

# Each conversation gets its own:
# - Input messages
# - Guided decoding grammar (xgrammar)
# - Output response
```

### Per-Channel Schema Constraints

Each channel maintains independent schema constraints:
- Only users who sent messages in that channel
- Only message IDs belonging to those specific users
- Prevents cross-channel action hallucination

### Action Routing

Actions are grouped by channel_id and applied independently:
```python
actions_by_channel: Dict[int, List[ActionData]] = {}
for idx, response in enumerate(responses):
    channel_id = channel_mapping[idx].channel_id
    actions = parse_batch_actions(response, channel_id, schema)
    actions_by_channel[channel_id] = actions
```

## Configuration

No configuration changes required. The existing `moderation_batch_seconds` setting controls the global timer duration:

```yaml
ai_settings:
  moderation_batch_seconds: 10.0  # Global timer duration
```

## Testing Considerations

Since this is a runtime optimization with no API changes:

1. **Functional Equivalence**
   - Each channel's messages are still processed identically
   - Schema constraints ensure correct user/message mapping
   - Action enforcement remains per-channel

2. **Integration Testing**
   - Verify multiple channels trigger global batch
   - Confirm actions route to correct channels
   - Test with varying message counts per channel

3. **Performance Testing**
   - Measure inference latency with multiple channels
   - Verify GPU utilization improvements
   - Monitor memory usage under load

## Migration Notes

This is a **breaking change** - backward compatibility layers were intentionally removed:

- Old code calling `get_batch_moderation_actions()` must use `get_multi_batch_moderation_actions()`
- Old code calling `generate_chat()` must use `generate_multi_chat()`
- Callback signatures changed from single batch to batch list

However, since this is an internal implementation detail and the public API (Discord bot interface) remains unchanged, users will see no difference except improved performance.

## Future Improvements

Potential enhancements to consider:

1. **Adaptive Batching**
   - Dynamic timer adjustment based on message rate
   - Flush batch early if it gets too large

2. **Priority Channels**
   - Process certain channels with lower latency
   - Multi-tier batching system

3. **Batch Size Limits**
   - Cap maximum conversations per vLLM call
   - Split into multiple batches if needed

4. **Metrics & Monitoring**
   - Track batch sizes and processing times
   - Monitor GPU utilization improvements

## Related Files

- `moderation_logic.md` - Updated architecture documentation
- `scripts/test_multi_image.py` - Reference implementation for vLLM batching
- `src/modcord/configuration/guild_settings.py` - Global batch coordinator
- `src/modcord/moderation/moderation_helper.py` - Batch processing entry point
- `src/modcord/ai/ai_moderation_processor.py` - Multi-batch inference orchestration
- `src/modcord/ai/ai_core.py` - vLLM batch generation wrapper
