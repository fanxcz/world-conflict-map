package com.wcm.app

import android.content.Context
import androidx.room.*
import com.google.gson.Gson
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

@Entity(tableName = "cached_conflicts")
data class CachedConflict(
    @PrimaryKey val id: Int,
    val name: String,
    val region: String,
    val status: String,
    val json: String
)

@Entity(tableName = "cached_events")
data class CachedEvent(
    @PrimaryKey val id: Int,
    val conflictId: Int?,
    val title: String,
    val type: String,
    val json: String
)

@Entity(tableName = "meta")
data class Meta(@PrimaryKey val key: String, val value: String)

@Dao
interface WcmDao {
    @Query("SELECT * FROM cached_conflicts ORDER BY id")
    suspend fun conflicts(): List<CachedConflict>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveConflicts(items: List<CachedConflict>)

    @Query("SELECT * FROM cached_events ORDER BY id DESC LIMIT 300")
    suspend fun events(): List<CachedEvent>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveEvents(items: List<CachedEvent>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun setMeta(m: Meta)

    @Query("SELECT value FROM meta WHERE `key` = :k LIMIT 1")
    suspend fun meta(k: String): String?
}

@Database(entities = [CachedConflict::class, CachedEvent::class, Meta::class], version = 1)
abstract class WcmDb : RoomDatabase() {
    abstract fun dao(): WcmDao
}

class Repository(ctx: Context) {
    private val gson = Gson()
    val db: WcmDb = Room.databaseBuilder(ctx.applicationContext, WcmDb::class.java, "wcm.db").build()

    var baseUrl: String = "http://10.0.2.2:8000/"
        private set

    private fun client(): WcmApi {
        val log = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
        val http = OkHttpClient.Builder().addInterceptor(log).build()
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(http)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(WcmApi::class.java)
    }

    fun setBaseUrl(url: String) {
        baseUrl = if (url.endsWith("/")) url else "$url/"
    }

    private val _offline = MutableStateFlow(false)
    val offline: StateFlow<Boolean> = _offline
    private val _lastUpdated = MutableStateFlow<String?>(null)
    val lastUpdated: StateFlow<String?> = _lastUpdated

    suspend fun loadConflicts(region: String? = null, status: String? = null, search: String? = null): List<Conflict> {
        return try {
            @Suppress("UNCHECKED_CAST")
            val raw = client().conflicts(region = region?.ifBlank { null }, status = status?.ifBlank { null }, search = search?.ifBlank { null })
            val items = (raw["items"] as? List<Map<String, Any?>>).orEmpty()
            val out = items.map { gson.fromJson(gson.toJson(it), Conflict::class.java) }
            db.dao().saveConflicts(out.map { CachedConflict(it.id, it.name, it.region, it.status, gson.toJson(it)) })
            val now = java.time.Instant.now().toString()
            db.dao().setMeta(Meta("last_updated", now))
            _lastUpdated.value = now
            _offline.value = false
            out
        } catch (e: Exception) {
            _offline.value = true
            _lastUpdated.value = db.dao().meta("last_updated")
            db.dao().conflicts().map { gson.fromJson(it.json, Conflict::class.java) }
                .filter {
                    (region.isNullOrBlank() || it.region == region) &&
                        (status.isNullOrBlank() || it.status == status) &&
                        (search.isNullOrBlank() || it.name.contains(search, true))
                }
        }
    }

    suspend fun loadEvents(conflictId: Int? = null, type: String? = null, query: String? = null): List<WcmEvent> {
        return try {
            @Suppress("UNCHECKED_CAST")
            val raw = client().events(conflictId = conflictId, eventType = type?.ifBlank { null }, search = query?.ifBlank { null })
            val items = (raw["items"] as? List<Map<String, Any?>>).orEmpty()
            val out = items.map { gson.fromJson(gson.toJson(it), WcmEvent::class.java) }
            db.dao().saveEvents(out.map { CachedEvent(it.id, it.conflictId, it.title, it.type, gson.toJson(it)) })
            _offline.value = false
            out
        } catch (e: Exception) {
            _offline.value = true
            db.dao().events().map { gson.fromJson(it.json, WcmEvent::class.java) }
                .filter {
                    (conflictId == null || it.conflictId == conflictId) &&
                        (type.isNullOrBlank() || it.type == type) &&
                        (query.isNullOrBlank() || it.title.contains(query, true))
                }
        }
    }

    suspend fun loadGeoJson(conflictId: Int? = null, date: String? = null): String {
        return try {
            val raw = client().geojson(conflictId = conflictId, date = date?.ifBlank { null })
            _offline.value = false
            gson.toJson(raw)
        } catch (e: Exception) {
            _offline.value = true
            db.dao().meta("last_geojson") ?: """{"type":"FeatureCollection","features":[]}"""
        }
    }

    suspend fun cacheGeoJson(json: String) {
        db.dao().setMeta(Meta("last_geojson", json))
    }
}

/** Push-notification architecture (no auto-send for SAMPLE data).
 * Categories: new_conflict_update, important_event, status_changed.
 * Wire to FCM by implementing PushHandler with firebase-messaging in future;
 * for now notifications are stored locally and rendered in-app.
 */
data class WcmNotification(val category: String, val title: String, val body: String, val at: String)

object NotificationStore {
    private val _items = MutableStateFlow<List<WcmNotification>>(emptyList())
    val items: StateFlow<List<WcmNotification>> = _items
    val allowed = setOf("new_conflict_update", "important_event", "status_changed")

    fun push(n: WcmNotification, isSample: Boolean) {
        if (isSample) return // never auto-notify for demo data
        if (n.category !in allowed) return
        _items.value = listOf(n) + _items.value.take(49)
    }
}
