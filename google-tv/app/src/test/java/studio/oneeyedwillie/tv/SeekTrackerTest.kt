package studio.oneeyedwillie.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SeekTrackerTest {
    private val duration = 7200.0

    @Test
    fun repeatedForwardPressesAccumulateFromTheRequestedPosition() {
        val seek = SeekTracker()
        // The decoder keeps reporting 600s: nothing has been committed yet.
        repeat(5) { seek.requestBy(10.0, actual = 600.0, duration = duration) }
        assertEquals(650.0, seek.pendingTarget()!!, 0.0)
        assertEquals(650.0, seek.displayed(actual = 600.0), 0.0)
    }

    @Test
    fun rewindAccumulatesAndClampsAtZero() {
        val seek = SeekTracker()
        repeat(3) { seek.requestBy(-10.0, actual = 25.0, duration = duration) }
        assertEquals(0.0, seek.pendingTarget()!!, 0.0)
        seek.requestBy(-10.0, actual = 25.0, duration = duration)
        assertEquals(0.0, seek.pendingTarget()!!, 0.0)
    }

    @Test
    fun forwardClampsAtDuration() {
        val seek = SeekTracker()
        repeat(10) { seek.requestBy(10.0, actual = 7190.0, duration = duration) }
        assertEquals(duration, seek.pendingTarget()!!, 0.0)
    }

    @Test
    fun reversingDirectionBeforeCommitUsesTheNewestTarget() {
        val seek = SeekTracker()
        repeat(4) { seek.requestBy(10.0, 100.0, duration) }     // 140
        repeat(6) { seek.requestBy(-10.0, 100.0, duration) }    // 80
        assertEquals(80.0, seek.pendingTarget()!!, 0.0)
    }

    @Test
    fun onlyTheLatestGenerationCanBeCommitted() {
        val seek = SeekTracker()
        val first = seek.requestBy(10.0, 100.0, duration)
        val second = seek.requestBy(10.0, 100.0, duration)
        // The debounce for `first` fires late, after `second` was requested.
        assertNull(seek.beginCommit(first))
        assertEquals(120.0, seek.beginCommit(second)!!, 0.0)
    }

    @Test
    fun targetIsKeptUntilTheSeekLands() {
        val seek = SeekTracker()
        val generation = seek.requestBy(10.0, 100.0, duration)
        seek.beginCommit(generation)
        // HLS restart in flight: the player still reports the old position.
        assertTrue(seek.hasPending())
        assertEquals(110.0, seek.displayed(actual = 100.0), 0.0)
        assertTrue(seek.settle(generation))
        assertFalse(seek.hasPending())
        assertEquals(111.0, seek.displayed(actual = 111.0), 0.0)
    }

    @Test
    fun pressesDuringAnInFlightRestartBuildOnThePendingTargetNotTheStalePlayerPosition() {
        val seek = SeekTracker()
        val restart = seek.requestBy(10.0, 100.0, duration)       // 110
        seek.beginCommit(restart)                                 // HLS restart begins
        // Player is stopped and still says 100 while two more presses arrive.
        seek.requestBy(10.0, actual = 100.0, duration = duration)
        seek.requestBy(10.0, actual = 100.0, duration = duration)
        assertEquals(130.0, seek.pendingTarget()!!, 0.0)
    }

    @Test
    fun aStaleRestartCompletingLateCannotClearOrOverwriteANewerRequest() {
        val seek = SeekTracker()
        val older = seek.requestBy(10.0, 100.0, duration)         // 110
        seek.beginCommit(older)
        val newer = seek.requestBy(10.0, 100.0, duration)         // 120
        // The older asynchronous seek finishes after the newer request.
        assertFalse(seek.settle(older))
        assertEquals(120.0, seek.pendingTarget()!!, 0.0)
        assertEquals(120.0, seek.beginCommit(newer)!!, 0.0)
        assertTrue(seek.settle(newer))
        assertNull(seek.pendingTarget())
    }

    @Test
    fun absoluteRequestsReplaceThePendingTarget() {
        val seek = SeekTracker()
        seek.requestBy(10.0, 500.0, duration)
        seek.requestTo(0.0, duration)                             // Play from beginning
        assertEquals(0.0, seek.pendingTarget()!!, 0.0)
    }

    @Test
    fun unknownDurationStillAllowsForwardSeeks() {
        val seek = SeekTracker()
        seek.requestBy(10.0, 30.0, duration = 0.0)
        assertEquals(40.0, seek.pendingTarget()!!, 0.0)
    }

    @Test
    fun cancelDropsThePendingTargetAndInvalidatesOutstandingGenerations() {
        val seek = SeekTracker()
        val generation = seek.requestBy(10.0, 100.0, duration)
        seek.cancel()
        assertNull(seek.pendingTarget())
        assertNull(seek.beginCommit(generation))
        assertFalse(seek.settle(generation))
    }

    @Test
    fun nonFinitePositionsAreSanitised() {
        val seek = SeekTracker()
        seek.requestTo(Double.NaN, duration)
        assertEquals(0.0, seek.pendingTarget()!!, 0.0)
        seek.requestTo(Double.POSITIVE_INFINITY, duration)
        assertEquals(duration, seek.pendingTarget()!!, 0.0)
    }

    @Test
    fun simulatedHeldButtonYieldsOneCommitAtTheAccumulatedTarget() {
        // 30 repeats 190ms apart; the 220ms debounce is restarted by each, so
        // exactly one commit (the newest generation) survives.
        val seek = SeekTracker()
        val generations = (1..30).map { seek.requestBy(10.0, actual = 1000.0, duration = duration) }
        val committed = generations.mapNotNull { seek.beginCommit(it) }
        assertEquals(listOf(1300.0), committed)
        assertNotNull(seek.pendingTarget())
    }
}

class LatestWinsTest {
    @Test
    fun onlyTheNewestStartIsCurrent() {
        val starts = LatestWins()
        val first = starts.next()
        val second = starts.next()
        assertFalse(starts.isCurrent(first))
        assertTrue(starts.isCurrent(second))
    }

    @Test
    fun outOfOrderCompletionsOnlyApplyTheNewest() {
        val starts = LatestWins()
        val applied = mutableListOf<String>()
        val a = starts.next()
        val b = starts.next()
        // b finishes first, then the slower a. a must not clobber b.
        if (starts.isCurrent(b)) applied += "b"
        if (starts.isCurrent(a)) applied += "a"
        assertEquals(listOf("b"), applied)
    }

    @Test
    fun invalidateSupersedesEverythingInFlight() {
        val starts = LatestWins()
        val serial = starts.next()
        starts.invalidate()
        assertFalse(starts.isCurrent(serial))
    }
}
