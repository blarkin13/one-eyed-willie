package studio.oneeyedwillie.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ShellLogicTest {
    @Test fun pathsMapToTabs() {
        assertEquals("home", ShellLogic.tabFor("/"))
        assertEquals("home", ShellLogic.tabFor(""))
        assertEquals("movies", ShellLogic.tabFor("/movies"))
        assertEquals("movies", ShellLogic.tabFor("/movie"))
        assertEquals("tv", ShellLogic.tabFor("/tv/season"))
        assertEquals("music", ShellLogic.tabFor("/music"))
        assertEquals("", ShellLogic.tabFor("/watch/12"))
        assertEquals("more", ShellLogic.tabFor("/settings/libraries"))
        assertEquals("more", ShellLogic.tabFor("/integrations"))
        assertEquals("more", ShellLogic.tabFor("/tvguide"))
    }

    @Test fun tabRoots() {
        assertTrue(ShellLogic.isTabRoot("/movies"))
        assertTrue(ShellLogic.isTabRoot(""))
        assertFalse(ShellLogic.isTabRoot("/movie"))
        assertFalse(ShellLogic.isTabRoot("/tv/show"))
    }

    @Test fun moreSheetHoldsTheServerPages() {
        val links = listOf(
            ShellLogic.NavLink("home", "/", "Home"),
            ShellLogic.NavLink("movies", "/movies", "Movies"),
            ShellLogic.NavLink("music", "/music", "Music"),
            ShellLogic.NavLink("library:4", "/movies?library_id=4", "Kids"),
            ShellLogic.NavLink("", "/services", "Services", "services"),
            ShellLogic.NavLink("", "/radarr", "Radarr", "radarr"),
            ShellLogic.NavLink("connections", "/integrations", "Integrations"),
            ShellLogic.NavLink("connections", "/integrations", "Integrations"),
            ShellLogic.NavLink("settings", "/settings", "Settings"),
            ShellLogic.NavLink("x", "https://evil.example/", "Elsewhere"),
            ShellLogic.NavLink("y", "/blank", " "))
        assertEquals(listOf("Kids", "Services", "Integrations", "Settings"), ShellLogic.moreLinks(links).map { it.name })
        assertTrue(ShellLogic.hasMusic(links))
        assertFalse(ShellLogic.hasMusic(links.filter { it.id != "music" }))
    }

    @Test fun serviceDashboardsStayWhenThereIsNoHub() {
        val links = listOf(ShellLogic.NavLink("", "/radarr", "Radarr", "radarr"))
        assertEquals(listOf("Radarr"), ShellLogic.moreLinks(links).map { it.name })
    }

    @Test fun sidewaysSwipesAreNotPullToRefresh() {
        assertTrue(ShellLogic.isSideways(40f, 12f, 16f))     // along a poster row, drifting down
        assertTrue(ShellLogic.isSideways(-40f, 30f, 16f))
        assertFalse(ShellLogic.isSideways(10f, 40f, 16f))    // a real pull down
        assertFalse(ShellLogic.isSideways(8f, 2f, 16f))      // not moved enough to decide
    }
}
