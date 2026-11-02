package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.components.actionrow.ActionRow;
import net.dv8tion.jda.api.components.buttons.Button;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Role;
import net.dv8tion.jda.api.entities.channel.middleman.GuildChannel;
import net.dv8tion.jda.api.utils.messages.MessageCreateBuilder;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.util.EmbedHelper;
import net.honeyberries.util.SetupChecklist;
import net.honeyberries.util.SetupChecklist.RoleInfo;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.awt.Color;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Builds the paged {@code /setup} message: a Status page, a Permissions detail page and a
 * short usage guide, with a navigation menu and a Re-check button.
 */
public class SetupEmbedUI {

    /** Every component ID this UI creates starts with this, so the listener can claim them. */
    public static final String ID_PREFIX = "setup_";
    public static final String NAV_ID = ID_PREFIX + "nav";
    public static final String RECHECK_PREFIX = ID_PREFIX + "recheck:";

    public static final String STATUS = "status";
    public static final String PERMISSIONS = "permissions";
    public static final String GUIDE = "guide";

    private static final List<NavPage> PAGES = List.of(
            new NavPage("Status", STATUS, "Is Modcord ready to moderate?"),
            new NavPage("Permissions detail", PERMISSIONS, "What's missing and how to fix it"),
            new NavPage("How to use Modcord", GUIDE, "A quick overview for admins"));

    private static final int MAX_ROLES_LISTED = 5;
    private static final String OK = "✅ ";
    private static final String BAD = "❌ ";
    private static final String WARN = "⚠️ ";

    private SetupEmbedUI() {}

    /**
     * Everything the pages need, gathered once per render.
     * @param configLines
     * @param required
     * @param missing
     * @param rolesAbove
     * @param rolesAboveTotal
     * @param botTopRole
     */
    private record Inspection(
            List<String> configLines,
            Set<Permission> required,
            List<Permission> missing,
            List<RoleInfo> rolesAbove,
            long rolesAboveTotal,
            String botTopRole) {}


    /**
     * Inspects the current configuration and role hierarchy of the given guild.
     * This method evaluates key guild settings, permissions, and role positions,
     * providing a summary of the bot's setup and any potential issues.
     *
     * @param guild the Discord guild to inspect, must not be null
     * @return an {@code Inspection} object containing configuration details,
     *         permissions, role hierarchy, and evaluation results relevant to the guild
     */
    private static Inspection inspect(@NotNull Guild guild) {
        GuildPreferences prefs = PreferencesManager.getInstance()
                .getOrDefaultPreferences(new GuildID(guild.getIdLong()));
        Member self = guild.getSelfMember();

        List<String> config = List.of(
                prefs.aiEnabled() ? OK + "AI moderation on" : BAD + "AI moderation off. Fix: `/preferences ai`",
                describeChannel(guild, self, prefs.rulesChannelID(), "Rules channel", "/preferences rules_channel",
                        EnumSet.of(Permission.VIEW_CHANNEL)),
                describeChannel(guild, self, prefs.auditLogChannelId(), "Audit channel", "/preferences audit_channel",
                        EnumSet.of(Permission.VIEW_CHANNEL, Permission.MESSAGE_SEND, Permission.MESSAGE_EMBED_LINKS)));

        Set<Permission> required = SetupChecklist.requiredPermissions(prefs.autoDeleteEnabled(),
                prefs.autoTimeoutEnabled(), prefs.autoKickEnabled(), prefs.autoBanEnabled());

        List<Role> selfRoles = self.getRoles(); // highest first
        int botPosition = selfRoles.isEmpty() ? 0 : selfRoles.getFirst().getPosition();
        List<RoleInfo> roles = guild.getRoles().stream()
                .map(r -> new RoleInfo(r.getName(), r.getPosition(), r.isManaged(), r.isPublicRole()))
                .toList();

        return new Inspection(
                config,
                required,
                SetupChecklist.missingPermissions(required, self.getPermissions()),
                SetupChecklist.rolesAboveBot(roles, botPosition, MAX_ROLES_LISTED),
                SetupChecklist.countRolesAboveBot(roles, botPosition),
                selfRoles.isEmpty() ? "@everyone" : selfRoles.getFirst().getName());
    }


    /**
     * Builds the full {@code /setup} message (embed plus nav menu and Re-check button) for one page.
     * Unknown page names fall back to the Status page.
     *
     * @param guild the guild being inspected
     * @param page  one of {@link #STATUS}, {@link #PERMISSIONS}, {@link #GUIDE}
     * @return the message, usable for both a new reply and an edit of an existing one
     */
    @NotNull
    public static MessageCreateData buildMessage(@NotNull Guild guild, @NotNull String page) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(page, "page must not be null");
        String current = PAGES.stream().anyMatch(p -> p.value().equals(page)) ? page : "";
        Inspection inspection = inspect(guild);

        EmbedBuilder embed = switch (current) {
            case PERMISSIONS -> permissionsPage(inspection);
            case GUIDE -> guidePage();
            case STATUS -> statusPage(inspection);
            default -> throw new IllegalStateException("Unexpected value: " + current);
        };
        
