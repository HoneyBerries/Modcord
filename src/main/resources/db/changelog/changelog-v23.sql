-- liquibase formatted sql

-- changeset modcord:23
-- comment: Drop the ai_log table; AI conversations (which contained message content) are no longer stored
DROP TABLE IF EXISTS ai_log;
