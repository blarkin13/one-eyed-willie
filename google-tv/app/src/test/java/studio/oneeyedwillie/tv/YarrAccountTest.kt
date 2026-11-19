package studio.oneeyedwillie.tv

import org.junit.Assert.assertEquals
import org.junit.Test

class YarrAccountTest {
    private fun outcome(status: Int, error: String?, token: String? = null, interval: Int? = null) =
        YarrAccount.pollOutcome(status, error, token, interval, 5)

    @Test fun grantedWhenTokenArrives() =
        assertEquals(YarrAccount.Poll.Granted("ydv_abc"), outcome(200, null, "ydv_abc"))

    @Test fun keepsWaitingWhilePending() = assertEquals(YarrAccount.Poll.Pending, outcome(400, "authorization_pending"))

    @Test fun slowsDownAndNeverSpeedsUp() {
        assertEquals(YarrAccount.Poll.SlowDown(10), outcome(400, "slow_down", interval = 10))
        assertEquals(YarrAccount.Poll.SlowDown(10), outcome(400, "slow_down"))
        assertEquals(YarrAccount.Poll.SlowDown(5), outcome(400, "slow_down", interval = 1))
        assertEquals(YarrAccount.Poll.SlowDown(30), outcome(400, "slow_down", interval = 99))
    }

    @Test fun stopsOnDenialOrExpiry() {
        assertEquals(YarrAccount.Poll.Denied, outcome(400, "access_denied"))
        assertEquals(YarrAccount.Poll.Expired, outcome(400, "expired_token"))
        assertEquals(YarrAccount.Poll.Expired, outcome(400, "invalid_grant"))
    }

    @Test fun unexpectedRepliesAreFailures() =
        assertEquals(YarrAccount.Poll.Failed("Yarr Media returned HTTP 503"), outcome(503, null))
}
