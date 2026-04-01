-- changeset modcord:9
-- comment: Enforce non-null moderator attribution for moderation actions

-- Backfill legacy rows created before moderator_id was required.
UPDATE guild_moderation_actions
SET moderator_id = user_id
WHERE moderator_id IS NULL;

ALTER TABLE guild_moderation_actions
    ALTER COLUMN moderator_id SET NOT NULL;

