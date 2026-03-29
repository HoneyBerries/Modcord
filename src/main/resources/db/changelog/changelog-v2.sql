-- liquibase formatted sql

-- changeset modcord:4
-- comment: Create ai_log table to store AI inputs and outputs
CREATE TABLE IF NOT EXISTS ai_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id BIGINT NOT NULL,
    input_data JSONB NOT NULL,
    output_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_log_guild_id ON ai_log(guild_id);
CREATE INDEX idx_ai_log_created_at ON ai_log(created_at);