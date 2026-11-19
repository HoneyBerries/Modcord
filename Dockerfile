# syntax=docker/dockerfile:1

# ---- Build stage: compile the shadow JAR ----
FROM eclipse-temurin:25-jdk-alpine AS build
WORKDIR /src

# Resolve dependencies first so this layer is cached until the build files change.
COPY gradlew settings.gradle.kts build.gradle.kts gradle.properties versions.properties ./
COPY gradle ./gradle
RUN --mount=type=cache,target=/root/.gradle ./gradlew --no-daemon dependencies > /dev/null

COPY src ./src
RUN --mount=type=cache,target=/root/.gradle ./gradlew --no-daemon shadowJar -x test \
    && cp build/libs/*-all.jar /modcord.jar

# ---- Runtime stage: slim JRE, non-root ----
FROM eclipse-temurin:25-jre-alpine
RUN addgroup -S modcord && adduser -S -G modcord modcord

# The app resolves ./config relative to the working directory.
WORKDIR /app
COPY --from=build /modcord.jar /app/Modcord.jar
RUN mkdir -p /app/config /app/logs && chown -R modcord:modcord /app

USER modcord

# Mount a volume at /app/config: missing app_config.yml / system_prompt.md are
# seeded from the defaults bundled in the JAR on first start.
VOLUME ["/app/config"]

# Same GC/heap settings as start.sh. Override with -e JAVA_OPTS=...
ENV JAVA_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+ParallelRefProcEnabled -Dfile.encoding=UTF-8"

# Secrets (DISCORD_BOT_TOKEN, OPENAI_API_KEY, POSTGRES_DB_PASSWORD) are NOT baked in;
# pass them at runtime (--env-file / compose env_file / secrets manager).
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/Modcord.jar"]
