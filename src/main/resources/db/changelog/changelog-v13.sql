-- changeset modcord:13
-- comment: Add action reversal tracking table for the rollback feature and UnbanWatcherTask
CREATE TABLE IF NOT EXISTS guild_moderation_action_reversals (
    action_id    UUID PRIMARY KEY
        CONSTRAINT fk_reversal_action REFERENCES guild_moderation_actions(action_id) ON DELETE CASCADE,
    reason       TEXT    NOT NULL DEFAULT '',
    reversed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reversals_action_id
    ON guild_moderation_action_reversals (action_id);

-- changeset modcord:14
-- comment: Add ban/moderation appeal table
CREATE TABLE IF NOT EXISTS moderation_appeals (
    appeal_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    reason          TEXT   NOT NULL,
    status          TEXT   NOT NULL DEFAULT 'open'
        CONSTRAINT chk_appeal_status CHECK (status IN ('open', 'closed')),
    resolution_note TEXT,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_appeals_guild_status
    ON moderation_appeals (guild_id, status);

-- changeset modcord:15
-- comment: Add persistent queue table for shutdown-safe message preservation
CREATE TABLE IF NOT EXISTS pending_moderation_messages (
    guild_id          BIGINT      NOT NULL,
    message_id        BIGINT      NOT NULL,
    user_id           BIGINT      NOT NULL,
    channel_id        BIGINT      NOT NULL,
    content           TEXT        NOT NULL DEFAULT '',
    message_timestamp TIMESTAMPTZ NOT NULL,
    is_history        BOOLEAN     NOT NULL DEFAULT FALSE,
    saved_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_pending_messages_guild
    ON pending_moderation_messages (guild_id, message_timestamp ASC);
