# Human Moderator Review System

## Overview
The human moderator review system provides a structured workflow for escalating AI-flagged content to human moderators when automated enforcement is uncertain or inappropriate. It consolidates multiple review requests into clean, actionable embeds with interactive buttons for quick moderation.

## Architecture

### Core Components

#### ReviewNotificationManager (`review_notifications.py`)
- **Purpose**: Aggregates review actions per guild and sends consolidated embeds
- **Key Features**:
  - Batch consolidation: Groups all review items per guild into single embed
  - User context: Includes 7-day moderation history for each flagged user
  - Database tracking: Stores review requests with status and resolution info
  - Role mentions: Notifies configured moderator roles automatically

#### ReviewResolutionView (`review_ui.py`)
- **Purpose**: Provides interactive UI buttons on review embeds
- **Buttons**:
  - ✅ Mark as Resolved: Updates status, disables buttons, records resolver
  - ⚠️ Warn: Suggests `/warn` command with user context
  - ⏱️ Timeout: Suggests `/timeout` command with duration options
  - 🚪 Kick: Suggests `/kick` command
  - 🔨 Ban: Suggests `/ban` command with duration options
  - 🗑️ Delete: Suggests message deletion methods
- **Permissions**: Only moderators with `manage_guild` or configured moderator roles can resolve

#### Database Schema (`database.py`)
```sql
CREATE TABLE review_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL UNIQUE,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by INTEGER,
    resolution_note TEXT,
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE,
    CHECK (status IN ('pending', 'resolved', 'dismissed'))
)
```

### Integration Flow

1. **AI Processing**: AI model returns `ActionType.REVIEW` for content requiring human judgment
2. **Batch Collection**: `moderation_helper.handle_review_action()` adds each review to `ReviewNotificationManager`
3. **Consolidation**: After all actions processed, `send_review_batch_embed()` creates single embed per guild
4. **Delivery**: Embed sent to all configured review channels with role mentions
5. **Database Storage**: Review request stored with `pending` status and unique batch ID
6. **Moderator Interaction**: Moderators click buttons to get command suggestions or mark resolved
7. **Status Update**: Resolved reviews update database and modify embed to show completion

## Configuration

### Guild Settings
Reviews are controlled through guild settings accessible via slash commands:

```python
# Configure review channels
/settings review_channels add <channel>
/settings review_channels remove <channel>
/settings review_channels list

# Configure moderator roles (for permissions)
/settings moderator_roles add <role>
/settings moderator_roles remove <role>
/settings moderator_roles list

# Enable/disable automatic review action
/settings toggle auto_review
```

### Moderation Prompt
The AI model should be instructed to use the REVIEW action when:
- Content is borderline and requires nuanced human judgment
- User context is needed for appropriate action severity
- Community standards are unclear or subjective
- False positive risk is high

Example prompt addition:
```
If content violates rules but severity is unclear, or if you're uncertain about 
the appropriate action, use the "review" action to flag it for human moderators.
Include a detailed reason explaining why manual review is needed.
```

## Review Embed Format

```
🛡️ AI Moderation Review Request
The AI flagged 2 user(s) for human review.

#1: DisplayName
User: @User#1234 (`123456789`)
Channel: #general
Reason: Borderline spam - unsure if promotional link violates rules
Message: Check out this cool new... [truncated]
[Jump to Message](https://discord.com/...)
History (7d): warn, delete (+2 more)

#2: AnotherUser
User: @User#5678 (`987654321`)
Channel: #off-topic
Reason: Potentially offensive language - context suggests joking but may offend
Message: [message content]
[Jump to Message](https://discord.com/...)
History (7d): No prior actions

Bot: ModCord | Batch: abc12345
```

## Usage Examples

### Reviewing Flagged Content
1. Moderator sees review embed in designated review channel
2. Moderator reads AI reasoning and user history
3. Moderator clicks "Jump to Message" to see full context
4. Moderator decides on action:
   - Clicks appropriate action button to get command suggestion
   - Executes command manually with proper parameters
   - Clicks "Mark as Resolved" when done

