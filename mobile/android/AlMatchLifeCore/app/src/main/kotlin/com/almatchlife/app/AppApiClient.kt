package com.almatchlife.app

import com.almatchlife.core.ApiResponse
import com.almatchlife.core.AuthenticatedApiClient
import com.almatchlife.core.NativeCallType
import com.almatchlife.core.PushEventType
import com.almatchlife.core.SessionTokenStore
import com.almatchlife.core.VoipCallPayload
import com.almatchlife.core.VoipPayloadValidator
import org.json.JSONObject
import java.util.concurrent.CompletableFuture

internal data class AppProfile(
    val name: String,
    val email: String,
    val country: String,
    val bio: String,
    val profession: String,
    val lookingFor: String,
    val goals: List<String>,
    val interests: List<String>,
    val skills: List<String>,
    val languages: List<String>,
    val trustScore: Int,
    val needsOnboarding: Boolean,
    val followersCount: Int = 0,
    val followingCount: Int = 0,
)

internal data class SocialRelationship(
    val isSelf: Boolean,
    val isFollowing: Boolean,
    val followsYou: Boolean,
    val isMutual: Boolean,
    val followersCount: Int,
    val followingCount: Int,
)

internal data class SocialListItem(val profile: AppProfile, val relationship: SocialRelationship)

internal data class SocialListPage(
    val kind: String,
    val profile: AppProfile,
    val items: List<SocialListItem>,
    val nextCursor: String,
)

internal data class ProfileUpdate(
    val bio: String,
    val profession: String,
    val lookingFor: String,
    val goals: String,
    val interests: String,
    val skills: String,
    val languages: String,
)

internal data class OnboardingAnswers(
    val lookingFor: String,
    val profession: String,
    val goals: String,
    val interests: String,
    val skills: String,
    val languages: String,
)

internal data class AiMatch(
    val profile: AppProfile,
    val score: Int,
    val level: String,
    val reasons: List<String>,
)

internal data class FeedPost(
    val id: String,
    val authorName: String,
    val authorEmail: String,
    val type: String,
    val text: String,
    val location: String,
    val hashtags: List<String>,
    val language: String,
    val date: String,
    val likesCount: Int,
    val commentsCount: Int,
    val savesCount: Int,
    val liked: Boolean,
    val saved: Boolean,
    val hasMedia: Boolean,
    val imageUrls: List<String>,
)

internal data class FeedPage(val posts: List<FeedPost>, val nextCursor: String)
internal data class FeedEngagement(val active: Boolean, val likesCount: Int, val commentsCount: Int, val savesCount: Int)
internal data class FeedCounts(val likesCount: Int, val commentsCount: Int, val savesCount: Int)

internal data class ChatMessage(
    val id: String,
    val senderEmail: String,
    val receiverEmail: String,
    val text: String,
    val time: String,
    val mine: Boolean,
    val sourceLanguage: String,
    val translatedText: String,
    val translationLanguage: String,
    val hasMedia: Boolean,
)

internal data class ChatSummary(
    val user: AppProfile,
    val lastMessage: ChatMessage,
)

internal data class ChatThread(
    val user: AppProfile,
    val messages: List<ChatMessage>,
    val autoTranslationEnabled: Boolean,
    val translationLanguage: String,
    val translationProviderAvailable: Boolean,
)

internal data class CallRoom(val callId: String, val otherEmail: String, val callType: String)

