package studio.oneeyedwillie.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RemoteSessionTest {
    private fun server(id: String, identity: String, online: Boolean, address: String?) =
        YarrAccount.RemoteServer(id, identity, "Home $id", online, address)

    @Test fun prefersTheTvsOwnHomeServer() {
        val list = listOf(server("a", "id-a", true, "https://1-2-3-4.sslip.io"),
                          server("b", "id-b", false, "https://5-6-7-8.sslip.io"))
        assertEquals("b", RemoteSession.chooseServer(list, "id-b")?.id)
    }

    @Test fun otherwiseAnOnlineServerWithAnAddress() {
        val list = listOf(server("a", "id-a", false, "https://1-2-3-4.sslip.io"),
                          server("b", "id-b", true, null),
                          server("c", "id-c", true, "https://9-9-9-9.sslip.io"))
        assertEquals("c", RemoteSession.chooseServer(list, "unknown")?.id)
        assertEquals("a", RemoteSession.chooseServer(list.take(2), null)?.id)
    }

    @Test fun noServerWithoutAnAddress() {
        assertNull(RemoteSession.chooseServer(listOf(server("a", "id-a", true, null)), "id-a"))
        assertNull(RemoteSession.chooseServer(emptyList(), null))
    }

    @Test fun renewsWellBeforeExpiry() {
        val now = 1_000_000_000L
        assertFalse(RemoteSession.needsRefresh(now + 60 * 60 * 1000L, now))
        assertFalse(RemoteSession.needsRefresh(now + 16 * 60 * 1000L, now))
        assertTrue(RemoteSession.needsRefresh(now + 14 * 60 * 1000L, now))
        assertTrue(RemoteSession.needsRefresh(now - 1, now))
    }

    @Test fun passOnlyGoesToTheRemoteServerOverHttps() {
        val s = RemoteSession.Active("https://1-2-3-4.sslip.io", "a", "PASS", 0L)
        assertEquals("Yarr-Pass PASS", RemoteSession.authorizationFor("https://1-2-3-4.sslip.io/api/playback/5/stream", s))
        assertEquals("Yarr-Pass PASS", RemoteSession.authorizationFor("https://1-2-3-4.SSLIP.io:443/hls/x.m3u8", s))
        assertNull(RemoteSession.authorizationFor("https://evil.example/api", s))
        assertNull(RemoteSession.authorizationFor("http://1-2-3-4.sslip.io/api", s))
        assertNull(RemoteSession.authorizationFor("https://1-2-3-4.sslip.io:8443/api", s))
        assertNull(RemoteSession.authorizationFor("https://user@1-2-3-4.sslip.io/api", s))
        assertNull(RemoteSession.authorizationFor("https://1-2-3-4.sslip.io/api", null))
        val plain = RemoteSession.Active("http://192.168.1.5:8787", "a", "PASS", 0L)
        assertNull(RemoteSession.authorizationFor("http://192.168.1.5:8787/api", plain))
    }

    @Test fun cookieMatchesWhatTheServerSets() {
        val now = 1_000_000_000L
        val s = RemoteSession.Active("https://1-2-3-4.sslip.io", "a", "PASS", now + 3_600_000L)
        assertEquals("yarr_pass=PASS; Path=/; Max-Age=3600; Secure; HttpOnly; SameSite=Lax", RemoteSession.cookieFor(s, now))
        assertTrue(RemoteSession.cookieFor(s.copy(expiresAtMillis = now - 5), now).contains("Max-Age=1;"))
    }

    @Test fun passReplies() {
        assertEquals(YarrAccount.PassReply.Granted("P", 5L, "https://x.example"),
            YarrAccount.passOutcome(200, null, "P", 5L, "https://x.example"))
        assertEquals(YarrAccount.PassReply.Granted("P", 5L, null),
            YarrAccount.passOutcome(200, null, "P", 5L, "http://x.example"))
        assertEquals(YarrAccount.PassReply.ProRequired, YarrAccount.passOutcome(402, "pro_required", null, null, null))
        assertEquals(YarrAccount.PassReply.SignedOut, YarrAccount.passOutcome(401, "unauthorized", null, null, null))
        assertEquals(YarrAccount.PassReply.ServerNotFound, YarrAccount.passOutcome(404, "server_not_found", null, null, null))
        assertTrue(YarrAccount.passOutcome(503, "passes_not_configured", null, null, null) is YarrAccount.PassReply.Failed)
        assertTrue(YarrAccount.passOutcome(200, null, "P", null, null) is YarrAccount.PassReply.Failed)
    }
}
