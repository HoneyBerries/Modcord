package net.honeyberries.util;

import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;
import java.util.concurrent.Callable;

/**
 * Executes a callable with exponential-backoff retry logic.
 * <p>
 * Each attempt waits {@code baseDelayMs * 2^(attempt-1)} milliseconds before the next try.
 * If all attempts fail the last exception is re-thrown, preserving the original stack trace.
 * Thread-safe and stateless — a single instance can be shared across the whole application.
 *
 * <p>Example usage:
 * <pre>{@code
 * RetryExecutor retry = new RetryExecutor(3, 500);
 * String result = retry.execute("fetch user", () -> discord.retrieveUserById(id).complete());
 * }</pre>
 */
public class RetryExecutor {

    private static final Logger logger = LoggerFactory.getLogger(RetryExecutor.class);

    /** Maximum number of attempts (including the first). */
    private final int maxAttempts;
    /** Base delay in milliseconds; doubled for each subsequent attempt. */
    private final long baseDelayMs;

    /**
     * Constructs a {@code RetryExecutor} with the given retry policy.
     *
     * @param maxAttempts total attempts allowed, must be >= 1
     * @param baseDelayMs base exponential-backoff delay in milliseconds, must be >= 0
     * @throws IllegalArgumentException if {@code maxAttempts} < 1 or {@code baseDelayMs} < 0
     */
    public RetryExecutor(int maxAttempts, long baseDelayMs) {
        if (maxAttempts < 1) throw new IllegalArgumentException("maxAttempts must be >= 1, got " + maxAttempts);
        if (baseDelayMs < 0) throw new IllegalArgumentException("baseDelayMs must be >= 0, got " + baseDelayMs);
        this.maxAttempts = maxAttempts;
        this.baseDelayMs = baseDelayMs;
    }

    /**
     * Executes the supplied callable, retrying on any exception up to {@code maxAttempts} times.
     * A descriptive {@code operationName} is included in log messages so failures are easy to trace.
     *
     * @param <T>           return type of the callable
     * @param operationName short label used in log messages, must not be {@code null}
     * @param callable      the operation to execute, must not be {@code null}
     * @return the value returned by the callable on a successful attempt
     * @throws Exception the last exception thrown by the callable if all attempts fail
     * @throws NullPointerException if {@code operationName} or {@code callable} is {@code null}
     */
    public <T> T execute(@NotNull String operationName, @NotNull Callable<T> callable) throws Exception {
        Objects.requireNonNull(operationName, "operationName must not be null");
        Objects.requireNonNull(callable, "callable must not be null");

        Exception lastException = null;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return callable.call();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw e;
            } catch (Exception e) {
                lastException = e;
                if (attempt < maxAttempts) {
                    long delay = baseDelayMs * (1L << (attempt - 1));
                    logger.warn("[RetryExecutor] {} failed on attempt {}/{}, retrying in {}ms: {}",
                            operationName, attempt, maxAttempts, delay, e.getMessage());
                    try {
                        Thread.sleep(delay);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        throw ie;
                    }
                } else {
                    logger.error("[RetryExecutor] {} failed after {} attempts: {}",
                            operationName, maxAttempts, e.getMessage());
                }
            }
        }

        assert lastException != null;
        throw lastException;
    }

    /**
     * Executes the supplied callable, swallowing all exceptions and returning {@code null} after
     * all retries are exhausted. Useful for best-effort operations where the caller does not need
     * to distinguish a failure from a {@code null} result.
     *
     * @param <T>           return type of the callable
     * @param operationName short label used in log messages, must not be {@code null}
     * @param callable      the operation to execute, must not be {@code null}
     * @return the callable's result, or {@code null} if all attempts fail
     */
    public <T> T executeOrNull(@NotNull String operationName, @NotNull Callable<T> callable) {
        try {
            return execute(operationName, callable);
        } catch (Exception e) {
            return null;
        }
    }
}
