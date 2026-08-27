-- liquibase formatted sql

-- changeset modcord:22
-- comment: Rename the guild preferences column remove_on_delete_enabled to remove_on_delete

ALTER TABLE guild_preferences RENAME COLUMN remove_on_delete_enabled TO remove_on_delete;