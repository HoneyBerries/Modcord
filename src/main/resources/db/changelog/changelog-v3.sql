-- liquibase formatted sql

-- changeset modcord:5
-- comment: Allow nullable guild_rules fields for unconfigured rules state
ALTER TABLE guild_rules
	ALTER COLUMN rules_channel_id DROP NOT NULL,
	ALTER COLUMN rules_text DROP NOT NULL,
	ALTER COLUMN rules_text DROP DEFAULT;

-- changeset modcord:6
-- comment: Allow nullable channel guideline text for unconfigured channels
ALTER TABLE guild_channel_guidelines
	   ALTER COLUMN guidelines DROP NOT NULL,
	   ALTER COLUMN guidelines DROP DEFAULT;


