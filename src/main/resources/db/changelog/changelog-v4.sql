-- changeset modcord:4
-- comment: Allow nullable audit_log_channel_id and rules_channel_id
ALTER TABLE guild_preferences
    ALTER COLUMN audit_log_channel_id DROP NOT NULL,
    ALTER COLUMN rules_channel_id DROP NOT NULL;

ALTER TABLE guild_preferences
    ALTER COLUMN audit_log_channel_id DROP DEFAULT,
    ALTER COLUMN rules_channel_id DROP DEFAULT;