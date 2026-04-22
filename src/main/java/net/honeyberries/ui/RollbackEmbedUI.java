package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.User;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.util.ActionHelper;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;

import java.awt.Color;
import java.time.Instant;
import java.util.Objects;

public class RollbackEmbedUI {

	/**
	 * Builds an embed for a single moderation action.
	 *
	 * @param action the action to display, must not be {@code null}
	 * @return an embed representing the action
	 */
	@NotNull
	public static EmbedBuilder buildRollbackEmbed(@NotNull ActionData action) {
		Objects.requireNonNull(action, "action must not be null");
		User user = action.userId().toUser();
		Color embedColor = ActionHelper.actionColor(action.action());

		String title = ActionHelper.actionEmoji(action.action()) + "  " + action.action().name() + " on " + (user != null ? user.getEffectiveName() : "Unknown User");

		return new EmbedBuilder()
				.setTitle(title)
				.setColor(embedColor)
				.setTimestamp(Instant.now())
				.addField("Action ID", "`" + action.id() + "`", false)
				.addField("User", DiscordUtils.userMention(action.userId()), false)
				.addField("Reason", action.reason(), false)
				.setFooter("Use /rollback action <action_id> to reverse this action", user != null ? user.getEffectiveAvatarUrl() : null);
	}
}
