package studio.oneeyedwillie.tv

import androidx.media3.common.PlaybackException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaybackRecoveryTest {
    private val network = PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED
    private val decoder = PlaybackException.ERROR_CODE_DECODING_FAILED

    @Test fun directNetworkBlipRetriesTheSameSource() {
        assertEquals(RecoveryAction.RETRY_SAME_SOURCE,
            PlaybackRecovery.decide(network, hlsMode = false, attempts = 0, fallbackUsed = false))
    }

    @Test fun directNetworkRetriesAreBoundedThenFallBackOnce() {
        val last = PlaybackRecovery.MAX_ATTEMPTS
        assertEquals(RecoveryAction.FALLBACK_TO_HLS,
            PlaybackRecovery.decide(network, false, last, fallbackUsed = false))
        assertEquals(RecoveryAction.GIVE_UP,
            PlaybackRecovery.decide(network, false, last, fallbackUsed = true))
    }

    @Test fun expiredOrDroppedTranscodeRestartsTheSessionInsteadOfFailing() {
        for (code in listOf(
            PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS,       // 404 "Stream expired"
            PlaybackException.ERROR_CODE_BEHIND_LIVE_WINDOW,
            PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT)) {
            assertEquals(RecoveryAction.RESTART_HLS,
                PlaybackRecovery.decide(code, hlsMode = true, attempts = 1, fallbackUsed = false))
        }
        assertEquals(RecoveryAction.GIVE_UP,
            PlaybackRecovery.decide(network, true, PlaybackRecovery.MAX_ATTEMPTS, false))
    }

    @Test fun decoderFailuresTranscodeImmediatelyAndNeverRetry() {
        assertEquals(RecoveryAction.FALLBACK_TO_HLS,
            PlaybackRecovery.decide(decoder, hlsMode = false, attempts = 0, fallbackUsed = false))
        assertEquals(RecoveryAction.GIVE_UP,
            PlaybackRecovery.decide(decoder, hlsMode = false, attempts = 0, fallbackUsed = true))
        assertEquals(RecoveryAction.GIVE_UP,
            PlaybackRecovery.decide(decoder, hlsMode = true, attempts = 0, fallbackUsed = false))
    }

    @Test fun backoffGrowsAndIsCapped() {
        assertEquals(1500L, PlaybackRecovery.backoffMs(1))
        assertEquals(3000L, PlaybackRecovery.backoffMs(2))
        assertEquals(6000L, PlaybackRecovery.backoffMs(10))
        assertEquals(1500L, PlaybackRecovery.backoffMs(0))
    }

    @Test fun qualityIdsAreValidatedAndMapToServerValues() {
        assertEquals(Quality.AUTO, Quality.normalize(null))
        assertEquals(Quality.AUTO, Quality.normalize("4k"))
        assertEquals("480p", Quality.normalize("480p"))
        assertEquals("720p", Quality.transcodeParam(Quality.AUTO))
        assertEquals("1080p", Quality.transcodeParam("1080p"))
        assertTrue(Quality.allowsDirect(Quality.AUTO))
        assertFalse(Quality.allowsDirect("1080p"))
        assertEquals(listOf("auto", "1080p", "720p", "480p", "360p"), Quality.options.map { it.id })
    }
}
