-- liquibase formatted sql

-- changeset modcord:20
-- comment: Add remove_on_delete_enabled flag to control whether deleted messages are removed from the moderation queue
ALTER TABLE guild_preferences ADD COLUMN remove_on_delete_enabled BOOLEAN NOT NULL DEFAULT FALSE;
