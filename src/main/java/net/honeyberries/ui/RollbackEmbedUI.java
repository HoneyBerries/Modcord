package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
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
	public static EmbedBuilder buildActionEmbed(@NotNull ActionData action) {
		Objects.requireNonNull(action, "action must not be null");

		String title = ActionHelper.actionEmoji(action.action()) + "  " + action.action().name() + " on " + DiscordUtils.userMention(action.userId());

		return new EmbedBuilder()
				.setTitle(title)
				.setColor(Color.ORANGE)
				.setTimestamp(Instant.now())
				.addField("Action ID", "`" + action.id() + "`", false)
				.addField("Reason", action.reason(), false)
				.setFooter("Use /rollback action <action_id> to reverse this action", null);
	}
}
