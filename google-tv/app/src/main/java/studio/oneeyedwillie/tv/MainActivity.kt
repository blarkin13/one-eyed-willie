package studio.oneeyedwillie.tv

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private val bg = Color(0xFF101114)
private val fg = Color(0xFFF3F0E9)

class MainActivity : ComponentActivity() {
    private val settings by lazy { getSharedPreferences("server", MODE_PRIVATE) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val scope = rememberCoroutineScope()
            var address by remember { mutableStateOf(settings.getString("url", "") ?: "") }
            var connected by remember { mutableStateOf(false) }
            var tab by remember { mutableStateOf("Home") }
            var entries by remember { mutableStateOf<List<MediaEntry>>(emptyList()) }
            var episodes by remember { mutableStateOf<List<EpisodeEntry>?>(null) }
            var message by remember { mutableStateOf("") }
            var busy by remember { mutableStateOf(false) }

            fun browse(selected: String) {
                tab = selected
                episodes = null
                scope.launch {
                    busy = true
                    message = ""
                    try {
                        entries = if (selected == "Movies") ServerApi(address).catalog("movies")
                            else if (selected == "TV Shows") ServerApi(address).catalog("tv")
                            else ServerApi(address).catalog("movies") + ServerApi(address).catalog("tv")
                    } catch (e: Exception) { message = e.message ?: "Unable to load catalog" }
                    finally { busy = false }
                }
            }
            fun play(mediaId: Int) {
                startActivity(Intent(this@MainActivity, PlayerActivity::class.java)
                    .putExtra("url", ServerApi(address).streamUrl(mediaId))
                    .putExtra("media_id", mediaId)
                    .putExtra("server", address))
            }
            LaunchedEffect(Unit) {
                if (address.isNotBlank()) {
                    try {
                        if (ServerApi(address).ping()) {
                            connected = true
                            browse("Home")
                        }
                    } catch (_: Exception) { message = "Cannot reach saved server" }
                }
            }
            Column(Modifier.fillMaxSize().background(bg).padding(42.dp)) {
                Text("ONE-EYED WILLIE", color = fg, fontSize = 30.sp)
                Spacer(Modifier.height(22.dp))
                if (!connected || tab == "Settings") {
                    Text("Server connection", color = fg, fontSize = 22.sp)
                    Spacer(Modifier.height(14.dp))
                    OutlinedTextField(
                        value = address, onValueChange = { address = it }, singleLine = true,
                        label = { Text("Server URL (for example http://192.168.1.20:8787)") },
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        modifier = Modifier.width(620.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = fg, unfocusedTextColor = fg,
                            focusedBorderColor = fg, unfocusedBorderColor = Color.Gray))
                    Spacer(Modifier.height(14.dp))
                    Button(onClick = {
                        scope.launch {
                            busy = true
                            try {
                                if (ServerApi(address).ping()) {
                                    settings.edit().putString("url", address.trimEnd('/')).apply()
                                    connected = true
                                    browse("Home")
                                } else message = "This is not a One-Eyed Willie server"
                            } catch (e: Exception) { message = e.message ?: "Connection failed" }
                            finally { busy = false }
                        }
                    }) { Text("Connect") }
                    if (connected) {
                        Spacer(Modifier.height(10.dp))
                        Button(onClick = { browse("Home") }) { Text("Back to Home") }
                    }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        listOf("Home", "Movies", "TV Shows", "Settings").forEach { name ->
                            Button(onClick = { browse(name) }) { Text(name) }
                        }
                    }
                    Spacer(Modifier.height(24.dp))
                    if (episodes != null) {
                        Button(onClick = { episodes = null }) { Text("Back") }
                        Spacer(Modifier.height(12.dp))
                        LazyVerticalGrid(GridCells.Fixed(3), horizontalArrangement = Arrangement.spacedBy(14.dp),
                            verticalArrangement = Arrangement.spacedBy(14.dp)) {
                            items(episodes!!) { episode ->
                                MediaTile(episode.title) { play(episode.id) }
                            }
                        }
                    } else {
                        Text(if (tab == "Home") "Your library" else tab, color = fg, fontSize = 25.sp)
                        Spacer(Modifier.height(15.dp))
                        LazyVerticalGrid(GridCells.Fixed(5), horizontalArrangement = Arrangement.spacedBy(16.dp),
                            verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            items(entries) { item ->
                                MediaTile(item.title + (item.year?.let { " ($it)" } ?: "")) {
                                    scope.launch {
                                        busy = true
                                        try {
                                            if (item.kind == "movies") play(ServerApi(address).movieMediaId(item))
                                            else episodes = ServerApi(address).episodes(item)
                                        } catch (e: Exception) { message = e.message ?: "Unable to open item" }
                                        finally { busy = false }
                                    }
                                }
                            }
                        }
                    }
                }
                if (busy) LinearProgressIndicator(Modifier.width(250.dp))
                if (message.isNotBlank()) Text(message, color = Color(0xFFFFA0A0))
            }
        }
    }
}

@Composable
private fun MediaTile(title: String, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.width(200.dp).height(150.dp).clickable(onClick = onClick).focusable(),
        shape = RoundedCornerShape(12.dp),
        color = Color(0xFF25262C),
        border = BorderStroke(1.dp, Color(0xFF454650))
    ) {
        Box(Modifier.padding(16.dp)) {
            Text(title, fontSize = 20.sp, color = fg)
        }
    }
}
