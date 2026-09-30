package com.wcm.app

import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val repo = Repository(this)
        setContent { WcmApp(repo) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WcmApp(repo: Repository) {
    var tab by remember { mutableStateOf(0) }
    var server by remember { mutableStateOf("http://10.0.2.2:8000") }
    var search by remember { mutableStateOf("") }
    var region by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("") }
    var eventType by remember { mutableStateOf("") }
    var date by remember { mutableStateOf("2026-09-30") }
    var conflicts by remember { mutableStateOf<List<Conflict>>(emptyList()) }
    var events by remember { mutableStateOf<List<WcmEvent>>(emptyList()) }
    var selectedConflict by remember { mutableStateOf<Conflict?>(null) }
    var selectedEvent by remember { mutableStateOf<WcmEvent?>(null) }
    var geojson by remember { mutableStateOf("""{"type":"FeatureCollection","features":[]}""") }
    val offline by repo.offline.collectAsState()
    val lastUpdated by repo.lastUpdated.collectAsState()
    val scope = rememberCoroutineScope()

    fun reload() {
        scope.launch {
            repo.setBaseUrl(server)
            conflicts = repo.loadConflicts(region, status, search)
            events = repo.loadEvents(null, eventType.ifBlank { null }, search.ifBlank { null })
            geojson = repo.loadGeoJson(null, date.ifBlank { null })
            repo.cacheGeoJson(geojson)
        }
    }

    LaunchedEffect(Unit) { reload() }

    MaterialTheme(colorScheme = darkColorScheme()) {
        Scaffold(
            topBar = {
                TopAppBar(title = { Text("World Conflict Map") }, actions = {
                    if (offline) Text("OFFLINE MODE", modifier = Modifier.padding(8.dp))
                })
            },
            bottomBar = {
                NavigationBar {
                    listOf("Map", "Conflicts", "Events", "Settings").forEachIndexed { i, t ->
                        NavigationBarItem(selected = tab == i, onClick = { tab = i }, label = { Text(t) }, icon = { Text("●") })
                    }
                }
            }
        ) { pad ->
            Column(Modifier.padding(pad).fillMaxSize().padding(8.dp)) {
                OutlinedTextField(value = search, onValueChange = { search = it }, label = { Text("Search country, conflict, event") }, modifier = Modifier.fillMaxWidth())
                if (offline) Text("OFFLINE MODE — showing cached data. Last updated: ${lastUpdated ?: "never"}. Cached data is not current.", color = MaterialTheme.colorScheme.error)
                when (tab) {
                    0 -> {
                        Row { Button(onClick = { reload() }) { Text("Reload") } }
                        MapPane(geojson)
                        Text("FILTERS", style = MaterialTheme.typography.titleSmall)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            FilterChip(region.isBlank(), { region = ""; reload() }, { Text("All regions") })
                            listOf("Europe", "Africa", "Asia").forEach { r ->
                                FilterChip(region == r, { region = r; reload() }, { Text(r) })
                            }
                        }
                        DateRow(date) { date = it; reload() }
                    }
                    1 -> LazyColumn {
                        items(conflicts) { c ->
                            Card(Modifier.fillMaxWidth().padding(4.dp).clickable { selectedConflict = c }) {
                                Column(Modifier.padding(8.dp)) {
                                    Text(c.name, style = MaterialTheme.typography.titleSmall)
                                    Text("${c.status} · ${c.region} · updated ${c.lastUpdated ?: ""}")
                                    if (c.isSample) Text("DEMO / SAMPLE DATA")
                                }
                            }
                        }
                    }
                    2 -> LazyColumn {
                        items(events) { e ->
                            Card(Modifier.fillMaxWidth().padding(4.dp).clickable { selectedEvent = e }) {
                                Column(Modifier.padding(8.dp)) {
                                    Text(e.title, style = MaterialTheme.typography.titleSmall)
                                    Text("${e.type} · ${e.confidence} · ${e.eventTime}")
                                }
                            }
                        }
                    }
                    else -> {
                        OutlinedTextField(value = server, onValueChange = { server = it }, label = { Text("Backend URL") }, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(value = date, onValueChange = { date = it }, label = { Text("Timeline date YYYY-MM-DD") }, modifier = Modifier.fillMaxWidth())
                        Button(onClick = { reload() }) { Text("Apply & reload") }
                        Text("Event type filter:")
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            listOf("", "clash", "ceasefire", "humanitarian").forEach { t ->
                                FilterChip(eventType == t, { eventType = t; reload() }, { Text(if (t.isBlank()) "all" else t) })
                            }
                        }
                        Text("Sources are shown inside conflict / event sheets. Every event requires a source (enforced by API).")
                    }
                }
            }
            if (selectedConflict != null) {
                ModalBottomSheet(onDismissRequest = { selectedConflict = null }) {
                    val c = selectedConflict!!
                    Column(Modifier.padding(16.dp)) {
                        Text(c.name, style = MaterialTheme.typography.titleMedium)
                        Text("Status: ${c.status} · Region: ${c.region}")
                        Text(c.description ?: "")
                        Text("SOURCES", style = MaterialTheme.typography.titleSmall)
                        c.sources.forEach { s -> Text("• ${s.title} (${s.publisher ?: "Open source"})") }
                        if (c.sources.isEmpty()) Text("No linked sources.")
                        Button(onClick = { selectedConflict = null }) { Text("Close") }
                    }
                }
            }
            if (selectedEvent != null) {
                ModalBottomSheet(onDismissRequest = { selectedEvent = null }) {
                    val e = selectedEvent!!
                    Column(Modifier.padding(16.dp)) {
                        Text(e.title, style = MaterialTheme.typography.titleMedium)
                        Text("${e.type} · ${e.confidence} · ${e.eventTime}")
                        Text(e.description ?: "")
                        e.sources.forEach { s -> Text("• ${s.title}") }
                        Button(onClick = { selectedEvent = null }) { Text("Close") }
                    }
                }
            }
        }
    }
}

