import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar
import java.util.Properties
import java.io.FileInputStream

buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath(libs.flyway.database.postgresql)
        classpath(libs.postgresql)
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
    alias(libs.plugins.org.flywaydb.flyway)
}

group = "net.honeyberries"
version = "3.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation(libs.openai.java)
    implementation(libs.jda)

    // Logging and config
    implementation(libs.snakeyaml)
    implementation(libs.slf4j.api)
    implementation(libs.logback.classic)
    implementation(libs.gson)
    implementation(libs.jackson.databind)
    implementation(libs.dotenv.java)
    implementation(libs.dotenv.kotlin)

    // Database stuff
    implementation(libs.postgresql)
    implementation(libs.hikari.cp)
    implementation(libs.flyway.core)
    implementation(libs.flyway.database.postgresql)

    // Console
    implementation(libs.picocli)
    implementation(libs.jline)



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


flyway {
    url = "jdbc:postgresql://modcord-test-db.postgres.database.azure.com:5432/postgres"
    user = "ModcordTestAdmin"
    password = envProps.getProperty("POSTGRES_DB_PASSWORD")
        ?: throw GradleException("DB password not set in .env")
    schemas = arrayOf("public")
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
    description = "Runs a single Java class"

    // Fully-qualified class name
    mainClass.set("net.honeyberries.Main")

    // Classpath to include compiled classes + dependencies
    classpath = sourceSets["main"].runtimeClasspath

    // Optional: pass arguments
    // args("arg1", "arg2")
}


tasks.test {
    useJUnitPlatform()
}