internal class AppApiClient(
    private val client: AuthenticatedApiClient,
    private val tokenStore: SessionTokenStore,
) {
    fun profile(): CompletableFuture<AppProfile> = client.request("/api/me").thenApply { response ->
        requireSuccess(response)
        decodeProfile(response.body)
    }

    fun socialList(profileEmail: String, kind: String, cursor: String = ""): CompletableFuture<SocialListPage> {
        require(kind in setOf("followers", "following"))
        require(cursor.isEmpty() || cursor.length <= 512 && cursor.matches(Regex("^[A-Za-z0-9_-]+$")))
        val query = if (cursor.isEmpty()) "?limit=$SOCIAL_PAGE_SIZE" else "?limit=$SOCIAL_PAGE_SIZE&cursor=$cursor"
        return client.request("/api/users/${pathSegment(profileEmail)}/$kind$query").thenApply { response ->
            requireSuccess(response)
            val root = parse(response.body)
            if (!root.optBoolean("ok") || root.bounded("kind", 16) != kind) throw AuthException("Invalid social list response")
            val owner = decodeUser(root.optJSONObject("profile") ?: throw AuthException("Invalid social list response"), false)
            if (!owner.email.equals(profileEmail, ignoreCase = true)) throw AuthException("Invalid social list response")
            val array = root.optJSONArray("items") ?: throw AuthException("Invalid social list response")
            if (array.length() > SOCIAL_PAGE_SIZE) throw AuthException("Invalid social list response")
            val items = buildList {
                val emails = mutableSetOf<String>()
                for (index in 0 until array.length()) {
                    val item = array.optJSONObject(index) ?: throw AuthException("Invalid social list response")
                    val itemProfile = decodeUser(item.optJSONObject("user") ?: throw AuthException("Invalid social list response"), false)
                    if (!emails.add(itemProfile.email.lowercase())) throw AuthException("Invalid social list response")
                    add(SocialListItem(itemProfile, decodeRelationship(item.optJSONObject("relationship"))))
                }
            }
            val nextCursor = if (root.isNull("next_cursor")) "" else root.bounded("next_cursor", 512, required = false)
            if (nextCursor.isNotEmpty() && (nextCursor.length > 512 || !nextCursor.matches(Regex("^[A-Za-z0-9_-]+$")))) {
                throw AuthException("Invalid social list response")
            }
            SocialListPage(kind, owner, items, nextCursor)
        }
    }

    fun setFollowing(profileEmail: String, following: Boolean): CompletableFuture<SocialRelationship> =
        client.request(
            path = "/api/users/${pathSegment(profileEmail)}/follow",
            method = if (following) "POST" else "DELETE",
            headers = mapOf("Accept" to "application/json"),
        ).thenApply { response ->
            requireSuccess(response)
            val root = parse(response.body)
            if (!root.optBoolean("ok")) throw AuthException("Invalid social relationship response")
            decodeRelationship(root)
        }

    fun matches(): CompletableFuture<List<AiMatch>> = client.request("/api/matches").thenApply { response ->
        requireSuccess(response)
        val root = parse(response.body)
        if (!root.optBoolean("ok")) throw AuthException("Invalid matches response")
        val array = root.optJSONArray("matches") ?: throw AuthException("Invalid matches response")
        if (array.length() > MAX_MATCHES) throw AuthException("Invalid matches response")
        buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: throw AuthException("Invalid matches response")
                val score = item.optInt("score", -1)
                if (score !in 0..MAX_MATCH_SCORE) throw AuthException("Invalid matches response")
                val level = item.bounded("level", 64)
                val reasonsArray = item.optJSONArray("reasons") ?: throw AuthException("Invalid matches response")
                if (reasonsArray.length() > MAX_MATCH_REASONS) throw AuthException("Invalid matches response")
                val reasons = buildList {
                    for (reasonIndex in 0 until reasonsArray.length()) {
                        val reason = reasonsArray.optString(reasonIndex).trim()
                        if (reason.isEmpty() || reason.length > 300) throw AuthException("Invalid matches response")
                        add(reason)
                    }
                }
                add(AiMatch(
                    decodeUser(item.optJSONObject("user") ?: throw AuthException("Invalid matches response"), false),
                    score,
                    level,
                    reasons,
                ))
            }
        }
    }

    fun feed(cursor: String = ""): CompletableFuture<FeedPage> {
        require(cursor.isEmpty() || cursor.length <= 512 && cursor.matches(Regex("^[A-Za-z0-9_-]+$")))
        val query = if (cursor.isEmpty()) "?limit=$FEED_PAGE_SIZE" else "?limit=$FEED_PAGE_SIZE&cursor=$cursor"
        return client.request("/api/feed$query").thenApply { response ->
        requireSuccess(response)
        val root = parse(response.body)
        if (!root.optBoolean("ok")) throw AuthException("Invalid feed response")
        val posts = root.optJSONArray("posts") ?: throw AuthException("Invalid feed response")
        if (posts.length() > FEED_PAGE_SIZE) throw AuthException("Invalid feed response")
        val decoded = buildList {
            for (index in 0 until posts.length()) {
                val item = posts.optJSONObject(index) ?: throw AuthException("Invalid feed response")
                val author = item.optJSONObject("author") ?: throw AuthException("Invalid feed response")
                val id = item.optString("id").trim()
                if (id.isEmpty() || id.length > 80) throw AuthException("Invalid feed response")
                val text = item.bounded("text", 5_000, required = false)
                val mediaType = item.bounded("media_type", 32, required = false)
                val mediaUrl = item.bounded("media_url", 2_048, required = false)
                val mediaItems = item.optJSONArray("media_items")
                if (mediaItems != null && mediaItems.length() > 10) throw AuthException("Invalid feed response")
                val imageUrls = mutableListOf<String>()
                if (mediaType == "image" && mediaUrl.isNotEmpty()) imageUrls += mediaUrl
                val hasMediaItems = mediaItems?.let { array ->
                    for (mediaIndex in 0 until array.length()) {
                        val media = array.optJSONObject(mediaIndex) ?: throw AuthException("Invalid feed response")
                        val candidateUrl = media.optString("url").trim()
                        val candidateType = media.optString("type").trim()
                        if (candidateUrl.length > 2_048 || candidateType.length > 32) {
                            throw AuthException("Invalid feed response")
                        }
                        if (candidateType == "image" && candidateUrl.isNotEmpty() && imageUrls.size < 4) {
                            imageUrls += candidateUrl
                        }
                    }
                    array.length() > 0
                } ?: false
                val hasMedia = mediaType in setOf("image", "video") && mediaUrl.isNotEmpty() || hasMediaItems
                if (text.isEmpty() && !hasMedia) throw AuthException("Invalid feed response")
                add(FeedPost(
                    id = id,
                    authorName = author.bounded("name", 100),
                    authorEmail = author.bounded("email", 254),
                    type = item.bounded("type", 80, required = false),
                    text = text,
                    location = item.bounded("location", 160, required = false),
                    hashtags = item.boundedList("hashtags", 10, 80),
                    language = item.bounded("language", 16, required = false),
                    date = item.bounded("date", 80, required = false),
                    likesCount = item.boundedCount("likes_count"),
                    commentsCount = item.boundedCount("comments_count"),
                    savesCount = item.boundedCount("saves_count"),
                    liked = item.requiredBoolean("liked"),
                    saved = item.requiredBoolean("saved"),
                    hasMedia = hasMedia,
                    imageUrls = imageUrls.distinct(),
                ))
            }
        }
        val nextCursor = if (root.isNull("next_cursor")) "" else root.bounded("next_cursor", 512, required = false)
        if (nextCursor.isNotEmpty() && !nextCursor.matches(Regex("^[A-Za-z0-9_-]+$"))) {
            throw AuthException("Invalid feed response")
        }
        FeedPage(decoded, nextCursor)
        }
    }

    fun toggleFeedInteraction(postId: String, action: String): CompletableFuture<FeedEngagement> {
        require(action in setOf("like", "save"))
        require(postId.length <= 20 && postId.matches(Regex("^[1-9][0-9]*$")))
        return client.request("/api/feed/posts/$postId/$action", method = "POST").thenApply { response ->
            requireSuccess(response)
            val root = parse(response.body)
            val stateField = if (action == "like") "liked" else "saved"
            if (!root.optBoolean("ok") || root.opt(stateField) !is Boolean) throw AuthException("Invalid feed interaction response")
            val post = root.optJSONObject("post") ?: throw AuthException("Invalid feed interaction response")
            if (post.optString("id") != postId) throw AuthException("Invalid feed interaction response")
            FeedEngagement(
                active = root.getBoolean(stateField),
                likesCount = post.boundedCount("likes_count"),
                commentsCount = post.boundedCount("comments_count"),
                savesCount = post.boundedCount("saves_count"),
            )
        }
    }

    fun addFeedComment(postId: String, text: String): CompletableFuture<FeedCounts> {
        require(postId.length <= 20 && postId.matches(Regex("^[1-9][0-9]*$")))
        val normalized = text.trim()
        require(normalized.isNotEmpty()) { "Введите комментарий" }
        require(normalized.length <= MAX_COMMENT_TEXT) { "Комментарий не должен превышать 1000 символов" }
        val body = JSONObject().put("text", normalized).toString().toByteArray(Charsets.UTF_8)
        return client.request(
            path = "/api/feed/posts/$postId/comment",
            method = "POST",
            body = body,
            headers = mapOf("Content-Type" to "application/json", "Accept" to "application/json"),
        ).thenApply { response ->
            if (response.statusCode != 201) throw AuthException.forStatus(response.statusCode)
            val root = parse(response.body)
            val post = root.optJSONObject("post") ?: throw AuthException("Invalid feed comment response")
            if (!root.optBoolean("ok") || post.optString("id") != postId) throw AuthException("Invalid feed comment response")
            FeedCounts(
                post.boundedCount("likes_count"),
                post.boundedCount("comments_count"),
                post.boundedCount("saves_count"),
            )
        }.whenComplete { _, _ -> body.fill(0) }
    }

    fun chats(currentEmail: String): CompletableFuture<List<ChatSummary>> = client.request("/api/chats").thenApply { response ->
        requireSuccess(response)
        val root = parse(response.body)
        if (!root.optBoolean("ok")) throw AuthException("Invalid chats response")
        val chats = root.optJSONArray("chats") ?: throw AuthException("Invalid chats response")
        if (chats.length() > MAX_CHATS) throw AuthException("Invalid chats response")
        buildList {
            for (index in 0 until chats.length()) {
                val item = chats.optJSONObject(index) ?: throw AuthException("Invalid chats response")
                val user = decodeUser(item.optJSONObject("user") ?: throw AuthException("Invalid chats response"), false)
                add(ChatSummary(
                    user,
                    decodeMessage(
                        item.optJSONObject("last_message") ?: throw AuthException("Invalid chats response"),
                        currentEmail,
                        user.email,
                    ),
                ))
            }
        }
    }

    fun chat(currentEmail: String, otherEmail: String): CompletableFuture<ChatThread> =
        client.request("/api/chats/${pathSegment(otherEmail)}/messages").thenApply { response ->
            requireSuccess(response)
            val root = parse(response.body)
            if (!root.optBoolean("ok")) throw AuthException("Invalid chat response")
            val user = decodeUser(root.optJSONObject("user") ?: throw AuthException("Invalid chat response"), false)
            if (!user.email.equals(otherEmail, ignoreCase = true)) throw AuthException("Invalid chat response")
            val messages = root.optJSONArray("messages") ?: throw AuthException("Invalid chat response")
            if (messages.length() > MAX_CHAT_MESSAGES) throw AuthException("Invalid chat response")
            val translation = root.optJSONObject("auto_translation") ?: throw AuthException("Invalid chat response")
            ChatThread(
                user,
                buildList {
                    for (index in 0 until messages.length()) {
                        add(decodeMessage(
                            messages.optJSONObject(index) ?: throw AuthException("Invalid chat response"),
                            currentEmail,
                            otherEmail,
                        ))
                    }
                },
                translation.optBoolean("enabled"),
                translation.bounded("target_language", 16, required = false),
                translation.optBoolean("provider_available"),
            )
        }

    fun sendMessage(currentEmail: String, otherEmail: String, text: String): CompletableFuture<ChatMessage> {
        val normalized = text.trim()
        require(normalized.isNotEmpty()) { "Введите сообщение" }
        require(normalized.length <= MAX_MESSAGE_TEXT) { "Сообщение не должно превышать 2000 символов" }
        val body = JSONObject().put("message", normalized).toString().toByteArray(Charsets.UTF_8)
        return client.request(
            path = "/api/chats/${pathSegment(otherEmail)}/messages",
            method = "POST",
            body = body,
            headers = mapOf("Content-Type" to "application/json", "Accept" to "application/json"),
        ).thenApply { response ->
            if (response.statusCode != 201) throw AuthException.forStatus(response.statusCode)
            val root = parse(response.body)
            if (!root.optBoolean("ok")) throw AuthException("Invalid message response")
            decodeMessage(root.optJSONObject("message") ?: throw AuthException("Invalid message response"), currentEmail, otherEmail)
        }.whenComplete { _, _ -> body.fill(0) }
    }

    fun registerPush(
        deviceId: String,
        token: String,
        appVersion: String,
        locale: String,
    ): CompletableFuture<Unit> {
        require(PushTokenValidator.isValid(token)) { "Invalid FCM token" }
        require(deviceId.matches(Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")))
        val body = JSONObject()
            .put("platform", "android")
            .put("device_id", deviceId)
            .put("token", token)
            .put("app_version", appVersion.take(64))
            .put("locale", locale.lowercase().take(35))
            .toString().toByteArray(Charsets.UTF_8)
        return client.request(
            path = "/api/push/devices",
            method = "POST",
            body = body,
            headers = mapOf("Content-Type" to "application/json", "Accept" to "application/json"),
        ).thenApply { response ->
            if (response.statusCode != 201) throw AuthException.forStatus(response.statusCode)
            val root = parse(response.body)
            val device = root.optJSONObject("device") ?: throw AuthException("Invalid push response")
            if (!root.optBoolean("ok") || device.optString("device_id") != deviceId ||
                device.optString("platform") != "android" || device.has("token")
            ) throw AuthException("Invalid push response")
        }.whenComplete { _, _ -> body.fill(0) }
    }

    fun resolveCallRoom(otherEmail: String, callType: String): CompletableFuture<CallRoom> {
        require(callType in setOf("audio", "video"))
        return client.request(
            path = "/api/calls/room",
            query = mapOf("other_email" to otherEmail, "call_type" to callType),
        ).thenApply { response ->
            requireSuccess(response)
            val root = parse(response.body)
            val roomId = root.optString("call_id").trim()
            val returnedEmail = root.optString("other_email").trim().lowercase()
            val returnedType = root.optString("call_type")
            if (!root.optBoolean("ok") || roomId.length !in 8..128 ||
                !roomId.all { it.isLetterOrDigit() || it == '_' || it == '-' } ||
                returnedEmail != otherEmail.trim().lowercase() || returnedType != callType
            ) throw AuthException("Invalid call-room response")
            CallRoom(roomId, returnedEmail, returnedType)
        }
    }

    fun resolveIncomingCallContext(
        callId: String,
        callType: NativeCallType,
        eventId: String,
        nowEpochSeconds: Long = System.currentTimeMillis() / 1_000,
    ): CompletableFuture<VoipCallPayload> {
        require(callId.length in 8..128 && CALL_IDENTIFIER.matches(callId))
        require(eventId.length in 16..80 && CALL_IDENTIFIER.matches(eventId))
        return client.request(
            path = "/api/calls/$callId/context",
            query = mapOf("call_type" to callType.wireValue, "event_id" to eventId),
        ).thenApply { response ->
            requireSuccess(response)
            val root = parse(response.body)
            val returnedCallId = root.bounded("call_id", 128)
            val returnedCallType = root.bounded("call_type", 16)
            val returnedEventId = root.bounded("event_id", 80)
            val returnedEventType = root.bounded("event_type", 32)
            val callerEmail = root.bounded("caller_email", 254)
            val receiverEmail = root.bounded("receiver_email", 254)
            val expiresValue = root.opt("expires_at")
            if (!root.optBoolean("ok") || expiresValue !is Number ||
                returnedCallId != callId || returnedCallType != callType.wireValue ||
                returnedEventId != eventId || returnedEventType != PushEventType.INCOMING_CALL.wireValue
            ) throw AuthException("Invalid call-context response")
            val expiresAt = expiresValue.toLong()
            VoipPayloadValidator.validate(
                mapOf(
                    "event_id" to returnedEventId,
                    "event_type" to returnedEventType,
                    "call_id" to returnedCallId,
                    "call_type" to returnedCallType,
                    "caller_email" to callerEmail,
                    "receiver_email" to receiverEmail,
                    "expires_at" to expiresAt.toString(),
                ),
                currentEmail = receiverEmail,
                nowEpochSeconds = nowEpochSeconds,
            )
        }
    }

    fun revokePush(deviceId: String): CompletableFuture<Unit> = client.request(
        path = "/api/push/devices/${pathSegment(deviceId)}",
        method = "DELETE",
        headers = mapOf("Accept" to "application/json"),
    ).thenApply { response ->
        requireSuccess(response)
        if (!parse(response.body).optBoolean("ok")) throw AuthException("Invalid push revoke response")
    }

    fun saveOnboarding(answers: OnboardingAnswers): CompletableFuture<AppProfile> {
        OnboardingInputValidator.validate(answers)
        return onboarding(JSONObject()
            .put("looking_for", answers.lookingFor.trim())
            .put("profession", answers.profession.trim())
            .put("goals", answers.goals.trim())
            .put("interests", answers.interests.trim())
            .put("skills", answers.skills.trim())
            .put("languages", answers.languages.trim()))
    }

    fun skipOnboarding(): CompletableFuture<AppProfile> = onboarding(JSONObject().put("action", "skip"))

    fun updateProfile(update: ProfileUpdate): CompletableFuture<AppProfile> {
        ProfileInputValidator.validate(update)
        val body = JSONObject()
            .put("bio", update.bio.trim())
            .put("profession", update.profession.trim())
            .put("looking_for", update.lookingFor.trim())
            .put("goals", update.goals.trim())
            .put("interests", update.interests.trim())
            .put("skills", update.skills.trim())
            .put("languages", update.languages.trim())
            .toString().toByteArray(Charsets.UTF_8)
        require(body.size <= 12 * 1024)
        return client.request(
            path = "/api/me/profile",
            method = "PATCH",
            body = body,
            headers = mapOf("Content-Type" to "application/json", "Accept" to "application/json"),
        ).thenApply { response ->
            requireSuccess(response)
            val root = parse(response.body)
            if (!root.optBoolean("ok")) throw AuthException("Invalid profile response")
            decodeUser(root.optJSONObject("user") ?: throw AuthException("Invalid profile response"), false)
        }.whenComplete { _, _ -> body.fill(0) }
    }

    fun logout(deviceId: String): CompletableFuture<Unit> {
        val refreshToken = tokenStore.read()?.refreshToken ?: return CompletableFuture.completedFuture(Unit)
        val body = JSONObject().put("refresh_token", refreshToken).toString().toByteArray(Charsets.UTF_8)
        return revokePush(deviceId).thenCompose { client.request(
            path = "/api/auth/logout",
            method = "POST",
            body = body,
            headers = mapOf("Content-Type" to "application/json", "Accept" to "application/json"),
        ) }.thenApply { response ->
            requireSuccess(response)
            val json = parse(response.body)
            if (!json.optBoolean("ok") || json.optBoolean("authenticated", true)) {
                throw AuthException("Invalid logout response")
            }
            tokenStore.clear()
        }.whenComplete { _, _ -> body.fill(0) }
    }

    private fun onboarding(json: JSONObject): CompletableFuture<AppProfile> {
        val body = json.toString().toByteArray(Charsets.UTF_8)
        require(body.size <= 8 * 1024)
        return client.request(
            path = "/api/me/onboarding",
            method = "POST",
            body = body,
            headers = mapOf("Content-Type" to "application/json", "Accept" to "application/json"),
        ).thenApply { response ->
            requireSuccess(response)
            decodeUser(parse(response.body).optJSONObject("user") ?: throw AuthException("Invalid profile response"), false)
        }.whenComplete { _, _ -> body.fill(0) }
    }

    private fun decodeProfile(bytes: ByteArray): AppProfile {
        val root = parse(bytes)
        if (!root.optBoolean("ok")) throw AuthException("Invalid profile response")
        val profile = decodeUser(
            root.optJSONObject("user") ?: throw AuthException("Invalid profile response"),
            root.optBoolean("needs_onboarding", true),
        )
        val social = root.optJSONObject("social") ?: throw AuthException("Invalid profile response")
        return profile.copy(
            followersCount = social.boundedSocialCount("followers_count"),
            followingCount = social.boundedSocialCount("following_count"),
        )
    }

    private fun decodeRelationship(value: JSONObject?): SocialRelationship {
        val relationship = value ?: throw AuthException("Invalid social relationship response")
        val isSelf = relationship.boundedBoolean("is_self")
        val isFollowing = relationship.boundedBoolean("is_following")
        val followsYou = relationship.boundedBoolean("follows_you")
        val isMutual = relationship.boundedBoolean("is_mutual")
        if (isMutual != (isFollowing && followsYou)) throw AuthException("Invalid social relationship response")
        if (isSelf && (isFollowing || followsYou || isMutual)) throw AuthException("Invalid social relationship response")
        return SocialRelationship(
            isSelf,
            isFollowing,
            followsYou,
            isMutual,
            relationship.boundedSocialCount("followers_count"),
            relationship.boundedSocialCount("following_count"),
        )
    }

    private fun JSONObject.boundedSocialCount(name: String): Int {
        val value = optInt(name, -1)
        if (value !in 0..MAX_SOCIAL_COUNT) throw AuthException("Invalid social relationship response")
        return value
    }

    private fun JSONObject.boundedBoolean(name: String): Boolean {
        if (!has(name) || opt(name) !is Boolean) throw AuthException("Invalid social relationship response")
        return getBoolean(name)
    }

    private fun decodeUser(user: JSONObject, needsOnboarding: Boolean): AppProfile = AppProfile(
        name = user.bounded("name", 100),
        email = user.bounded("email", 254),
        country = user.bounded("country", 100, required = false),
        bio = user.bounded("bio", 1_000, required = false),
        profession = user.bounded("profession", 160, required = false),
        lookingFor = user.bounded("looking_for", 500, required = false),
        goals = user.boundedList("goals"),
        interests = user.boundedList("interests"),
        skills = user.boundedList("skills"),
        languages = user.boundedList("languages"),
        trustScore = user.optInt("trust_score", 0).coerceIn(0, 100),
        needsOnboarding = needsOnboarding,
    )

    private fun JSONObject.boundedList(
        name: String,
        maximumItems: Int = 12,
        maximumLength: Int = 100,
    ): List<String> = optJSONArray(name)?.let { array ->
        if (array.length() > maximumItems) throw AuthException("Invalid server response")
        buildList {
            for (index in 0 until array.length()) {
                val value = array.optString(index).trim()
                if (value.length > maximumLength) throw AuthException("Invalid server response")
                if (value.isNotEmpty() && value !in this) add(value)
            }
        }
    }.orEmpty()

    private fun JSONObject.boundedCount(name: String): Int {
        val value = optInt(name, -1)
        if (value !in 0..MAX_AGGREGATE_COUNT) throw AuthException("Invalid feed response")
        return value
    }

    private fun JSONObject.requiredBoolean(name: String): Boolean {
        if (!has(name) || opt(name) !is Boolean) throw AuthException("Invalid feed response")
        return getBoolean(name)
    }

    private fun decodeMessage(item: JSONObject, currentEmail: String, otherEmail: String): ChatMessage {
        val sender = item.bounded("from", 254)
        val receiver = item.bounded("to", 254)
        val participants = setOf(sender.lowercase(), receiver.lowercase())
        if (participants != setOf(currentEmail.lowercase(), otherEmail.lowercase())) {
            throw AuthException("Invalid chat participants")
        }
        val id = item.optString("id").trim()
        if (id.isEmpty() || id.length > 80) throw AuthException("Invalid message response")
        val text = item.bounded("message", MAX_MESSAGE_TEXT, required = false)
        val mediaUrl = item.bounded("media_url", 2_048, required = false)
        val mediaType = item.bounded("media_type", 32, required = false)
        val hasMedia = mediaUrl.isNotEmpty() && mediaType.isNotEmpty()
        if (text.isEmpty() && !hasMedia) throw AuthException("Invalid message response")
        val translated = item.bounded("translated_text", MAX_MESSAGE_TEXT, required = false)
        val language = item.bounded("translation_language", 16, required = false)
        if (translated.isNotEmpty() != language.isNotEmpty()) throw AuthException("Invalid message translation")
        val mine = item.optBoolean("mine")
        if (mine != sender.equals(currentEmail, ignoreCase = true)) throw AuthException("Invalid message direction")
        return ChatMessage(
            id, sender, receiver, text,
            item.bounded("time", 80, required = false),
            mine,
            item.bounded("source_language", 16, required = false),
            translated,
            language,
            hasMedia,
        )
    }

    private fun pathSegment(value: String): String {
        require(value.length in 3..254 && value.all { it.code in 33..126 }) { "Invalid chat address" }
        return value.toByteArray(Charsets.UTF_8).joinToString("") { byte ->
            val unsigned = byte.toInt() and 0xff
            val character = unsigned.toChar()
            if (character.isLetterOrDigit() || character in "-._~") character.toString() else "%${unsigned.toString(16).uppercase().padStart(2, '0')}"
        }
    }

    private fun parse(bytes: ByteArray): JSONObject {
        if (bytes.isEmpty() || bytes.size > 512 * 1024) throw AuthException("Invalid server response")
        return runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }
            .getOrElse { throw AuthException("Invalid profile response") }
    }

    private fun JSONObject.bounded(name: String, maximum: Int, required: Boolean = true): String {
        val value = optString(name).trim()
        if (value.length > maximum || required && value.isEmpty()) throw AuthException("Invalid profile response")
        return value
    }

    private fun requireSuccess(response: ApiResponse) {
        if (response.statusCode !in 200..299) throw AuthException.forStatus(response.statusCode)
    }

    private companion object {
        val CALL_IDENTIFIER = Regex("^[A-Za-z0-9_-]+$")
        const val MAX_MATCHES = 20
        const val MAX_MATCH_REASONS = 8
        const val MAX_MATCH_SCORE = 10_000
        const val FEED_PAGE_SIZE = 10
        const val MAX_AGGREGATE_COUNT = 10_000_000
        const val MAX_CHATS = 100
        const val MAX_CHAT_MESSAGES = 500
        const val MAX_MESSAGE_TEXT = 2_000
        const val MAX_COMMENT_TEXT = 1_000
        const val MAX_SOCIAL_COUNT = 100_000_000
        const val SOCIAL_PAGE_SIZE = 20
    }
}
