-- changeset modcord:11
-- comment: rename table for storing Discord user IDs and usernames
ALTER TABLE discord_usernames RENAME TO special_users;