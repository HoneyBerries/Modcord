-- changeset modcord:16
-- comment: Redesign appeal table to use is_open boolean and link to actions with foreign key
ALTER TABLE moderation_appeals ADD COLUMN is_open BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE moderation_appeals SET is_open = (status = 'open');

ALTER TABLE moderation_appeals DROP CONSTRAINT IF EXISTS chk_appeal_status;
ALTER TABLE moderation_appeals DROP COLUMN status;

ALTER TABLE moderation_appeals ADD COLUMN action_id UUID;
ALTER TABLE moderation_appeals ADD CONSTRAINT fk_appeal_action FOREIGN KEY (action_id) REFERENCES guild_moderation_actions(action_id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_appeals_guild_is_open ON moderation_appeals (guild_id, is_open);
DROP INDEX IF EXISTS idx_appeals_guild_status;

-- Add foreign key constraint for guild_id to ensure it references a valid guild
ALTER TABLE moderation_appeals ADD CONSTRAINT fk_appeal_guild FOREIGN KEY (guild_id) REFERENCES guild_preferences(guild_id) ON DELETE CASCADE;
