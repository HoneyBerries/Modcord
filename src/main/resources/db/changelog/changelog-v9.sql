-- changeset modcord:10
-- comment: Add table for storing Discord user IDs and usernames
CREATE TABLE IF NOT EXISTS discord_usernames (
    user_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    PRIMARY KEY (user_id)
);

