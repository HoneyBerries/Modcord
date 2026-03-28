package net.honeyberries.datatypes.action;

/**
 * Enumeration of supported moderation actions.
 */
public enum ActionType {
    BAN("action_type:ban"),
    UNBAN("action_type:unban"),
    KICK("action_type:kick"),
    WARN("action_type:warn"),
    DELETE("action_type:delete"),
    TIMEOUT("action_type:timeout"),
    NULL("action_type:null");

    private final String value;

    ActionType(String value) {
        this.value = value;
    }

    @Override
    public String toString() {
        return value;
    }

    public String getValue() {
        return value;
    }
}

