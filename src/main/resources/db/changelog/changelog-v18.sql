-- liquibase formatted sql

-- changeset modcord:18
-- comment: Make action_id required for appeals (action IDs are now mandatory)
-- Remove any appeals without an action_id (they cannot be enforced anyway)
DELETE FROM moderation_appeals WHERE action_id IS NULL;

-- Add NOT NULL constraint
ALTER TABLE moderation_appeals ALTER COLUMN action_id SET NOT NULL;
