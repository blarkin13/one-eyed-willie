package studio.oneeyedwillie.tv

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.launch

private val navy = Color(0xFF000000)
private val rail = Color(0xFF080808)
private val surface = Color(0xFF151515)
private val ink = Color(0xFFF4F0E8)
private val muted = Color(0xFFB0AFA9)
private val accent = Color(0xFFE8E3D9)

class MainActivity : ComponentActivity() {
    private val settings by lazy { getSharedPreferences("server", MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val scope = rememberCoroutineScope()
            var address by remember { mutableStateOf(settings.getString("url", "") ?: "") }
            var connected by remember { mutableStateOf(false) }
            var section by remember { mutableStateOf("Home") }
            var home by remember { mutableStateOf<List<Pair<String, List<MediaEntry>>>>(emptyList()) }
            var entries by remember { mutableStateOf<List<MediaEntry>>(emptyList()) }
            var selected by remember { mutableStateOf<MediaEntry?>(null) }
            var episodes by remember { mutableStateOf<List<EpisodeEntry>>(emptyList()) }
            var detail by remember { mutableStateOf<MediaDetails?>(null) }
            var status by remember { mutableStateOf("") }
            var busy by remember { mutableStateOf(false) }

            fun play(id: Int) {
                startActivity(Intent(this@MainActivity, PlayerActivity::class.java)
                    .putExtra("url", ServerApi(address).streamUrl(id))
                    .putExtra("media_id", id).putExtra("server", address))
            }
            fun navigate(target: String) {
                section = target
                selected = null
                detail = null
                scope.launch {
                    busy = true
                    status = ""
                    try {
                        if (target == "Home") home = ServerApi(address).home()
                        else if (target == "Movies" || target == "TV Shows")
                            entries = ServerApi(address).catalog(if(target == "Movies") "movies" else "tv")
                    } catch (e: Exception) { status = e.message ?: "Library unavailable" }
                    finally { busy = false }
                }
            }
            fun open(item: MediaEntry) {
                selected = item
                detail = null
                episodes = emptyList()
                scope.launch {
                    busy = true
                    status = ""
                    try {
                        val api = ServerApi(address)
                        detail = api.details(item)
                        if (item.kind == "tv") episodes = api.episodes(item)
                    } catch (e: Exception) { status = e.message ?: "Details unavailable" }
                    finally { busy = false }
                }
            }
            BackHandler(selected != null) { selected = null; detail = null }
            LaunchedEffect(Unit) {
                if (address.isNotBlank()) try {
                    if (ServerApi(address).ping()) {
                        connected = true
                        navigate("Home")
                    }
                } catch (_: Exception) { status = "Unable to reach saved server" }
            }

            Row(Modifier.fillMaxSize().background(navy)) {
                Column(
                    Modifier.width(210.dp).fillMaxHeight().background(rail)
                        .border(width = 1.dp, color = Color(0xFF292827))
                        .padding(start = 18.dp, end = 18.dp, top = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Image(
                        painter = painterResource(id = R.drawable.willie_logo),
                        contentDescription = "One-Eyed Willie pirate ship",
                        modifier = Modifier.fillMaxWidth().height(156.dp),
                        contentScale = ContentScale.Fit
                    )
                    Spacer(Modifier.height(12.dp))
                    listOf(
                        Triple("Home", "⌂", "Home"),
                        Triple("Movies", "▣", "Movies"),
                        Triple("TV Shows", "▤", "TV Shows"),
                        Triple("Settings", "⚙", "Settings")
                    ).forEach { (label, glyph, target) ->
                        NavigationItem(glyph, label, section == target && selected == null) {
                            navigate(target)
                        }
                    }
                }
                Column(
                    Modifier.fillMaxSize().padding(horizontal = 42.dp, vertical = 28.dp)
                ) {
                    if (!connected || section == "Settings") {
                        Text("SETTINGS  /  SERVER", color = ink, fontSize = 25.sp, fontWeight = FontWeight.Medium, letterSpacing = 2.sp)
                        Spacer(Modifier.height(14.dp))
                        Text("Connect to the One-Eyed Willie server on your local network.", color = muted)
                        Spacer(Modifier.height(18.dp))
                        OutlinedTextField(
                            value = address, onValueChange = { address = it }, singleLine = true,
                            label = { Text("Server address") },
                            placeholder = { Text("http://192.168.86.100:8787") },
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                            modifier = Modifier.width(560.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = ink, unfocusedTextColor = ink,
                                focusedBorderColor = accent, unfocusedBorderColor = muted,
                                focusedLabelColor = accent, unfocusedLabelColor = muted
                            )
                        )
                        Spacer(Modifier.height(18.dp))
                        Button(onClick = {
                            scope.launch {
                                busy = true
                                status = ""
                                try {
                                    if (ServerApi(address).ping()) {
                                        settings.edit().putString("url", address.trimEnd('/')).apply()
                                        connected = true
                                        navigate("Home")
                                    } else status = "Not a One-Eyed Willie server"
                                } catch (e: Exception) { status = e.message ?: "Connection failed" }
                                finally { busy = false }
                            }
                        }) { Text("Connect") }
                    } else if (selected != null) {
                        val item = selected!!
                        Text(item.title, fontSize = 35.sp, color = ink, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(8.dp))
                        Text(listOfNotNull(item.year?.toString(), detail?.genres?.takeIf { it.isNotBlank() })
                            .joinToString("  ·  "), color = muted, fontSize = 16.sp)
                        Spacer(Modifier.height(18.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(25.dp)) {
                            AsyncImage(
                                model = detail?.artwork,
                                contentDescription = item.title + " poster",
                                modifier = Modifier.width(165.dp).height(245.dp).clip(RoundedCornerShape(12.dp))
                                    .background(surface), contentScale = ContentScale.Crop)
                            Column(Modifier.weight(1f)) {
                                Text(detail?.description.orEmpty(), color = ink, fontSize = 18.sp, lineHeight = 26.sp,
                                    maxLines = 6, overflow = TextOverflow.Ellipsis)
                                Spacer(Modifier.height(22.dp))
                                if(item.kind == "movies") {
                                    FocusPill("▶  Play movie") {
                                        scope.launch {
                                            try { play(ServerApi(address).movieMediaId(item)) }
                                            catch (e: Exception) { status = e.message ?: "Unable to play" }
                                        }
                                    }
                                } else Text("Episodes", color = ink, fontSize = 22.sp)
                            }
                        }
                        Spacer(Modifier.height(18.dp))
                        if(item.kind == "tv") {
                            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                items(episodes, key = { it.id }) { episode ->
                                    FocusPill("▶   " + episode.title) { play(episode.id) }
                                }
                            }
                        }
                    } else if (section == "Home") {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(28.dp)) {
                            item {
                                Row(
                                    Modifier.fillMaxWidth().padding(bottom = 6.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(20.dp)
                                ) {
                                    Image(
                                        painter = painterResource(id = R.drawable.willie_logo),
                                        contentDescription = null,
                                        modifier = Modifier.height(108.dp).width(108.dp),
                                        contentScale = ContentScale.Fit
                                    )
                                    Column {
                                        Text("ONE-EYED WILLIE", fontSize = 30.sp,
                                            fontWeight = FontWeight.Light, letterSpacing = 3.sp, color = ink)
                                        Text("YOUR COLLECTION  ·  YOUR SHIP", color = muted,
                                            fontSize = 13.sp, letterSpacing = 2.sp)
                                    }
                                }
                            }
                            items(home) { (heading, titles) ->
                                Column {
                                    Text(heading.uppercase(), fontSize = 21.sp, fontWeight = FontWeight.Medium, color = ink, letterSpacing = 1.6.sp)
                                    Spacer(Modifier.height(16.dp))
                                    if (titles.isEmpty()) {
                                        Text("Nothing here yet", color = muted)
                                    } else {
                                        LazyRow(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                            items(titles, key = { it.kind + ":" + it.libraryId + ":" + it.key }) { item ->
                                                PosterCard(address, item) { open(item) }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    } else {
                        Text(section.uppercase(), fontSize = 28.sp, fontWeight = FontWeight.Medium, color = ink, letterSpacing = 2.sp)
                        Spacer(Modifier.height(20.dp))
                        LazyVerticalGrid(
                            columns = GridCells.Adaptive(minSize = 155.dp),
                            horizontalArrangement = Arrangement.spacedBy(18.dp),
                            verticalArrangement = Arrangement.spacedBy(25.dp)
                        ) {
                            gridItems(entries, key = { it.kind + ":" + it.libraryId + ":" + it.key }) { item ->
                                PosterCard(address, item) { open(item) }
                            }
                        }
                    }
                    if (busy) LinearProgressIndicator(Modifier.width(200.dp), color = accent)
                    if (status.isNotBlank()) Text(status, color = Color(0xFFFFAAAA), fontSize = 16.sp)
                }
            }
        }
    }
}

@Composable
private fun NavigationItem(symbol: String, name: String, active: Boolean, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }
            .clip(RoundedCornerShape(10.dp))
            .background(if (focused || active) Color(0xFF292722) else Color.Transparent)\n            .border(if (focused) 1.dp else 0.dp, if (focused) accent else Color.Transparent, RoundedCornerShape(10.dp))
            .clickable(onClick = onClick).padding(horizontal = 12.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(symbol, color = ink, fontSize = 23.sp)
        Spacer(Modifier.width(13.dp))
        Text(name, color = if (focused || active) ink else muted, fontSize = 16.sp,
            fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun FocusPill(label: String, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Box(
        Modifier.onFocusChanged { focused = it.isFocused }
            .clip(RoundedCornerShape(9.dp))
            .background(if (focused) accent else surface)
            .clickable(onClick = onClick).padding(horizontal = 20.dp, vertical = 13.dp)
    ) {
        Text(label, color = if(focused) navy else ink, fontSize = 18.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun PosterCard(server: String, item: MediaEntry, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    var artwork by remember(item.key, item.kind, item.libraryId, server) { mutableStateOf<String?>(item.posterUrl) }
    LaunchedEffect(item.key, item.kind, item.libraryId, server) {
        try { artwork = ServerApi(server).details(item).artwork } catch (_: Exception) { }
    }
    Column(Modifier.width(157.dp).onFocusChanged { focused = it.isFocused }
        .scale(if (focused) 1.055f else 1f)
        .clickable(onClick = onClick)) {
        Box(
            Modifier.fillMaxWidth().height(224.dp)
                .clip(RoundedCornerShape(11.dp))
                .background(surface)
                .border(if (focused) 3.dp else 1.dp,
                    if(focused) accent else Color(0xFF32302C), RoundedCornerShape(11.dp))
        ) {
            if(artwork != null) {
                AsyncImage(model = artwork, contentDescription = item.title + " poster",
                    contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            } else {
                Text(item.title.take(1).uppercase(), color = Color(0xFFACA79D),
                    fontSize = 64.sp, modifier = Modifier.align(Alignment.Center))
            }
            if(item.progress > 0) {
                Box(Modifier.align(Alignment.BottomStart).fillMaxWidth()
                    .height(5.dp).background(Color(0xFF35312B))) {
                    Box(Modifier.fillMaxWidth((item.progress / 100f).coerceIn(0f, 1f))
                        .fillMaxHeight().background(accent))
                }
            }
        }
        Spacer(Modifier.height(9.dp))
        Text(item.title, color = ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
            maxLines = 2, overflow = TextOverflow.Ellipsis)
        if(item.year != null) Text(item.year.toString(), fontSize = 13.sp, color = muted)
    }
}
