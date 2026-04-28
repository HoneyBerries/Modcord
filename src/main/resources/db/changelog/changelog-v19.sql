--changeset pepmon:19
ALTER TABLE guild_preferences ADD COLUMN allow_appeals BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE guild_preferences ADD COLUMN allow_reappeals BOOLEAN NOT NULL DEFAULT FALSE;
