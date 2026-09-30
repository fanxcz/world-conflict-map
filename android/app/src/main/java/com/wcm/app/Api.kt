package com.wcm.app

import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

interface WcmApi {
    @GET("api/conflicts")
    suspend fun conflicts(
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 100,
        @Query("region") region: String? = null,
        @Query("status") status: String? = null,
        @Query("search") search: String? = null
    ): Map<String, Any>

    @GET("api/conflicts/{id}")
    suspend fun conflict(@Path("id") id: Int): Conflict

    @GET("api/events")
    suspend fun events(
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 100,
        @Query("conflict_id") conflictId: Int? = null,
        @Query("event_type") eventType: String? = null,
        @Query("confidence") confidence: String? = null,
        @Query("search") search: String? = null,
        @Query("bbox") bbox: String? = null
    ): Map<String, Any>

    @GET("api/map/geojson")
    suspend fun geojson(
        @Query("conflict_id") conflictId: Int? = null,
        @Query("date") date: String? = null
    ): Map<String, Any>

    @GET("api/regions")
    suspend fun regions(): List<Map<String, Any>>

    @GET("api/health")
    suspend fun health(): Map<String, Any>
}