### Checking Review Status
```python
# Get status of a specific review batch
status = await ReviewNotificationManager.get_review_status(batch_id)
# Returns: {"status": "resolved", "resolved_by": 123456, "resolved_at": "2024-..."}
```

### Manually Marking Resolved
```python
# From application code
success = await ReviewNotificationManager.mark_resolved(
    batch_id="abc123",
    resolved_by=moderator_user_id,
    resolution_note="Handled manually via DM"
)
```

## Database Queries

### Get pending reviews for a guild
```sql
SELECT * FROM review_requests 
WHERE guild_id = ? AND status = 'pending' 
ORDER BY created_at DESC;
```

### Get resolution statistics
```sql
SELECT 
    resolved_by,
    COUNT(*) as resolved_count,
    AVG(JULIANDAY(resolved_at) - JULIANDAY(created_at)) * 24 as avg_hours_to_resolve
FROM review_requests
WHERE status = 'resolved' AND guild_id = ?
GROUP BY resolved_by;
```

### Find unresolved reviews older than 24h
```sql
SELECT * FROM review_requests
WHERE status = 'pending' 
    AND created_at < datetime('now', '-24 hours')
ORDER BY created_at;
```

## Testing

### Unit Tests
See `tests/test_review_system.py` for comprehensive test coverage:
- Batch consolidation logic
- Database operations (store, resolve, query)
- Permission checks
- Button interactions
- Embed formatting

### Manual Testing Checklist
- [ ] Review embed appears in configured channels
- [ ] Moderator roles are mentioned
- [ ] User history displays correctly
- [ ] Jump links work
- [ ] Images display in embed
- [ ] All 6 buttons render correctly
- [ ] Non-moderators cannot resolve reviews
- [ ] Moderators can click "Mark as Resolved"
- [ ] Embed updates to show resolved status
- [ ] Buttons disable after resolution
- [ ] Quick-action buttons send ephemeral suggestions
- [ ] Database records review correctly
- [ ] Multiple reviews in same batch consolidate into one embed

## Future Enhancements

### Potential Features
- [ ] Dashboard for review analytics per guild
- [ ] Review queue priority system based on severity
- [ ] Automated follow-up if reviews not resolved within time limit
- [ ] Review assignment to specific moderators
- [ ] Bulk resolution for false positives
- [ ] Integration with external case management systems
- [ ] ML feedback loop from moderator decisions

### Performance Optimizations
- [ ] Batch embed editing for multiple simultaneous resolutions
- [ ] Caching of user history queries
- [ ] Pagination for review embeds with many users
- [ ] Rate limiting on review channel sends

## Troubleshooting

### Reviews not appearing
1. Check `/settings review_channels list` to verify channels configured
2. Check bot permissions in review channels (Send Messages, Embed Links)
3. Verify `auto_review_enabled` is not disabled in guild settings
4. Check logs for errors during `send_review_batch_embed()`

### Permission errors on resolution
1. Verify moderator roles are configured via `/settings moderator_roles`
2. Check user has `manage_guild` permission or configured role
3. Check `_check_moderator_permission()` logic in `review_ui.py`

### Buttons not working after bot restart
- Review views are persistent and should survive restarts
- Ensure custom_id format matches pattern: `review_resolve:{batch_id}`
- Check Discord.py persistence configuration

### Database errors
- Verify foreign key constraints are enabled: `PRAGMA foreign_keys = ON`
- Ensure guild_settings record exists before inserting review_requests
- Check indexes are created on batch_id and guild_id+status

## References
- Main integration: `src/modcord/moderation/moderation_helper.py`
- Database schema: `src/modcord/database/database.py`
- UI components: `src/modcord/bot/review_ui.py`
- Notification manager: `src/modcord/moderation/review_notifications.py`
- Tests: `tests/test_review_system.py`
- Architecture docs: `LOGIC.md`
