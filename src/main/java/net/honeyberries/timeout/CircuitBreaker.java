package net.honeyberries.timeout;

import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * A simple circuit-breaker implementation that prevents cascading failures against an external resource.
 * <p>
 * The breaker cycles through three states:
 * <ul>
 *   <li><b>CLOSED</b> — normal operation; each failure increments a counter.</li>
 *   <li><b>OPEN</b>   — breaker tripped; all calls fail fast with {@link CircuitOpenException}
 *                        without touching the downstream system.</li>
 *   <li><b>HALF_OPEN</b> — one probe call is allowed through after the reset timeout elapses;
 *                           success closes the breaker, failure re-opens it.</li>
 * </ul>
 *
 * <p>This implementation is thread-safe.
 *
 * <p>Example usage:
 * <pre>{@code
 * CircuitBreaker breaker = new CircuitBreaker("AI-inference", 5, Duration.ofMinutes(1));
 *
 * try {
 *     String result = breaker.execute(() -> callExternalApi());
 * } catch (CircuitBreaker.CircuitOpenException e) {
 *     // fast-fail path
 * } catch (Exception e) {
 *     // actual error from the external call
 * }
 * }</pre>
 */
public class CircuitBreaker {

    private static final Logger logger = LoggerFactory.getLogger(CircuitBreaker.class);

    /** Possible states of the circuit breaker. */
    public enum State { CLOSED, OPEN, HALF_OPEN }

    private final String name;
    private final int failureThreshold;
    private final long resetTimeoutMs;

    private final AtomicInteger failureCount = new AtomicInteger(0);
    private final AtomicReference<State> state = new AtomicReference<>(State.CLOSED);
    private final AtomicLong openedAt = new AtomicLong(0);

    /**
     * Constructs a circuit breaker with the given policy.
     *
     * @param name             descriptive name used in log messages, must not be {@code null}
     * @param failureThreshold number of consecutive failures required to trip the breaker, must be >= 1
     * @param resetTimeoutMs   milliseconds to wait in OPEN state before attempting a probe, must be >= 0
     * @throws NullPointerException     if {@code name} is {@code null}
     * @throws IllegalArgumentException if threshold or timeout are out of range
     */
    public CircuitBreaker(@NotNull String name, int failureThreshold, long resetTimeoutMs) {
        this.name = Objects.requireNonNull(name, "name must not be null");
        if (failureThreshold < 1) throw new IllegalArgumentException("failureThreshold must be >= 1");
        if (resetTimeoutMs < 0) throw new IllegalArgumentException("resetTimeoutMs must be >= 0");
        this.failureThreshold = failureThreshold;
        this.resetTimeoutMs = resetTimeoutMs;
    }

    /**
     * Returns the current state of the circuit breaker.
     *
     * @return current {@link State}, never {@code null}
     */
    @NotNull
    public State getState() {
        maybeTransitionToHalfOpen();
        return state.get();
    }

    /**
     * Executes the callable through the circuit breaker.
     * <p>
     * Succeeds and resets the failure counter if the call completes normally.
     * On failure, increments the counter and opens the breaker when the threshold is reached.
     * Throws {@link CircuitOpenException} immediately when the breaker is OPEN.
     *
     * @param <T>      return type
     * @param callable the operation to guard, must not be {@code null}
     * @return the callable's result
     * @throws CircuitOpenException if the breaker is currently OPEN
     * @throws Exception            any exception thrown by the callable itself
     * @throws NullPointerException if {@code callable} is {@code null}
     */
    public <T> T execute(@NotNull Callable<T> callable) throws Exception {
        Objects.requireNonNull(callable, "callable must not be null");
        maybeTransitionToHalfOpen();

        State current = state.get();
        if (current == State.OPEN) {
            throw new CircuitOpenException("Circuit breaker '" + name + "' is OPEN — call rejected");
        }

        try {
            T result = callable.call();
            onSuccess();
            return result;
        } catch (CircuitOpenException e) {
            throw e;
        } catch (Exception e) {
            onFailure();
            throw e;
        }
    }

    /**
     * Records a successful call, resetting the failure counter and closing the breaker.
     */
    private void onSuccess() {
        failureCount.set(0);
        if (state.compareAndSet(State.HALF_OPEN, State.CLOSED)) {
            logger.info("[CircuitBreaker:{}] Probe succeeded — breaker CLOSED", name);
        }
    }

    /**
     * Records a failed call. Opens the breaker when the failure threshold is crossed.
     */
    private void onFailure() {
        int failures = failureCount.incrementAndGet();
        if (failures >= failureThreshold) {
            if (state.compareAndSet(State.CLOSED, State.OPEN)
                    || state.compareAndSet(State.HALF_OPEN, State.OPEN)) {
                openedAt.set(System.currentTimeMillis());
                logger.warn("[CircuitBreaker:{}] Failure threshold ({}) reached — breaker OPEN",
                        name, failureThreshold);
            }
        }
    }

    /**
     * Transitions from OPEN to HALF_OPEN once the reset timeout has elapsed,
     * allowing one probe call through to test if the resource has recovered.
     */
    private void maybeTransitionToHalfOpen() {
        if (state.get() == State.OPEN) {
            long elapsed = System.currentTimeMillis() - openedAt.get();
            if (elapsed >= resetTimeoutMs) {
                if (state.compareAndSet(State.OPEN, State.HALF_OPEN)) {
                    logger.info("[CircuitBreaker:{}] Reset timeout elapsed — breaker HALF_OPEN (probe attempt)",
                            name);
                }
            }
        }
    }

    /**
     * Thrown when the circuit breaker is in OPEN state and rejects a call without
     * executing it.
     */
    public static class CircuitOpenException extends RuntimeException {
        /**
         * Constructs a new exception with the supplied message.
         *
         * @param message detail message, must not be {@code null}
         */
        public CircuitOpenException(@NotNull String message) {
            super(Objects.requireNonNull(message, "message must not be null"));
        }
    }
}
