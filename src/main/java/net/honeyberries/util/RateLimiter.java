package net.honeyberries.util;

import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

/**
 * Token-bucket rate limiter keyed by an arbitrary domain type.
 * <p>
 * Each key gets its own semaphore capped at {@code maxPermits}. A background refill
 * thread periodically restores permits up to the configured maximum so callers can
 * acquire them again. This approach smooths bursts while applying steady-state limits.
 *
 * <p>Thread-safe; per-key semaphores are created lazily and stored in a
 * {@link ConcurrentHashMap}.
 *
 * <p>Example usage (per-guild action rate limiting):
 * <pre>{@code
 * RateLimiter<GuildID> limiter = new RateLimiter<>(10, 5, TimeUnit.SECONDS);
 *
 * if (!limiter.tryAcquire(guildId)) {
 *     logger.warn("Rate limit exceeded for guild {}", guildId);
 *     return;
 * }
 * // proceed with the action
 * }</pre>
 */
public class RateLimiter<K> {

    private static final Logger logger = LoggerFactory.getLogger(RateLimiter.class);

    private final int maxPermits;
    private final Map<K, Semaphore> buckets = new ConcurrentHashMap<>();

    /**
     * Constructs a rate limiter and starts the background refill thread.
     *
     * @param maxPermits   maximum concurrent permits per key (burst capacity), must be >= 1
     * @param refillPeriod how often permits are replenished, must be > 0
     * @param refillUnit   time unit for {@code refillPeriod}, must not be {@code null}
     * @throws IllegalArgumentException if {@code maxPermits} < 1 or {@code refillPeriod} <= 0
     * @throws NullPointerException     if {@code refillUnit} is {@code null}
     */
    public RateLimiter(int maxPermits, long refillPeriod, @NotNull TimeUnit refillUnit) {
        Objects.requireNonNull(refillUnit, "refillUnit must not be null");
        if (maxPermits < 1) throw new IllegalArgumentException("maxPermits must be >= 1");
        if (refillPeriod <= 0) throw new IllegalArgumentException("refillPeriod must be > 0");
        this.maxPermits = maxPermits;

        long periodMs = refillUnit.toMillis(refillPeriod);
        Thread refillThread = Thread.ofVirtual()
                .name("rate-limiter-refill")
                .start(() -> {
                    while (!Thread.currentThread().isInterrupted()) {
                        try {
                            refillUnit.sleep(refillPeriod);
                            refillAll();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    }
                });
        // Daemon behavior: the virtual thread terminates when the JVM does, so no
        // explicit shutdown is required.
        logger.debug("[RateLimiter] Started refill thread (maxPermits={}, period={}ms)",
                maxPermits, periodMs);
    }

    /**
     * Attempts to acquire a permit for the given key without blocking.
     * Returns {@code true} if the permit was acquired, {@code false} if the bucket is empty.
     *
     * @param key the key identifying the rate-limited domain, must not be {@code null}
     * @return {@code true} if a permit was acquired
     * @throws NullPointerException if {@code key} is {@code null}
     */
    public boolean tryAcquire(@NotNull K key) {
        Objects.requireNonNull(key, "key must not be null");
        return buckets.computeIfAbsent(key, k -> new Semaphore(maxPermits, true))
                .tryAcquire();
    }

    /**
     * Attempts to acquire a permit for the given key, waiting up to {@code timeout} if none are available.
     *
     * @param key     the key identifying the rate-limited domain, must not be {@code null}
     * @param timeout maximum time to wait
     * @param unit    time unit for {@code timeout}, must not be {@code null}
     * @return {@code true} if a permit was acquired within the timeout
     * @throws InterruptedException if the thread is interrupted while waiting
     * @throws NullPointerException if {@code key} or {@code unit} is {@code null}
     */
    public boolean tryAcquire(@NotNull K key, long timeout, @NotNull TimeUnit unit) throws InterruptedException {
        Objects.requireNonNull(key, "key must not be null");
        Objects.requireNonNull(unit, "unit must not be null");
        return buckets.computeIfAbsent(key, k -> new Semaphore(maxPermits, true))
                .tryAcquire(timeout, unit);
    }

    /**
     * Returns the number of available permits for the given key.
     * Useful for monitoring and diagnostics.
     *
     * @param key the key to inspect, must not be {@code null}
     * @return available permits (0 to {@code maxPermits})
     */
    public int availablePermits(@NotNull K key) {
        Objects.requireNonNull(key, "key must not be null");
        Semaphore bucket = buckets.get(key);
        return bucket == null ? maxPermits : bucket.availablePermits();
    }

    /**
     * Replenishes all existing buckets back to {@code maxPermits}.
     * Called periodically by the background refill thread.
     */
    private void refillAll() {
        buckets.forEach((key, semaphore) -> {
            int current = semaphore.availablePermits();
            int deficit = maxPermits - current;
            if (deficit > 0) {
                semaphore.release(deficit);
            }
        });
    }
}
