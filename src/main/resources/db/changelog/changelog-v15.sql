-- changeset modcord:17
-- comment: Add image persistence to pending_moderation_messages table
ALTER TABLE pending_moderation_messages ADD COLUMN images JSONB NOT NULL DEFAULT '[]'::jsonb;
