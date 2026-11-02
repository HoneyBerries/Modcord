package net.honeyberries.util;

import net.dv8tion.jda.api.Permission;
import net.honeyberries.util.SetupChecklist.RoleInfo;
import org.junit.jupiter.api.Test;

import java.util.EnumSet;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SetupChecklistTest {

    @Test
    void requiredPermissionsFollowEnabledActions() {
        var none = SetupChecklist.requiredPermissions(false, false, false, false);
        assertFalse(none.contains(Permission.BAN_MEMBERS));
        var all = SetupChecklist.requiredPermissions(true, true, true, true);
        assertTrue(all.containsAll(EnumSet.of(Permission.MESSAGE_MANAGE, Permission.MODERATE_MEMBERS,
                Permission.KICK_MEMBERS, Permission.BAN_MEMBERS)));
    }

    @Test
    void missingPermissionsReportsGapsAndAdminBypasses() {
        var required = SetupChecklist.requiredPermissions(false, true, false, true);
        var granted = EnumSet.of(Permission.VIEW_CHANNEL, Permission.MESSAGE_HISTORY, Permission.MESSAGE_SEND,
                Permission.MESSAGE_EMBED_LINKS, Permission.BAN_MEMBERS);
        assertEquals(List.of(Permission.MODERATE_MEMBERS), SetupChecklist.missingPermissions(required, granted));
        assertTrue(SetupChecklist.missingPermissions(required, EnumSet.of(Permission.ADMINISTRATOR)).isEmpty());
    }

    @Test
    void rolesAboveBotFiltersAndLimits() {
        List<RoleInfo> roles = List.of(
                new RoleInfo("Owner", 10, false, false),
                new RoleInfo("Mod", 9, false, false),
                new RoleInfo("OtherBot", 8, true, false),
                new RoleInfo("A", 7, false, false),
                new RoleInfo("B", 6, false, false),
                new RoleInfo("C", 5, false, false),
                new RoleInfo("D", 4, false, false),
                new RoleInfo("Modcord", 3, true, false),
                new RoleInfo("Member", 1, false, false),
                new RoleInfo("@everyone", 0, false, true));
        var above = SetupChecklist.rolesAboveBot(roles, 3, 5);
        assertEquals(List.of("Owner", "Mod", "A", "B", "C"), above.stream().map(RoleInfo::name).toList());
        assertEquals(6, SetupChecklist.countRolesAboveBot(roles, 3));
        assertTrue(SetupChecklist.rolesAboveBot(roles, 10, 5).isEmpty());
    }
}
