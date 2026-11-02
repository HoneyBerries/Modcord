package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.MessageEmbed;
import net.dv8tion.jda.api.entities.Role;
import net.dv8tion.jda.api.entities.channel.middleman.GuildChannel;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.util.PreferenceCommandHelper;
import net.honeyberries.util.SetupChecklist;
import net.honeyberries.util.SetupChecklist.RoleInfo;
import net.honeyberries.util.SlashCommandUtils;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.Color;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Slash command {@code /setup}: a first-run checklist for the current guild covering
 * preferences, bot permissions and role hierarchy. Admin-only, same gate as {@code /preferences}.
 */
public class SetupCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(SetupCommands.class);
    private static final int MAX_ROLES_LISTED = 5;
    private static final String OK = "✅ ";
    private static final String BAD = "❌ ";
    private static final String WARN = "⚠️ ";

    private final PreferenceCommandHelper helper = new PreferenceCommandHelper();

    /**
     * Registers the {@code /setup} slash command.
     *
     * @param commands the command list to register onto; must not be null
     */
    public void registerSetupCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        commands.addCommands(Commands.slash("setup", "Check this server's Modcord setup (permissions, channels, role order)"));
        logger.info("Registered /setup command");
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("setup")) {
            return;
        }
        Guild guild = helper.validateGuildAndPermissions(event);
        if (guild == null) {
            return; // helper already replied
        }
        try {
            SlashCommandUtils.replyEphemeral(event, buildChecklist(guild));
        } catch (Exception e) {
            logger.error("Error handling /setup in guild {}", guild.getId(), e);
            SlashCommandUtils.replyEphemeral(event, "An unexpected error occurred while processing the command.");
        }
    }

    private MessageEmbed buildChecklist(@NotNull Guild guild) {
        GuildPreferences prefs = PreferencesManager.getInstance()
                .getOrDefaultPreferences(new GuildID(guild.getIdLong()));
        Member self = guild.getSelfMember();

        StringBuilder config = new StringBuilder();
        config.append(prefs.aiEnabled() ? OK + "AI moderation enabled\n"
                : BAD + "AI moderation is disabled. Fix: `/preferences ai enabled:true`\n");
        config.append(describeChannel(guild, self, prefs.rulesChannelID(), "Rules channel",
                "/preferences rules_channel", EnumSet.of(Permission.VIEW_CHANNEL)));
        config.append(describeChannel(guild, self, prefs.auditLogChannelId(), "Audit-log channel",
                "/preferences audit_channel",
                EnumSet.of(Permission.VIEW_CHANNEL, Permission.MESSAGE_SEND, Permission.MESSAGE_EMBED_LINKS)));

        String actions = String.format("warn %s | delete %s | timeout %s | kick %s | ban %s",
                flag(prefs.autoWarnEnabled()), flag(prefs.autoDeleteEnabled()), flag(prefs.autoTimeoutEnabled()),
                flag(prefs.autoKickEnabled()), flag(prefs.autoBanEnabled()));

        Set<Permission> required = SetupChecklist.requiredPermissions(prefs.autoDeleteEnabled(),
                prefs.autoTimeoutEnabled(), prefs.autoKickEnabled(), prefs.autoBanEnabled());
        List<Permission> missing = SetupChecklist.missingPermissions(required, self.getPermissions());
        StringBuilder perms = new StringBuilder();
        if (missing.isEmpty()) {
            perms.append(OK).append("All permissions needed for enabled actions are granted.");
        } else {
            for (Permission p : missing) {
                perms.append(BAD).append("Missing **").append(p.getName())
                        .append("**. Fix: Server Settings > Roles > Modcord > enable it.\n");
            }
        }

        String hierarchy = describeHierarchy(guild, self);
        boolean allGood = config.indexOf(BAD) < 0 && missing.isEmpty() && hierarchy.startsWith(OK);

        return new EmbedBuilder()
                .setTitle("Modcord setup checklist")
                .setColor(allGood ? Color.GREEN : Color.ORANGE)
                .addField("Configuration", config.toString(), false)
                .addField("Actions enabled", actions, false)
                .addField("Bot permissions", perms.toString(), false)
                .addField("Role hierarchy", hierarchy, false)
                .setFooter("Change settings with /preferences")
                .build();
    }

    private static String flag(boolean enabled) {
        return enabled ? "on" : "off";
    }

    private String describeChannel(@NotNull Guild guild, @NotNull Member self, @Nullable ChannelID id,
                                   @NotNull String label, @NotNull String fixCommand, @NotNull Set<Permission> needed) {
        if (id == null) {
            return BAD + label + " not set. Fix: `" + fixCommand + "`\n";
        }
        GuildChannel channel = guild.getGuildChannelById(id.value());
        if (channel == null) {
            return BAD + label + " <#" + id.value() + "> no longer exists. Fix: `" + fixCommand + "`\n";
        }
        List<String> lacking = needed.stream()
                .filter(p -> !self.hasPermission(channel, p))
                .map(Permission::getName)
                .collect(Collectors.toList());
        if (!lacking.isEmpty()) {
            return BAD + label + " " + channel.getAsMention() + ": bot lacks " + String.join(", ", lacking)
                    + ". Fix: grant it in the channel's permissions.\n";
        }
        return OK + label + " " + channel.getAsMention() + "\n";
    }

    private String describeHierarchy(@NotNull Guild guild, @NotNull Member self) {
        List<Role> selfRoles = self.getRoles(); // sorted highest first
        int botPosition = selfRoles.isEmpty() ? 0 : selfRoles.get(0).getPosition();
        List<RoleInfo> infos = guild.getRoles().stream()
                .map(r -> new RoleInfo(r.getName(), r.getPosition(), r.isManaged(), r.isPublicRole()))
                .toList();
        List<RoleInfo> above = SetupChecklist.rolesAboveBot(infos, botPosition, MAX_ROLES_LISTED);
        long total = SetupChecklist.countRolesAboveBot(infos, botPosition);

        StringBuilder sb = new StringBuilder();
        if (above.isEmpty()) {
            sb.append(OK).append("No roles rank above the Modcord role.\n");
        } else {
            sb.append(WARN).append("Roles above the bot's top role (**")
                    .append(selfRoles.isEmpty() ? "@everyone" : selfRoles.get(0).getName()).append("**): ")
                    .append(above.stream().map(r -> "**" + r.name() + "**").collect(Collectors.joining(", ")));
            if (total > above.size()) {
                sb.append(" and ").append(total - above.size()).append(" more");
            }
            sb.append("\nDrag the Modcord role above these roles in Server Settings > Roles; "
                    + "Discord bots cannot act on members whose top role is equal/higher.\n");
        }
        sb.append("Note: the server owner can never be punished by a bot, regardless of role order.");
        return sb.toString();
    }
}
