# Discord Bot Batching System

## Overview

This document describes the new channel-based message batching system implemented to improve the efficiency and scalability of the Discord moderation bot. Instead of processing each message individually, the bot now collects messages per channel over 15-second intervals and processes them in batches.

## Key Benefits

- **Massive efficiency improvement**: Reduces from potentially hundreds of individual AI inference calls to just one call per channel every 15 seconds
- **Better context awareness**: AI can see multiple messages together, improving spam and pattern detection
- **Reduced GPU workload**: Utilizes torch.cat for efficient batching across channels
- **Maintains responsiveness**: Actions are still applied promptly after each 15-second batch

## Architecture

### 1. Message Collection (bot_config.py)

The `BotConfig` class now includes:
- `channel_message_batches`: Per-channel message buffers
- `channel_batch_timers`: Asyncio tasks managing 15-second intervals
- `add_message_to_batch()`: Collects messages and starts timers
- `_batch_timer()`: Processes batches after 15 seconds

### 2. AI Processing (ai_model.py)

New batch processing functions:
- `get_batch_moderation_actions()`: Processes entire channel batches
- `parse_batch_actions()`: Handles multiple actions in JSON responses
- Maintains backward compatibility with existing `get_appropriate_action()`

### 3. Event Handling (cogs/events.py)

Modified message processing:
- `on_message` now adds messages to batches instead of immediate processing
- `_process_message_batch()`: Handles batch AI processing
- `_apply_batch_action()`: Applies individual actions from batch responses

### 4. Enhanced Actions (bot_helper.py)

Extended action system:
- `take_batch_action()`: Supports new batch parameters (delete_count, timeout_duration, ban_duration)
- `delete_recent_messages_by_count()`: Deletes specific number of messages
- `format_duration()`: Human-readable duration formatting
- Maintains backward compatibility with existing `take_action()`

## Data Formats

### Input JSON (sent to AI model)
```json
{
  "channel_id": "1234567890",
  "messages": [
    {
      "user_id": "1001",
      "username": "Alice",
      "timestamp": "2023-01-01T12:00:00Z",
      "content": "Hello everyone!",
      "image_summary": null
    },
    {
      "user_id": "1002", 
      "username": "Bob",
      "timestamp": "2023-01-01T12:00:05Z",
      "content": "SPAM SPAM SPAM!!!",
      "image_summary": null
    }
  ]
}
```

### Output JSON (received from AI model)
```json
{
  "channel_id": "1234567890",
  "actions": [
    {
      "user_id": "1002",
      "action": "warn",
      "reason": "repeated spam in short window",
      "delete_count": 5,
      "timeout_duration": null,
      "ban_duration": null
    }
  ]
}
```

## Supported Actions

- `null`: No action needed
- `delete`: Delete messages only
- `warn`: Send warning to user
- `timeout`: Temporarily mute user
- `kick`: Remove user from server
- `ban`: Ban user from server

Each action supports additional parameters:
- `delete_count`: Number of recent messages to delete (0-100)
- `timeout_duration`: Timeout duration in seconds (null = default 10 minutes)
- `ban_duration`: Ban duration in seconds (null/0 = permanent)

## Configuration

The system is automatically enabled when the bot starts. Per-guild AI moderation can be disabled using existing settings.

Key timing parameters:
- **Batch interval**: 15 seconds per channel
- **Message history**: Up to 128 messages per channel kept for context
- **Max batch size**: No hard limit, but typically 1-20 messages per 15-second window

## Backward Compatibility

The implementation maintains full backward compatibility:
- Existing `get_appropriate_action()` function still works
- Existing `take_action()` function still works
- All slash commands and manual moderation remain unchanged
- Only the automatic message processing uses the new batching system

## Performance Impact

Expected performance improvements:
- **GPU utilization**: 90-95% reduction in inference calls for typical servers
- **Latency**: Slight increase (max 15 seconds) but better overall throughput  
- **Memory usage**: Minimal increase for message buffering
- **Network usage**: Significantly reduced API calls

## Testing

Comprehensive test suite includes:
- Unit tests for batch collection and timing
- Integration tests for complete workflow
- JSON format validation
- Error handling and edge cases

Run tests with:
```bash
python -m unittest tests.test_batching -v
python -m unittest tests.test_integration -v
```

## Demo

See the batching system in action:
```bash
python demo_batching.py
```

This demonstrates message collection, batch processing, and the efficiency gains achieved.

## Migration Notes

No configuration changes are required. The new system activates automatically while maintaining all existing functionality. Servers can still disable AI moderation per-guild if needed.

The 15-second delay is intentional and provides better spam detection by allowing the AI to see patterns across multiple messages rather than making snap judgments on individual messages.