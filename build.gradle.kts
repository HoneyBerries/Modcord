import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar
import java.util.Properties
import java.io.FileInputStream

buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath(libs.postgresql)
        classpath("org.liquibase:liquibase-core:4.31.0")
    }
}


// Load .env file at project root
val envProps = Properties().apply {
    val envFile = rootDir.resolve(".env")
    if (envFile.exists()) {
        FileInputStream(envFile).use { load(it) }
    }
}

plugins {
    id("java")
    alias(libs.plugins.com.gradleup.shadow)
    alias(libs.plugins.org.liquibase.gradle)
}

group = "net.honeyberries"
version = "3.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation(libs.openai.java)
    implementation(libs.jda)

    implementation(libs.snakeyaml)
    implementation(libs.slf4j.api)
    implementation(libs.logback.classic)
    implementation(libs.gson)
    implementation(libs.jackson.databind)
    implementation(libs.dotenv.java)
    implementation(libs.dotenv.kotlin)

    implementation(libs.postgresql)
    implementation(libs.hikari.cp)
    implementation(libs.liquibase.core)

    implementation(libs.picocli)
    implementation(libs.jline)

    // Liquibase runtime classpath
    liquibaseRuntime(libs.liquibase.core)
    liquibaseRuntime(libs.postgresql)
    liquibaseRuntime(libs.slf4j.api)
    liquibaseRuntime(libs.logback.classic)
    liquibaseRuntime(libs.picocli)
    liquibaseRuntime(libs.apache.commons.lang3)

    testImplementation(platform(Testing.junit.bom))
    testImplementation(Testing.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}

// === Enforce Java 25+ ===
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}



liquibase {
    activities.register("main") {
        arguments = mapOf(
            "changelogFile" to "./db/changelog/db.changelog-master.xml",
            "searchPath" to "src/main/resources",
            "url" to "jdbc:postgresql://modcord-test-db.postgres.database.azure.com:5432/postgres",
            "username" to "ModcordTestAdmin",
            "password" to envProps.getProperty("POSTGRES_DB_PASSWORD")
        )
    }
}


tasks.withType<JavaCompile> {
    if (JavaVersion.current() < JavaVersion.VERSION_25) {
        throw GradleException("Java 25 or newer is required! Current version: ${JavaVersion.current()}")
    }
}

tasks.named<ShadowJar>("shadowJar") {
    manifest.attributes["Main-Class"] = "net.honeyberries.Main"
}


tasks.register<JavaExec>("run") {
    group = "application"
    description = "Runs the bot normally"

    mainClass.set("net.honeyberries.Main")
    classpath = sourceSets["main"].runtimeClasspath
}

tasks.register<JavaExec>("runTest") {
    group = "application"
    description = "Runs the bot with --test flag (auto-shuts down after 5 seconds)"

    mainClass.set("net.honeyberries.Main")
    classpath = sourceSets["main"].runtimeClasspath
    args("--test")
}


tasks.test {
    useJUnitPlatform()
}