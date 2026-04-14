-- changeset modcord:12
-- comment: add an exclude channel ID column to the exemptions table

ALTER TABLE guild_moderation_exemptions ADD COLUMN channel_id BIGINT;

-- Update the check constraint to allow exactly one of user_id, role_id, or channel_id
ALTER TABLE guild_moderation_exemptions
    DROP CONSTRAINT chk_user_or_role;

ALTER TABLE guild_moderation_exemptions
    ADD CONSTRAINT chk_user_role_or_channel
        CHECK (
            (user_id IS NOT NULL AND role_id IS NULL AND channel_id IS NULL) OR
            (user_id IS NULL AND role_id IS NOT NULL AND channel_id IS NULL) OR
            (user_id IS NULL AND role_id IS NULL AND channel_id IS NOT NULL)
        );

-- Create unique index for channel_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_exemptions_guild_channel
    ON guild_moderation_exemptions (guild_id, channel_id)
    WHERE channel_id IS NOT NULL;

-- Create regular index for faster lookups
CREATE INDEX IF NOT EXISTS idx_exemptions_channel
    ON guild_moderation_exemptions (guild_id, channel_id);
