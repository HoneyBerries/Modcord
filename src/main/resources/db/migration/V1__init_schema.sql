-- ============================================
-- Flyway Migration: Initialize Database Schema
-- Tables: guild_preferences, guild_channel_guidelines, guild_rules, guild_moderation_actions, guild_moderation_action_deletions
-- ============================================


-- ==========================
-- Table: guild_preferences
-- ==========================
CREATE TABLE IF NOT EXISTS guild_preferences (
    guild_id BIGINT PRIMARY KEY,
    ai_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rules_channel_id BIGINT,
    auto_warn_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_delete_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_timeout_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_kick_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_ban_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    audit_log_channel_id BIGINT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ==========================
-- Table: guild_channel_guidelines
-- ==========================
CREATE TABLE IF NOT EXISTS guild_channel_guidelines (
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    guidelines TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, channel_id),
    CONSTRAINT fk_guild_channel_guidelines_guild
        FOREIGN KEY (guild_id)
        REFERENCES guild_preferences(guild_id)
        ON DELETE CASCADE
);

-- ==========================
-- Table: guild_rules
-- ==========================
CREATE TABLE IF NOT EXISTS guild_rules (
    guild_id BIGINT NOT NULL,
    rules_channel_id BIGINT NOT NULL,
    rules_text TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id),
    CONSTRAINT fk_guild_rules_guild
        FOREIGN KEY (guild_id)
        REFERENCES guild_preferences(guild_id)
        ON DELETE CASCADE
);

-- ==========================
-- Table: guild_moderation_actions
-- ==========================
CREATE TABLE IF NOT EXISTS guild_moderation_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- unique UUID per action
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    action TEXT NOT NULL,            -- ActionType stored as text
    reason TEXT NOT NULL DEFAULT '',
    timeout_duration BIGINT NOT NULL DEFAULT 0,
    ban_duration BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_moderation_guild
        FOREIGN KEY (guild_id)
        REFERENCES guild_preferences(guild_id)
        ON DELETE CASCADE
);

-- ==========================
-- Table: guild_moderation_action_deletions
-- ==========================
CREATE TABLE IF NOT EXISTS guild_moderation_action_deletions (
    action_id UUID NOT NULL,          -- FK to guild_moderation_actions.id
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    PRIMARY KEY (action_id, channel_id, message_id),
    CONSTRAINT fk_action
        FOREIGN KEY (action_id)
        REFERENCES guild_moderation_actions(id)
        ON DELETE CASCADE
);

-- ==========================
-- Trigger Function (reusable)
-- ==========================
CREATE OR REPLACE FUNCTION fn_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==========================
-- Triggers for automatic updated_at
-- ==========================
CREATE TRIGGER trg_guild_preferences_update
BEFORE UPDATE ON guild_preferences
FOR EACH ROW
EXECUTE FUNCTION fn_update_timestamp();

CREATE TRIGGER trg_guild_channel_guidelines_update
BEFORE UPDATE ON guild_channel_guidelines
FOR EACH ROW
EXECUTE FUNCTION fn_update_timestamp();

CREATE TRIGGER trg_guild_rules_update
BEFORE UPDATE ON guild_rules
FOR EACH ROW
EXECUTE FUNCTION fn_update_timestamp();

CREATE TRIGGER trg_guild_moderation_actions_update
BEFORE UPDATE ON guild_moderation_actions
FOR EACH ROW
EXECUTE FUNCTION fn_update_timestamp();