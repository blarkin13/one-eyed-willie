"""Static regressions for the content-first Yarr Media layout."""
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server"


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.scripts = []
    def handle_starttag(self, tag, attrs):
        if tag == "script" and not dict(attrs).get("src"):
            self.inside = True
            self.scripts.append("")
    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False
    def handle_data(self, data):
        if self.inside:
            self.scripts[-1] += data


class CompactLayoutTests(unittest.TestCase):
    def test_home_has_only_media_shelves_not_hero(self):
        page = (SERVER / "dashboard.html").read_text()
        for heading in ("Continue Watching", "Recently Added Movies",
                        "Recently Added TV Shows"):
            self.assertIn(heading, page)
        self.assertNotIn("Your movies and shows, all in one place", page)
        self.assertNotIn('id="movie-count"', page)
        self.assertNotIn('id="show-count"', page)
        self.assertNotIn('class="page-head"', page)
        self.assertIn('class="sr-only">Home', page)

    def test_home_selected_poster_shows_cinematic_details_above_each_shelf(self):
        page = (SERVER / "dashboard.html").read_text()
        self.assertIn("function makeHomeFeature(shelf)", page)
        self.assertIn("shelf.insertBefore(feature,shelf.querySelector('.section-heading'))", page)
        self.assertIn("function updateHomeFeature(link,item)", page)
        self.assertIn("link._homeItem=item", page)
        self.assertIn("document.addEventListener('focusin',selectHomePoster,true)", page)
        self.assertIn("document.addEventListener('pointerover',selectHomePoster", page)
        self.assertIn("const first=track.querySelector('.tile-button')", page)
        self.assertIn("updateHomeFeature(first,first._homeItem)", page)
        self.assertIn("const label=item.kind==='tv'?'TV SERIES':'MOVIE'", page)
        self.assertIn("item.play_state==='next'?'UP NEXT':'CONTINUE WATCHING'", page)
        self.assertIn("info.overview", page)
        self.assertIn("info.content_rating", page)
        self.assertIn("info.network", page)
        self.assertIn("info.certification", page)
        self.assertIn("info.tmdb_rating", page)
        self.assertIn("info.genres", page)

    def test_phone_home_shelves_do_not_force_full_screen_and_hide_posters(self):
        home = (SERVER / "dashboard.html").read_text()
        self.assertIn('body[data-page="home"] .shelf{', home)
        self.assertIn('height:auto;min-height:0;max-height:none;overflow:visible;', home)
        self.assertIn('body[data-page="home"] .home-feature{', home)
        self.assertIn('flex:0 0 auto;min-height:0;height:auto;max-height:none;', home)
        self.assertIn("String(item.subtitle).trim()!==String(year||'').trim()", home)

    def test_mobile_show_details_do_not_reserve_loading_space(self):
        show = (SERVER / "tv_detail.html").read_text()
        self.assertIn("#loading:empty{display:none}", show)
        self.assertIn('body[data-page="tv"]:not(.tv-season-mode) .workspace>.content', show)
        self.assertIn('padding-top:34px!important;', show)
        self.assertIn('body[data-page="tv"]:not(.tv-season-mode) .tv-show-hero', show)

    def test_home_details_use_global_backdrop_and_fixed_layout_to_prevent_jumps(self):
        page = (SERVER / "dashboard.html").read_text()
        self.assertIn("const serial=++state.serial", page)
        self.assertIn("if(state.serial!==serial)return", page)
        self.assertIn("homeDetailsCache=new Map()", page)
        # Home sections are viewport-height flex columns; the details block
        # fills the space above the poster rail instead of a fixed clamp.
        self.assertIn("height:auto;flex:1 1 auto;min-height:0;max-height:none", page)
        self.assertIn("border:0;border-radius:0;background:transparent", page)
        self.assertIn("height:2.16em;min-height:2.16em", page)
        self.assertIn("height:24px;min-height:24px", page)
        self.assertIn("height:4.29em;min-height:4.29em", page)
        self.assertIn("copy.append(kicker,title,meta,summary,genres,cast);feature.append(copy)", page)
        self.assertNotIn("home-feature-art", page)
        self.assertNotIn("setHomeFeatureArt", page)
        self.assertNotIn("validHomeArt", page)
        self.assertNotIn("translateY(7px)", page)
        self.assertIn("prefers-reduced-motion:reduce", page)
        # No fixed full-page backdrop (it caused jumps). The only fixed element
        # is the long-press context menu popup, which must stay on screen.
        self.assertEqual(page.count("position:fixed"), 1)
        self.assertIn(".continue-menu{position:fixed;", page)

    def test_google_tv_home_dpad_moves_by_shelf_with_animated_scroll(self):
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" /
                   "java" / "studio" / "oneeyedwillie" / "tv" /
                   "MainActivity.kt").read_text()
        self.assertIn("document.body.dataset.page==='home'", android)
        self.assertIn("active.closest('.shelf-track,.section-heading')", android)
        self.assertIn("document.querySelectorAll('.content > .shelf')", android)
        self.assertIn("rows[next].querySelectorAll('.shelf-track .tile-button')", android)
        self.assertIn("first.focus({preventScroll:true})", android)
        self.assertIn("row.getBoundingClientRect().top-10", android)
        # Home shelves scroll with the shared glide animator (cancellable, one
        # clock) rather than the browser's own smooth scrolling.
        self.assertIn("glideTo(root,'top',top)", android)
        self.assertIn("if(document.body.dataset.page==='home' &&", android)
        self.assertIn("shelf.matches('.shelf-track'))return true", android)
        self.assertIn("const delta=r.top<padding?r.top-padding", android)
        self.assertIn("prefers-reduced-motion: reduce", android)

    def test_totals_in_libraries_settings(self):
        page = (SERVER / "index.html").read_text()
        self.assertIn('id="overview-movies"', page)
        self.assertIn('id="overview-tv"', page)
        self.assertIn("loadOverview()", page)

    def test_uploaded_logo_and_favicon_are_served(self):
        for filename in ("logo.png", "favicon.png"):
            file = SERVER / filename
            self.assertTrue(file.is_file())
            self.assertEqual(file.read_bytes()[:8], bytes([137,80,78,71,13,10,26,10]))
            self.assertIn("/assets/" + filename, (SERVER / "main.py").read_text())
        # The brand uses the moon-and-sail logo; the favicon stays in browser tabs.
        self.assertIn("image.src='/assets/logo.svg?v=moon-sail-v1'", (SERVER / "shell.js").read_text())
        self.assertIn("favicon.href='/assets/favicon.png?v=moon-sail-v1'", (SERVER / "shell.js").read_text())

    def test_there_is_no_top_header_or_magnifier(self):
        for page in ("dashboard.html", "catalog.html", "index.html",
                     "remote_settings.html", "metadata_settings.html",
                     "arr_connections.html", "explore.html", "tv_detail.html"):
            text = (SERVER / page).read_text()
            self.assertNotIn('class="topbar"', text, page)
            self.assertNotIn('id="breadcrumbs"', text, page)
        shell = (SERVER / "shell.js").read_text()
        # (fa-magnifying-glass remains as one glyph in the library icon set; it
        # is not a header control.)
        self.assertNotIn("topbar-actions", shell)
        self.assertNotIn("topbar-action", shell)
        self.assertIn(".topbar,.app-topbar{display:none!important}",
                      (SERVER / "ui.css").read_text())

    def test_expanded_brand_matches_supplied_artwork_and_font(self):
        shell = (SERVER / "shell.js").read_text()
        css = (SERVER / "ui.css").read_text()
        self.assertIn("image.src='/assets/logo.svg?v=moon-sail-v1'", shell)
        self.assertNotIn("image.src='/assets/favicon.png'", shell)
        # The wordmark is editable text (YARR . MEDIA), not an image.
        self.assertIn("name.textContent='YARR'", shell)
        self.assertIn("media.textContent='MEDIA'", shell)
        self.assertIn('font-family:"Snell Roundhand"', css)
        self.assertIn(".sidebar:hover,.sidebar:focus-within{width:min(240px", css)
        self.assertNotIn("width:440px", css)
        self.assertNotIn("width:142px", css)
        self.assertIn("width:90px;height:90px", css)
        self.assertIn("brand-logo-frame", shell)
        self.assertIn("overflow:hidden", css)
        self.assertIn("mix-blend-mode:screen", css)
        self.assertIn("object-fit:contain", css)
        self.assertNotIn('font-family:"Pirata One"', css)

    def test_wordmark_appears_only_on_sidebar_expansion(self):
        shell = (SERVER / "shell.js").read_text()
        css = (SERVER / "ui.css").read_text()
        # The old ship-greeting animation was removed. Expansion is still
        # tracked once (not on each navigation focus step) and shows the text
        # wordmark next to the logo; the mobile rail never shows it.
        self.assertNotIn("greeting.textContent='Yarr'", shell)
        self.assertNotIn("willie-ship-greeting", css)
        self.assertIn("target.addEventListener('pointerenter',updateRailGreeting)", shell)
        self.assertIn("target.addEventListener('focusin',updateRailGreeting)", shell)
        self.assertIn("if(open===railExpanded)return", shell)
        self.assertIn("target.classList.toggle('brand-yarr-open',open)", shell)
        self.assertIn("matchMedia('(min-width:701px)')", shell)
        self.assertIn(".sidebar:hover .brand-wordmark,.sidebar:focus-within .brand-wordmark{display:inline-flex}", css)
        self.assertIn(".sidebar:focus-within .brand-wordmark{display:none!important}", css)

    def test_cast_profile_stacks_portrait_above_bio_on_mobile(self):
        page = (SERVER / "person.html").read_text()
        self.assertIn('class="person-hero"', page)
        self.assertIn('class="person-photo-frame"', page)
        self.assertIn('id="person-name"', page)
        self.assertIn('id="person-bio"', page)
        self.assertIn(".person-hero > *{min-width:0}", page)
        self.assertIn(".person-photo-frame{position:relative;width:100%;min-width:0;min-height:0;", page)
        self.assertIn("@media(max-width:700px){", page)
        mobile = page.split("@media(max-width:700px){", 1)[1].split("/* One selectable", 1)[0]
        self.assertIn("grid-template-columns:minmax(0,1fr)", mobile)
        self.assertNotIn("grid-template-columns:105px minmax(0,1fr)", page)
        self.assertIn(".person-credits{grid-template-columns:repeat(2,minmax(0,1fr))", page)

    def test_home_has_explicit_favicon(self):
        home = (SERVER / "dashboard.html").read_text()
        shell = (SERVER / "shell.js").read_text()
        self.assertIn('<link rel="icon" type="image/png" sizes="128x128" href="/assets/favicon.png?v=5">', home)
        self.assertIn("favicon.href='/assets/favicon.png?v=moon-sail-v1'", shell)

    def test_playback_controls_and_fullscreen_request(self):
        player = (SERVER / "player.js").read_text()
        movie = (SERVER / "catalog.html").read_text()
        tv = (SERVER / "tv_detail.html").read_text()
        home = (SERVER / "dashboard.html").read_text()
        self.assertIn("requestFullscreen", player)
        self.assertIn("willie:watch-updated", player)
        self.assertIn("/api/playback/progress", player)
        self.assertIn("/api/watch/", player)
        self.assertIn("'/movie?'", movie)
        self.assertNotIn('id="detail-dialog"', movie)
        full_movie = (SERVER / "movie_detail.html").read_text()
        self.assertIn('id="play-movie"', full_movie)
        self.assertIn('id="resume-movie"', full_movie)
        self.assertIn('aria-label="Play from beginning"', full_movie)
        self.assertIn('aria-label="Resume from saved position"', full_movie)
        self.assertIn('willie-subtitle-select', player)
        self.assertIn('/api/stream/subtitles/', player)
        self.assertIn('id="watched-movie"', full_movie)
        self.assertIn("WilliePlayer.open", full_movie)
        self.assertIn("/api/stream/hls/", player)
        self.assertIn("function playbackButton(", tv)
        self.assertIn("Resume from saved position", tv)
        self.assertIn("WilliePlayer.open", home)
        self.assertIn("Yarr Media", (SERVER / "watch.html").read_text())

    def test_season_focus_selects_and_click_plays_first_unwatched(self):
        tv = (SERVER / "tv_detail.html").read_text()
        self.assertIn("available.find(episode=>!episode.watched)||available[0]", tv)
        self.assertNotIn("available[available.length-1]", tv)
        self.assertIn("button.addEventListener('focus',()=>selectEpisode(episode))", tv)
        self.assertIn("button.onclick=()=>WilliePlayer.open(episode.id", tv)
        self.assertIn("{restart:!canResume(episode)}", tv)
        self.assertIn("return !item.watched&&p>=30&&(d<=0||p<d*.95)", tv)
        self.assertIn("document.addEventListener('willie:watch-updated',refreshEpisodeProgress)", tv)

    def test_watched_indicators_are_anchor_icons_not_checkmarks(self):
        for filename in ("catalog.html", "dashboard.html", "movie_detail.html", "tv_detail.html"):
            page = (SERVER / filename).read_text()
            self.assertIn('cx="12" cy="5" r="3"', page, filename)
            self.assertNotIn("✓ Watched", page, filename)
        tv = (SERVER / "tv_detail.html").read_text()
        self.assertIn("syncEpisodeWatchedBadge", tv)
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" / "java" /
                   "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        self.assertNotIn('.watched-badge::after', android)
        self.assertIn("override fun onResume()", android)
        css = (SERVER / "ui.css").read_text()
        self.assertIn(".watched-badge svg", css)

    def test_small_watched_anchor_badges_on_posters_and_episode_stills(self):
        css = (SERVER / "ui.css").read_text()
        self.assertIn("width:15px;height:15px;padding:0;border-radius:50%", css)
        self.assertIn(".watched-badge svg{display:block;width:10px;height:10px}", css)
        tv = (SERVER / "tv_detail.html").read_text()
        self.assertIn(".season-episode-watched svg{width:10px;height:10px", tv)
        self.assertIn("width:15px;height:15px;border-radius:50%", tv)
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" /
                   "java" / "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        self.assertIn("width:15px!important;height:15px!important", android)
        self.assertIn("width:10px!important;height:10px!important", android)

    def test_stable_tv_season_hero_and_compact_actions(self):
        page = (SERVER / "tv_detail.html").read_text()
        self.assertIn("height:clamp(315px,44vh,400px)", page)
        self.assertIn(".season-episode-summary{height:2.8em", page)
        self.assertIn(".season-episode-format{height:29px", page)
        self.assertIn("grid-auto-columns:clamp(122px,15vw,200px)", page)
        self.assertIn("className", page)
        self.assertIn("option('Shuffle season'", page)
        self.assertIn("option('Fix match'", page)
        self.assertIn("Mark episode unwatched", page)
        self.assertIn("Mark season watched", page)
        self.assertIn("trailerButton(data.show.trailer_key", page)
        self.assertIn("actions.replaceChildren()", page)

    def test_every_episode_down_targets_play_not_cast_or_trailer(self):
        page = (SERVER / "tv_detail.html").read_text()
        self.assertIn("play.id='season-play-button'", page)
        self.assertIn("track.addEventListener('keydown',event=>", page)
        self.assertIn("if(event.key!=='ArrowDown')return", page)
        self.assertIn("action.focus({preventScroll:true})", page)
        self.assertIn("['season-play-button','season-resume-button']", page)
        self.assertIn("episodeTile.focus({preventScroll:true})", page)
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" / "java" /
                   "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        self.assertIn("if(direction==='down'&&active?.matches?.('.season-episode-tile'))", android)
        self.assertIn("document.getElementById('season-play-button')", android)
        self.assertIn("['season-play-button','season-resume-button'].includes(active?.id)", android)
        self.assertIn("Intent.ACTION_VIEW, uri", android)

    def test_quality_on_selected_thumbnail_and_rating_after_duration(self):
        page = (SERVER / "tv_detail.html").read_text()
        self.assertIn("season-video-quality", page)
        self.assertIn("tile.append(badges)", page)
        self.assertNotIn("format.replaceChildren()", page)
        self.assertNotIn("const format=el('div','season-episode-format')", page)
        self.assertIn("previousButton.querySelector('.season-video-quality')?.remove()", page)
        self.assertIn("if(data.show.content_rating)fields.push(data.show.content_rating)", page)
        self.assertIn("season-parental-inline", page)
        self.assertIn("const rt=el('span','season-fact','RT '+score+'%')", page)
        self.assertIn("data.show.rotten_tomatoes", page)
        self.assertIn("data.show.network", page)
        self.assertIn("data.show.genres", page)
        self.assertNotIn("actions.append(el('span','season-actions-label'", page)
        self.assertIn("Reviews · TMDB community", page)
        self.assertIn("const reviews=Array.isArray(data.reviews)", page)
        self.assertNotIn("rtReviewsLink", page)
        self.assertIn("showExtras({...show,title:data.show.title+' Season '", page)
        self.assertIn(".season-support .tv-cast{grid-auto-columns:clamp(76px,8vw,108px)", page)

    def test_enlarged_episode_cards_without_double_focus_boxes(self):
        page = (SERVER / "tv_detail.html").read_text()
        self.assertIn("grid-auto-columns:clamp(168px,20vw,270px)", page)
        self.assertIn("grid-auto-columns:clamp(145px,34vw,218px)", page)
        self.assertIn(".season-episode-tile.is-selected:not(:focus):not(:focus-visible){", page)
        self.assertIn("transform:scale(1.045)!important", page)
        self.assertIn("outline:0!important;box-shadow:none!important", page)

    def test_small_season_menu_keyboard_outside_and_remote_back(self):
        page = (SERVER / "tv_detail.html").read_text()
        self.assertIn("const menu=el('div','season-more-popover')", page)
        self.assertIn("menu.setAttribute('role','menu')", page)
        self.assertIn("document.addEventListener('pointerdown',outside,true)", page)
        self.assertIn("window.__willieCloseSeasonMenu=()=>", page)
        self.assertIn("if(['Escape','Backspace','BrowserBack','GoBack'].includes(event.key))", page)
        self.assertNotIn("const dialog=el('dialog','season-overflow-dialog')", page)
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" / "java" /
                   "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        self.assertIn("if(window.__willieCloseSeasonMenu?.())return 'handled';", android)
        self.assertIn("dialog[open],.season-more-popover", android)

    def test_series_vertical_selection_order_uses_first_of_each_section(self):
        page = (SERVER / "tv_detail.html").read_text()
        self.assertIn("button.id='series-play-button'", page)
        self.assertIn("card.querySelector('.tile-button').id='series-first-season'", page)
        self.assertIn("if(actions && event.key==='ArrowDown')", page)
        self.assertIn("const leftmostAdjacentSeason=(active,direction)=>", page)
        self.assertIn("else if(grid){", page)
        self.assertIn("const nextRow=leftmostAdjacentSeason(active,event.key)", page)
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" / "java" /
                   "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        self.assertIn("const detailSections=()=>", android)
        self.assertIn("if(path==='/tv/show')return [", android)
        self.assertIn("if(moveThroughSections(active,direction))return true", android)
        self.assertIn("scope:'.season-grid'", android)
        self.assertIn("scope:'.movie-detail-actions'", android)
        self.assertIn("const firstPreferred=(selectors)=>", android)
        self.assertIn("for(const raw of selectors.split(','))", android)
        self.assertIn("const item=firstPreferred(lanes[i].first)", android)
        self.assertIn("const firstOfAdjacentGridRow=(active,direction", android)
        self.assertIn("firstOfAdjacentGridRow(", android)
        self.assertIn("'.season-grid','.tile-button'", android)

    def test_library_up_down_animates_rows_on_google_tv(self):
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" /
                   "java" / "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        # Behaviour is covered in a real browser by
        # test_google_tv_library_scroll_browser; this pins the structure.
        self.assertIn("const moveLibraryGridRow=(active,direction)=>", android)
        self.assertIn("if(moveLibraryGridRow(active,direction))return true", android)
        self.assertIn("!isLibraryGrid()", android)
        self.assertIn("active?.matches?.('#items .tile-button')", android)
        self.assertIn("target.focus({preventScroll:true})", android)
        self.assertIn("revealLibraryRow(target,next===0)", android)
        # One scroll animator whose clock starts at the first animation frame
        # and whose progress is clamped (negative progress threw the page back).
        self.assertIn("if(begun===null)begun=now;", android)
        self.assertIn("const t=Math.max(0,Math.min(1,(now-begun)/duration));", android)
        self.assertNotIn("const begun=performance.now()", android)
        self.assertNotIn("libraryScrollFrame", android)
        self.assertIn("prefers-reduced-motion: reduce", android)

    def test_library_navigation_does_not_scan_every_poster_per_key_press(self):
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" /
                   "java" / "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        self.assertIn("const libraryLayout=known=>{", android)
        self.assertNotIn("libraryRowTop", android)
        move = android[android.index("const move=direction=>{"):]
        # Library handlers run before the O(posters) candidates() scan.
        self.assertLess(move.index("moveLibraryGridRow(active,direction)"),
                        move.index("const nodes=candidates();"))

    def test_library_browser_keyboard_scrolls_rows_but_not_columns(self):
        page = (SERVER / "catalog.html").read_text()
        self.assertIn("function scrollCatalogRowTo(card){", page)
        self.assertIn("function remoteCatalogMove(key){", page)
        self.assertIn("const betweenPosterRows=['ArrowUp','ArrowDown'].includes(key)", page)
        self.assertIn("if(betweenPosterRows)scrollCatalogRowTo(closest)", page)
        self.assertIn("behavior:reduced?'instant':'smooth'", page)
        self.assertIn("closest.focus({preventScroll:true})", page)
        self.assertIn("!['ArrowLeft','ArrowRight'].includes(key)", page)

    def test_metadata_refresh_keeps_current_library_poster_focus(self):
        page = (SERVER / "catalog.html").read_text()
        self.assertIn("async function load({preserveFocus=false}={},quiet=false)", page)
        self.assertIn("load({preserveFocus:true},true)", page)
        self.assertIn("previouslyFocused.dataset.hoverLibraryId", page)
        self.assertIn("previouslyFocused.dataset.hoverKey", page)
        # The focused poster is rebuilt synchronously however deep it is, then
        # focus and scroll are restored together.
        self.assertIn("Math.max(24,focusIndex>=0?focusIndex+30:0)", page)
        self.assertIn("restored.focus({preventScroll:true})", page)
        self.assertIn(".scrollTop=previousScroll", page)

    def test_system_wide_scale_selection_instead_of_outline(self):
        css = (SERVER / "ui.css").read_text()
        self.assertIn("html body[data-page] :is(a,button,select,[tabindex=\"0\"])", css)
        self.assertIn("transform:scale(1.07)!important", css)
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" / "java" /
                   "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt").read_text()
        self.assertIn("body[data-page] .season-episode-tile.is-selected", android)
        player = (SERVER.parent / "google-tv" / "app" / "src" / "main" / "java" /
                  "studio" / "oneeyedwillie" / "tv" / "PlayerActivity.kt").read_text()
        self.assertIn("button.animate().scaleX(if (hasFocus) 1.16f else 1f)", player)
        self.assertNotIn("if (hasFocus) setStroke(dp(2)", player)

    def test_series_actions_and_clamped_description(self):
        page = (SERVER / "tv_detail.html").read_text()
        self.assertIn("showHero.append(seriesControls(data))", page)
        self.assertIn("seriesDescriptionDialog(title,overview)", page)
        self.assertIn("series-overview", page)
        self.assertIn("Play next episode", page)
        self.assertIn("data.imdb_rating", page)
        self.assertIn("data.content_rating", page)
        self.assertIn("data.network", page)
        self.assertIn("data.genres", page)

    def test_series_shuffles_all_available_seasons_beside_play(self):
        page = (SERVER / "tv_detail.html").read_text()
        play = page.index("button.id='series-play-button'")
        shuffle = page.index("shuffle.id='series-shuffle-button'")
        watch = page.index("actions.append(bulkWatchedControl(data,'show')")
        self.assertLess(play, shuffle)
        self.assertLess(shuffle, watch)
        self.assertIn("shuffle.title='Shuffle play series'", page)
        self.assertIn("WilliePlayer.shuffleSeason(episodes.map(", page)
        self.assertIn("id:episode.id,title:data.title+' · '+episode.title", page)
        player = (SERVER / "player.js").read_text()
        self.assertIn("autoPlayNext=seasonShuffle", player)

    def test_focus_tints_white_icons_blue_without_focus_boxes(self):
        css = (SERVER / "ui.css").read_text()
        self.assertIn("--willie-icon-focus:#a9ddff", css)
        self.assertIn("color:var(--willie-icon-focus)!important", css)
        self.assertIn('data-service-nav="radarr"', css)
        self.assertIn('data-service-nav="sonarr"', css)
        android = (SERVER.parent / "google-tv" / "app" / "src" / "main" /
                   "java" / "studio" / "oneeyedwillie" / "tv")
        browser = (android / "MainActivity.kt").read_text()
        native = (android / "PlayerActivity.kt").read_text()
        # The TV selection color is now one server-owned setting shared by the
        # web UI, the WebView shell and the native player (default crimson).
        self.assertIn("/api/settings/tv-appearance", native)
        self.assertIn('optString("selection_color", "#A61E1E")', native)
        self.assertIn("applyPlayerSelectionColor(color)", native)
        self.assertIn("--oew-tv-select-color", browser)
        self.assertIn("p.selection_color", browser)
        self.assertIn("0xFFF4EFE4.toInt()", native)
        self.assertIn("button.animate().scaleX(if (hasFocus) 1.16f else 1f)", native)

    def test_native_and_browser_shuffle_queue(self):
        player = (SERVER / "player.js").read_text()
        self.assertIn("function shuffleSeason(episodes)", player)
        self.assertIn("shuffleQueue=list.slice(1)", player)
        self.assertIn("shuffleQueue.shift()", player)
        android_root = SERVER.parent / "google-tv" / "app" / "src" / "main" / "java" / "studio" / "oneeyedwillie" / "tv"
        activity = (android_root / "MainActivity.kt").read_text()
        native_player = (android_root / "PlayerActivity.kt").read_text()
        self.assertIn("window.WilliePlayer.shuffleSeason=nativeShuffle", activity)
        self.assertIn("payload.shuffle_queue", activity)
        self.assertIn("seasonShuffle = intent.hasExtra", native_player)
        self.assertIn('following.putExtra("shuffle_queue", remaining.toString())', native_player)

    def test_trailer_controls_are_not_required_when_embedded_trailers_are_removed(self):
        movie = (SERVER / "movie_detail.html").read_text()
        tv = (SERVER / "tv_detail.html").read_text()
        # Preview blocks are optional; the player and external metadata must remain usable.
        self.assertIn("play-movie", movie)
        self.assertIn("function openTvTrailer(", tv)
        self.assertIn("WilliePlayer.open", tv)


    def test_icon_nav_has_all_required_links_and_labels(self):
        js = (SERVER / "shell.js").read_text()
        for path in ("/movies", "/tv", "/settings"):
            self.assertIn(path, js)
        for name in ("fa-house", "fa-film", "fa-tv", "fa-gear"):
            self.assertIn(name, js)
        self.assertIn("aria-label", js)
        self.assertIn("fa-fallback", js)
        catalog = (SERVER / "catalog.html").read_text()
        self.assertIn('id="explore-library"', catalog)
        self.assertIn("/explore?type=", catalog)
        css = (SERVER / "ui.css").read_text()
        self.assertIn("@media(max-width:700px)", css)
        self.assertIn("safe-area-inset-bottom", css)

    def test_explore_remote_controls(self):
        explore = (SERVER / "explore.html").read_text()
        catalog = (SERVER / "catalog.html").read_text()
        self.assertIn("function remoteMove(key)", explore)
        self.assertIn("remoteCandidates(scope)", explore)
        self.assertIn("ArrowUp", explore)
        self.assertIn("ArrowDown", explore)
        self.assertIn("BrowserBack", explore)
        self.assertIn("dialog.addEventListener('close'", explore)
        self.assertIn("active.click()", explore)
        self.assertIn("explore-trailer-preview", explore)
        self.assertIn("function remoteCatalogMove(key)", catalog)
        self.assertIn("focus-visible", catalog)
        self.assertIn("explore-library", catalog)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_ui_javascript_syntax(self):
        source_files = [SERVER / "shell.js", SERVER / "player.js"]
        for path in (SERVER / "dashboard.html", SERVER / "catalog.html", SERVER / "index.html", SERVER / "tv_detail.html", SERVER / "watch.html", SERVER / "movie_detail.html", SERVER / "explore.html"):
            parser = Scripts()
            parser.feed(path.read_text())
            for script in parser.scripts:
                result = subprocess.run(
                    ["node", "--check"], input=script, text=True,
                    capture_output=True, timeout=10
                )
                self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")
        for path in source_files:
            result = subprocess.run(["node", "--check", str(path)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