        return new MessageCreateBuilder()
                .setEmbeds(embed.build())
                .setComponents(
                        EmbedHelper.navigationRow(NAV_ID, current, PAGES),
                        ActionRow.of(Button.primary(RECHECK_PREFIX + current, "🔄 Refresh")))
                .build();
    }


    /**
     * Generates a status embed summarizing the current setup and configuration status for Modcord.
     * The status includes configuration details, permission checks, and role hierarchy order.
     *
     * @param i the {@code Inspection} instance containing configuration details and evaluation results
     * @return an {@code EmbedBuilder} representing the formatted status of the current setup
     */
    private static EmbedBuilder statusPage(@NotNull Inspection i) {
        List<String> config = i.configLines();
        String permissions = i.missing().isEmpty()
                ? OK + "All granted"
                : BAD + "Missing " + i.missing().stream().map(Permission::getName).collect(Collectors.joining(", "));
        String roleOrder = i.rolesAboveTotal() == 0
                ? OK + "No roles above Modcord"
                : WARN + i.rolesAboveTotal() + " role(s) above Modcord";

        long issues = Stream.concat(config.stream(), Stream.of(permissions, roleOrder))
                .filter(line -> !line.startsWith(OK))
                .count();
        return new EmbedBuilder()
                .setTitle("Modcord Setup · Status")
                .setDescription(issues == 0 ? OK + "All good" : WARN + issues + " thing(s) need attention")
                .setColor(issues == 0 ? Color.GREEN : Color.ORANGE)
                .addField("Configuration", String.join("\n", config), false)
                .addField("Permissions", permissions, false)
                .addField("Role order", roleOrder, false)
                .setFooter("Use the menu below for details");
    }


    /**
     * Generates an embed summarizing the required permissions and role hierarchy configurations for Modcord.
     * This method provides detailed feedback on missing permissions, required actions, and role order.
     *
     * @param i the {@code Inspection} instance containing configuration details, required permissions,
     *          missing permissions, and roles above the bot's current top role
     * @return an {@code EmbedBuilder} containing the formatted permissions and role hierarchy details
     */
    private static EmbedBuilder permissionsPage(@NotNull Inspection i) {
        String perms = i.required().stream()
                .sorted(Comparator.comparing(Permission::getName))
                .map(p -> i.missing().contains(p)
                        ? BAD + p.getName() + ": Server Settings > Roles > Modcord"
                        : OK + p.getName())
                .collect(Collectors.joining("\n"));

        String roles = i.rolesAbove().isEmpty()
                ? OK + "No roles rank above Modcord."
                : WARN + "Above **" + i.botTopRole() + "**: "
                + i.rolesAbove().stream().map(r -> "**" + r.name() + "**").collect(Collectors.joining(", "))
                + (i.rolesAboveTotal() > i.rolesAbove().size()
                ? " and " + (i.rolesAboveTotal() - i.rolesAbove().size()) + " more" : "")
                + "\nDrag Modcord above them in Server Settings > Roles.";

        return new EmbedBuilder()
                .setTitle("Modcord Setup · Permissions")
                .setColor(Color.CYAN)
                .addField("Needed for your enabled actions", perms, false)
                .addField("Role order", roles, false)
                .setFooter("The server owner can never be punished by a bot.");
    }

    private static EmbedBuilder guidePage() {
        return new EmbedBuilder()
                .setTitle("Modcord Setup · How to use")
                .setColor(Color.CYAN)
                .setDescription("""
                        • Modcord reviews messages in batches and acts on rule breaks.
                        • Change settings with `/preferences`.
                        • Users can appeal actions by DM.
                        • Every action is logged in your audit channel.""");
    }


    /**
     * Describes the state of a specific channel in a guild with respect to configuration or permissions.
     * Provides feedback highlighting if the channel is missing, invalid, or lacks required permissions.
     *
     * @param guild the Discord guild where the channel is located, must not be null
     * @param self the bot itself represented as a member of the guild, must not be null
     * @param id the identifier of the channel to describe; can be null if the channel is not set
     * @param label the label used to identify the channel in the description, must not be null
     * @param fixCommand the command users can execute to fix missing or invalid channels, must not be null
     * @param needed a set of permissions required for the bot in the channel, must not be null
     * @return a formatted string describing the state of the channel, including its availability and permission status
     */
    private static String describeChannel(@NotNull Guild guild, @NotNull Member self, @Nullable ChannelID id,
                                          @NotNull String label, @NotNull String fixCommand,
                                          @NotNull Set<Permission> needed) {
        if (id == null) {
            return BAD + label + " not set. Fix: `" + fixCommand + "`";
        }
        GuildChannel channel = guild.getGuildChannelById(id.value());
        if (channel == null) {
            return BAD + label + " <#" + id.value() + "> no longer exists. Fix: `" + fixCommand + "`";
        }
        String lacking = needed.stream()
                .filter(p -> !self.hasPermission(channel, p))
                .map(Permission::getName)
                .collect(Collectors.joining(", "));
        return lacking.isEmpty()
                ? OK + label + " " + channel.getAsMention()
                : BAD + label + " " + channel.getAsMention() + ": bot lacks " + lacking;
    }
}
