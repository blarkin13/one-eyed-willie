package studio.oneeyedwillie.tv

import java.util.concurrent.atomic.AtomicLong

/**
 * Single source of truth for remote-control seeking.
 *
 * A seek has two phases: the viewer *requests* positions (possibly many times
 * while a button is held) and, after a short pause, one request is *committed*
 * to the player. For direct play the player reflects the new position at once;
 * for HLS the transcoder may have to restart at the new offset, which takes
 * seconds. Throughout that time the tracker keeps the viewer's requested target,
 * so
 *
 *  * further presses accumulate from the REQUESTED position, never from a stale
 *    player position;
 *  * the seek bar and clock show the requested position until the seek lands;
 *  * every request gets a new generation number, so the completion of an older
 *    asynchronous seek (a slow HLS restart) can be recognised as stale and must
 *    not overwrite what a newer request asked for.
 *
 * This class has no Android dependencies so its behaviour is covered by plain
 * JVM unit tests ([SeekTrackerTest]). All calls are made on the main thread
 * except [isCurrent], which is safe to call from any thread.
 */
class SeekTracker {
    @Volatile
    private var generation = 0L
    private var target: Double? = null

    /** The position the viewer last asked for, or null when nothing is pending. */
    fun pendingTarget(): Double? = target

    fun hasPending(): Boolean = target != null

    /** What the seek bar and clock should show right now. */
    fun displayed(actual: Double): Double = target ?: actual

    /**
     * Adds [delta] seconds to the requested position (or to [actual] when no
     * seek is pending) and returns the new generation.
     */
    fun requestBy(delta: Double, actual: Double, duration: Double): Long =
        requestTo((target ?: actual) + delta, duration)

    /** Requests an absolute position and returns the new generation. */
    fun requestTo(position: Double, duration: Double): Long {
        val upper = if (duration > 0 && duration.isFinite()) duration else UNKNOWN_DURATION_LIMIT
        target = if (position.isNaN()) 0.0 else position.coerceIn(0.0, upper)
        generation += 1
        return generation
    }

    /** True while [generation] is the most recent request. */
    fun isCurrent(generation: Long): Boolean = generation == this.generation

    /**
     * Called when the debounce for [generation] fires. Returns the position to
     * apply, or null when a newer request has superseded this one.
     */
    fun beginCommit(generation: Long): Double? {
        if (!isCurrent(generation)) return null
        return target
    }

    /**
     * Called when the player has actually reached the committed position.
     * Returns false (and changes nothing) if a newer request exists, in which
     * case the newer target keeps being displayed and will be committed itself.
     */
    fun settle(generation: Long): Boolean {
        if (!isCurrent(generation)) return false
        target = null
        return true
    }

    /** Forgets any pending request (for example after a failed restart). */
    fun cancel() {
        target = null
        generation += 1
    }

    companion object {
        /** Passed by HLS starts that are not the result of a seek. */
        const val NO_GENERATION = -1L
        const val UNKNOWN_DURATION_LIMIT = 1e7
    }
}

/**
 * "Latest request wins" arbitration for asynchronous work such as starting an
 * HLS session. Every start takes a serial from [next]; when it finishes it must
 * still be [isCurrent] before it may touch the player. Thread-safe.
 */
class LatestWins {
    private val counter = AtomicLong()

    /** Begins a new request, superseding every earlier one. */
    fun next(): Long = counter.incrementAndGet()

    fun isCurrent(serial: Long): Boolean = counter.get() == serial

    /** Supersedes everything in flight without starting anything new. */
    fun invalidate() {
        counter.incrementAndGet()
    }
}
