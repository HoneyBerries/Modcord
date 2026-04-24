-- liquibase formatted sql

-- changeset modcord:17
-- comment: Add created_at indices for improved sorting performance

CREATE INDEX IF NOT EXISTS idx_actions_guild_id_created_at_desc
    ON guild_moderation_actions (guild_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_actions_guild_user_id_created_at_desc
    ON guild_moderation_actions (guild_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_actions_created_at_desc
    ON guild_moderation_actions (created_at DESC);
