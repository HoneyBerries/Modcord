-- changeset modcord:5
-- comment: Add moderation exemptions table (users and roles)
CREATE TABLE IF NOT EXISTS guild_moderation_exemptions (
    guild_id BIGINT NOT NULL,
    user_id BIGINT,
    role_id BIGINT,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (guild_id, user_id, role_id),

    CONSTRAINT fk_exemptions_guild
        FOREIGN KEY (guild_id)
        REFERENCES guild_preferences(guild_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_user_or_role
        CHECK (
            (user_id IS NOT NULL AND role_id IS NULL) OR
            (user_id IS NULL AND role_id IS NOT NULL)
        )
);

-- Optional but recommended indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_exemptions_user
    ON guild_moderation_exemptions (guild_id, user_id);

CREATE INDEX IF NOT EXISTS idx_exemptions_role
    ON guild_moderation_exemptions (guild_id, role_id);


-- changeset modcord:6
-- comment: add indexes for all other tables
CREATE INDEX IF NOT EXISTS idx_actions_guild_id_id_desc
    ON guild_moderation_actions (guild_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_actions_guild_user_id_id_desc
    ON guild_moderation_actions (guild_id, user_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_actions_action_guild_id
    ON guild_moderation_actions (action, guild_id);
