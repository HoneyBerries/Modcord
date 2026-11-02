package net.honeyberries.ui;

import org.jetbrains.annotations.NotNull;

/**
 * One entry in a page-navigation select menu.
 *
 * @param label       the text shown for the page
 * @param value       the value sent back when the page is picked
 * @param description the short hint shown under the label
 */
public record NavPage(@NotNull String label, @NotNull String value, @NotNull String description) {}
