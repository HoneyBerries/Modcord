package net.honeyberries.action;

import net.dv8tion.jda.api.JDA;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.discord.JDAManager;
import org.slf4j.Logger;

public class ActionHandler {

    private static final ActionHandler INSTANCE = new ActionHandler();
    private final Logger logger = org.slf4j.LoggerFactory.getLogger(ActionHandler.class);
    private final JDA jda = JDAManager.getInstance().getJDA();

    private ActionHandler() {
    }

    public static ActionHandler getInstance() {
        return INSTANCE;
    }

    public boolean processAction(ActionData actionData) throws  {

    }


}
