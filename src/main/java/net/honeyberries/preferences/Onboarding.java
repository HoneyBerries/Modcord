package net.honeyberries.preferences;

import net.dv8tion.jda.api.entities.Guild;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.slf4j.Logger;

public class Onboarding {

    public static final Onboarding INSTANCE = new Onboarding();
    private static final Logger logger = org.slf4j.LoggerFactory.getLogger(Onboarding.class);


    public static Onboarding getInstance() {
        return INSTANCE;
    }

    public boolean setupGuild(Guild guild) {

        GuildID guildID = GuildID.fromGuild(guild);
        GuildPreferences defaultPreferences = new GuildPreferences(guildID);

        //TODO: finish implementation

        return false;
    }


}
