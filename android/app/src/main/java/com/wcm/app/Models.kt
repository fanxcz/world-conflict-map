package com.wcm.app

import com.google.gson.annotations.SerializedName

data class Paged<T>(val items: List<T> = emptyList(), val total: Int = 0)

data class ApiSource(
    val id: Int = 0,
    val title: String = "",
    val publisher: String? = null,
    val url: String? = null,
    @SerializedName("published_at") val publishedAt: String? = null,
    @SerializedName("reliability_note") val reliabilityNote: String? = null
)

data class Conflict(
    val id: Int = 0,
    val name: String = "",
    val slug: String = "",
    val region: String = "",
    val description: String? = null,
    val status: String = "active",
    @SerializedName("start_date") val startDate: String? = null,
    @SerializedName("last_updated") val lastUpdated: String? = null,
    @SerializedName("is_sample") val isSample: Boolean = false,
    val sources: List<ApiSource> = emptyList()
)

data class WcmEvent(
    val id: Int = 0,
    @SerializedName("conflict_id") val conflictId: Int? = null,
    val type: String = "",
    val title: String = "",
    val description: String? = null,
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
    @SerializedName("event_time") val eventTime: String = "",
    val confidence: String = "REPORTED",
    @SerializedName("is_sample") val isSample: Boolean = false,
    val sources: List<ApiSource> = emptyList()
)

data class GeoJson(val type: String = "FeatureCollection", val features: List<Map<String, Any?>> = emptyList())
