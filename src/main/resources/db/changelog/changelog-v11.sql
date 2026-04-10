-- changeset modcord:11
-- comment: recreate the AI log table

DROP TABLE IF EXISTS ai_log;

CREATE TABLE ai_log (
    interaction_id UUID PRIMARY KEY NOT NULL DEFAULT gen_random_uuid(),
    guild_id BIGINT NOT NULL,
    interaction JSONB NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);