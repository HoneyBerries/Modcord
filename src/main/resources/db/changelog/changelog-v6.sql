-- changeset modcord:7
-- comment: Fix moderation exemptions uniqueness semantics for user/role rows

-- The previous composite primary key implied NOT NULL on user_id/role_id,
-- which conflicts with the user-or-role check constraint.
ALTER TABLE guild_moderation_exemptions
    DROP CONSTRAINT IF EXISTS guild_moderation_exemptions_pkey;

ALTER TABLE guild_moderation_exemptions
    ALTER COLUMN user_id DROP NOT NULL,
    ALTER COLUMN role_id DROP NOT NULL;

-- Enforce idempotency per (guild,user) and (guild,role) while still allowing one nullable target column.
CREATE UNIQUE INDEX IF NOT EXISTS uq_exemptions_guild_user
    ON guild_moderation_exemptions (guild_id, user_id)
    WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_exemptions_guild_role
    ON guild_moderation_exemptions (guild_id, role_id)
    WHERE role_id IS NOT NULL;

