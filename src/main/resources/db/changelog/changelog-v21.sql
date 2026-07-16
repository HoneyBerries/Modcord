-- liquibase formatted sql

-- changeset modcord:21
-- comment: Add appeals_enabled flag to control whether users can submit moderation appeals
ALTER TABLE guild_preferences ADD COLUMN appeals_enabled BOOLEAN NOT NULL DEFAULT TRUE;
