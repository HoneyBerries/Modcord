-- changeset modcord:8
-- comment: Rename moderation action key to action_id and track moderator attribution

ALTER TABLE guild_moderation_actions
    RENAME COLUMN id TO action_id;

ALTER TABLE guild_moderation_actions
    ADD COLUMN moderator_id BIGINT;

-- Keep index definitions aligned with renamed key column.
DROP INDEX IF EXISTS idx_actions_guild_id_id_desc;
CREATE INDEX IF NOT EXISTS idx_actions_guild_id_action_id_desc
    ON guild_moderation_actions (guild_id, action_id DESC);

DROP INDEX IF EXISTS idx_actions_guild_user_id_id_desc;
CREATE INDEX IF NOT EXISTS idx_actions_guild_user_id_action_id_desc
    ON guild_moderation_actions (guild_id, user_id, action_id DESC);

