rootProject.name = "Modcord"

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

plugins {
    id("de.fayard.refreshVersions") version "0.60.6"
}

dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
        }
    }
}