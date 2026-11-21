package studio.oneeyedwillie.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineLogicTest {
    @Test fun sizesAndQualityLabels() {
        assertEquals("1.2 GB", OfflineLogic.sizeLabel(1_234_000_000))
        assertEquals("850 MB", OfflineLogic.sizeLabel(850_000_000))
        assertEquals("", OfflineLogic.sizeLabel(0))
        assertEquals("720p · about 1.1 GB", OfflineLogic.qualityLabel("720p", 1_100_000_000, "about"))
        assertEquals("1080p · up to 3.6 GB", OfflineLogic.qualityLabel("1080p", 3_600_000_000, "up_to"))
        assertEquals("480p", OfflineLogic.qualityLabel("480p", 0, "about"))
    }

    @Test fun resumingDownloads() {
        assertNull(OfflineLogic.rangeHeader(0))
        assertEquals("bytes=500-", OfflineLogic.rangeHeader(500))
        assertTrue(OfflineLogic.resumes(206, 500))
        assertFalse("a full answer means start over", OfflineLogic.resumes(200, 500))
        assertEquals(1000, OfflineLogic.totalBytes("bytes 500-999/1000", 500, 500, true))
        assertEquals(1000, OfflineLogic.totalBytes(null, 500, 500, true))
        assertEquals(800, OfflineLogic.totalBytes(null, 800, 500, false))
        assertEquals(-1, OfflineLogic.totalBytes(null, -1, 0, false))
    }

    @Test fun watchedAndResume() {
        assertTrue(OfflineLogic.watched(95_000, 100_000))
        assertFalse(OfflineLogic.watched(90_000, 100_000))
        assertEquals(0, OfflineLogic.resumeFrom(10_000, 3_600_000))
        assertEquals(600_000, OfflineLogic.resumeFrom(600_000, 3_600_000))
        assertEquals(0, OfflineLogic.resumeFrom(3_500_000, 3_600_000))
    }

    @Test fun statusLines() {
        assertEquals("Preparing on your server · 40%", OfflineLogic.statusLine("preparing", 0.4, 0, null))
        assertEquals("Downloading · 12%", OfflineLogic.statusLine("downloading", 0.125, 0, null))
        assertEquals("2.0 GB", OfflineLogic.statusLine("done", 1.0, 2_000_000_000, null))
        assertEquals("Downloads need Pro", OfflineLogic.statusLine("failed", 0.0, 0, "Downloads need Pro"))
        assertEquals("srv#12", OfflineLogic.key("srv", 12))
    }
}