@Composable
fun DateRow(date: String, onChange: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Button(onClick = { onChange(shift(date, -1)) }) { Text("<") }
        Text(date, modifier = Modifier.padding(8.dp))
        Button(onClick = { onChange(shift(date, 1)) }) { Text(">") }
    }
}

fun shift(d: String, n: Int): String {
    return try {
        val p = java.time.LocalDate.parse(d).plusDays(n.toLong())
        p.toString()
    } catch (e: Exception) { d }
}

@Composable
fun MapPane(geojson: String) {
    val html = remember(geojson) { mapHtml(geojson) }
    AndroidView(factory = { ctx ->
        WebView(ctx).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = WebViewClient()
            loadDataWithBaseURL("https://cdn.example/", html, "text/html", "utf-8", null)
        }
    }, update = { w -> w.loadDataWithBaseURL("https://cdn.example/", html, "text/html", "utf-8", null) },
        modifier = Modifier.fillMaxWidth().height(320.dp))
}

fun mapHtml(geojson: String): String {
    val safe = geojson.replace("</", "<\\/")
    return """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'/>
<link href='https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css' rel='stylesheet'/>
<script src='https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js'></script>
<style>html,body,#m{height:100%;margin:0;background:#0b0e13}</style></head><body><div id='m'></div>
<script>var GJ=$safe;
var map=new maplibregl.Map({container:'m',style:'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',center:[20,30],zoom:1.5});
map.addControl(new maplibregl.NavigationControl(),'top-right');
map.on('load',function(){
 map.addSource('w',{type:'geojson',data:GJ});
 map.addLayer({id:'p',type:'circle',source:'w',paint:{'circle-color':'#ffb300','circle-radius':5}});
 map.addLayer({id:'f',type:'fill',source:'w',paint:{'fill-color':'#ff5252','fill-opacity':0.25}});
 map.addLayer({id:'l',type:'line',source:'w',paint:{'line-color':'#ff5252','line-width':2}});
});</script></body></html>"""
}
