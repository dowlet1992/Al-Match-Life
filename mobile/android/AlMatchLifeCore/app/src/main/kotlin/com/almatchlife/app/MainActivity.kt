package com.almatchlife.app

import android.Manifest
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Rect
import android.text.InputType
import android.text.InputFilter
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.ViewTreeObserver
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ImageView
import android.widget.HorizontalScrollView
import android.widget.ScrollView
import android.widget.TextView
import android.graphics.drawable.GradientDrawable
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.content.ContextCompat
import com.almatchlife.core.system.NotificationPermissionController
import com.almatchlife.core.system.NotificationPermissionState
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import java.util.Locale

class MainActivity : Activity() {
    private data class PrimaryNavItem(val key: String, val label: Int, val icon: Int, val action: () -> Unit)

    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var auth: AuthApiClient
    private lateinit var appApi: AppApiClient
    private lateinit var sessionStore: com.almatchlife.core.SessionTokenStore
    private lateinit var applicationGraph: AlMatchApplication
    private lateinit var notificationPermission: NotificationPermissionController
    private var notificationProfile: AppProfile? = null
    private var currentPrimarySection = "home"
    private var currentNestedScreen = "none"
    private val imageLoads = mutableSetOf<java.util.concurrent.CompletableFuture<android.graphics.Bitmap>>()
    private val displayedBitmaps = mutableSetOf<android.graphics.Bitmap>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.enableEdgeToEdge(window)
        currentPrimarySection = savedInstanceState?.getString(PRIMARY_SECTION_STATE)
            ?.takeIf { it in PRIMARY_SECTIONS } ?: "home"
        currentNestedScreen = savedInstanceState?.getString(NESTED_SCREEN_STATE)
            ?.takeIf { it in RESTORABLE_NESTED_SCREENS } ?: "none"
        applicationGraph = application as AlMatchApplication
        sessionStore = applicationGraph.sessionStore
        auth = applicationGraph.authApi
        appApi = applicationGraph.appApi
        notificationPermission = NotificationPermissionController(
            this,
            getSharedPreferences("notification_permission", MODE_PRIVATE),
        )
        if (sessionStore.read() == null) {
            currentPrimarySection = "home"
            currentNestedScreen = "none"
            showLogin()
        } else loadProfile()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString(PRIMARY_SECTION_STATE, currentPrimarySection)
        outState.putString(NESTED_SCREEN_STATE, currentNestedScreen)
        super.onSaveInstanceState(outState)
    }

    override fun onResume() {
        super.onResume()
        val profile = notificationProfile
        if (profile != null && currentNestedScreen == "notifications") showNotifications(profile)
    }

    private fun showLogin() {
        ProfileDraftMemory.clear()
        val content = form(R.string.sign_in)
        val login = field(R.string.login_hint, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS)
        val password = passwordField()
        val status = statusView()
        val submit = button(R.string.sign_in)
        content.addView(login); content.addView(password); content.addView(submit); content.addView(status)
        content.addView(button(R.string.create_account).apply { setOnClickListener { showRegistration() } })
        submit.setOnClickListener {
            submit.isEnabled = false; status.setText(R.string.working)
            val secret = password.text.toString()
            runCatching { auth.login(login.text.toString(), secret) }
                .onSuccess { future -> future.whenComplete { result, failure ->
                    mainHandler.post {
                        password.text.clear()
                        if (!isDestroyed) completeAuth(result, failure, submit, status)
                    }
                } }
                .onFailure { completeAuth(null, it, submit, status); password.text.clear() }
        }
        display(content)
    }

    private fun showRegistration() {
        val content = form(R.string.create_account)
        val name = field(R.string.name_hint)
        val age = field(R.string.age_hint, InputType.TYPE_CLASS_NUMBER)
        val country = field(R.string.country_hint)
        val email = field(R.string.email_hint, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS)
        val password = passwordField()
        val status = statusView()
        val submit = button(R.string.create_account)
        listOf(name, age, country, email, password, submit, status).forEach(content::addView)
        content.addView(button(R.string.back_to_login).apply { setOnClickListener { showLogin() } })
        submit.setOnClickListener {
            submit.isEnabled = false; status.setText(R.string.working)
            val secret = password.text.toString()
            runCatching { auth.register(name.text.toString(), age.text.toString(), country.text.toString(), email.text.toString(), secret) }
                .onSuccess { future -> future.whenComplete { result, failure ->
                    mainHandler.post {
                        password.text.clear()
                        if (!isDestroyed) completeAuth(result, failure, submit, status)
                    }
                } }
                .onFailure { completeAuth(null, it, submit, status); password.text.clear() }
        }
        display(content)
    }

    private fun showVerification(required: AuthResult.VerificationRequired) {
        val content = form(R.string.verify_account)
        content.addView(TextView(this).apply {
            text = getString(if (required.deliverySent) R.string.code_sent else R.string.code_delivery_unavailable)
        })
        val code = field(R.string.code_hint, InputType.TYPE_CLASS_NUMBER)
        val status = statusView()
        val submit = button(R.string.verify_account)
        content.addView(code); content.addView(submit); content.addView(status)
        content.addView(button(R.string.back_to_login).apply { setOnClickListener { showLogin() } })
        submit.setOnClickListener {
            submit.isEnabled = false; status.setText(R.string.working)
            runCatching { auth.verify(required.contactType, required.contactValue, code.text.toString()) }
                .onSuccess { it.whenComplete { result, failure ->
                    mainHandler.post { if (!isDestroyed) completeAuth(result, failure, submit, status) }
                } }
                .onFailure { completeAuth(null, it, submit, status) }
        }
        display(content)
    }

    private fun completeAuth(result: AuthResult?, failure: Throwable?, submit: Button, status: TextView) {
        submit.isEnabled = true
        if (failure != null) {
            status.text = readableFailure(failure)
            return
        }
        when (result) {
            is AuthResult.Authenticated -> loadProfile()
            is AuthResult.VerificationRequired -> showVerification(result)
            null -> status.setText(R.string.request_failed)
        }
    }

    private fun loadProfile() {
        val content = form(R.string.welcome)
        val status = statusView().apply { setText(R.string.loading_profile) }
        content.addView(status)
        display(content)
        appApi.profile().whenComplete { profile, failure ->
            mainHandler.post {
                if (isDestroyed) return@post
                if (failure != null) {
                    if (sessionStore.read() == null) showLogin()
                    else {
                        status.text = readableFailure(failure)
                        content.addView(button(R.string.retry).apply { setOnClickListener { loadProfile() } })
                    }
                } else if (profile.needsOnboarding) showOnboarding() else restoreAuthenticatedScreen(profile)
            }
        }
    }

    private fun restoreAuthenticatedScreen(profile: AppProfile) {
        when (currentNestedScreen) {
            "social_followers" -> loadSocialList(profile, "followers")
            "social_following" -> loadSocialList(profile, "following")
            "notifications" -> showNotifications(profile)
            "profile_editor" -> showProfileEditor(profile)
            else -> openPrimarySection(profile, currentPrimarySection)
        }
    }

    private fun openPrimarySection(profile: AppProfile, section: String) {
        when (section) {
            "matches" -> loadMatches(profile)
            "feed" -> loadFeed(profile)
            "messages" -> loadChats(profile)
            else -> showHome(profile)
        }
    }

    private fun showOnboarding() {
        val content = form(R.string.onboarding_title)
        content.addView(TextView(this).apply { setText(R.string.onboarding_intro) })
        val lookingFor = field(R.string.looking_for_hint)
        val profession = field(R.string.profession_hint)
        val goals = field(R.string.goals_hint)
        val interests = field(R.string.interests_hint)
        val skills = field(R.string.skills_hint)
        val languages = field(R.string.languages_hint)
        val status = statusView()
        val save = button(R.string.save_and_continue)
        listOf(lookingFor, profession, goals, interests, skills, languages, save, status).forEach(content::addView)
        val skip = button(R.string.skip_for_now)
        content.addView(skip)
        save.setOnClickListener {
            val answers = OnboardingAnswers(
                lookingFor.text.toString(), profession.text.toString(), goals.text.toString(),
                interests.text.toString(), skills.text.toString(), languages.text.toString(),
            )
            runOnboarding(save, skip, status) { appApi.saveOnboarding(answers) }
        }
        skip.setOnClickListener { runOnboarding(save, skip, status, appApi::skipOnboarding) }
        display(content)
    }

    private fun runOnboarding(
        save: Button,
        skip: Button,
        status: TextView,
        request: () -> java.util.concurrent.CompletableFuture<AppProfile>,
    ) {
        save.isEnabled = false; skip.isEnabled = false; status.setText(R.string.working)
        runCatching(request).onSuccess { future ->
            future.whenComplete { profile, failure -> mainHandler.post {
                if (isDestroyed) return@post
                save.isEnabled = true; skip.isEnabled = true
                if (failure == null) showHome(profile) else status.text = readableFailure(failure)
            } }
        }.onFailure {
            save.isEnabled = true; skip.isEnabled = true; status.text = readableFailure(it)
        }
    }

    private fun showHome(profile: AppProfile) {
        val content = form(R.string.home_title)
        content.addView(TextView(this).apply {
            text = getString(R.string.profile_summary, profile.name, profile.email, profile.country)
            gravity = Gravity.CENTER
        })
        if (profile.profession.isNotBlank()) content.addView(TextView(this).apply {
            text = getString(R.string.profession_value, profile.profession)
        })
        if (profile.interests.isNotEmpty()) content.addView(TextView(this).apply {
            text = getString(R.string.interests_value, profile.interests.joinToString(", "))
        })
        content.addView(TextView(this).apply {
            text = getString(R.string.trust_score_value, profile.trustScore)
        })
        val socialActions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(buttonText(getString(R.string.followers_count, profile.followersCount)).apply {
                setOnClickListener { loadSocialList(profile, "followers") }
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(buttonText(getString(R.string.following_count, profile.followingCount)).apply {
                setOnClickListener { loadSocialList(profile, "following") }
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        content.addView(socialActions)
        content.addView(button(R.string.edit_profile).apply { setOnClickListener { showProfileEditor(profile) } })
        content.addView(button(R.string.ai_matches).apply { setOnClickListener { loadMatches(profile) } })
        content.addView(button(R.string.feed).apply { setOnClickListener { loadFeed(profile) } })
        content.addView(button(R.string.messages).apply { setOnClickListener { loadChats(profile) } })
        content.addView(button(R.string.notifications).apply { setOnClickListener { showNotifications(profile) } })
        content.addView(TextView(this).apply { setText(R.string.home_next_features); gravity = Gravity.CENTER })
        val status = statusView()
        val logout = button(R.string.sign_out)
        content.addView(logout); content.addView(status)
        logout.setOnClickListener {
            logout.isEnabled = false; status.setText(R.string.working)
            appApi.logout(applicationGraph.deviceIdentity.id()).whenComplete { _, failure -> mainHandler.post {
                if (isDestroyed) return@post
                logout.isEnabled = true
                if (failure == null) {
                    ProfileDraftMemory.clear(profile.email)
                    showLogin()
                } else status.text = readableFailure(failure)
            } }
        }
        displayMain(content, profile, "home")
    }

    private fun loadSocialList(
        profile: AppProfile,
        kind: String,
        cursor: String = "",
        accumulated: List<SocialListItem> = emptyList(),
    ) {
        val title = if (kind == "followers") R.string.followers else R.string.following
        val content = form(title)
        val status = statusView().apply { setText(R.string.loading_social_list) }
        content.addView(status)
        content.addView(button(R.string.back_home).apply { setOnClickListener { loadProfile() } })
        displayMain(content, profile, "home", "social_$kind")
        appApi.socialList(profile.email, kind, cursor).whenComplete { page, failure -> mainHandler.post {
            if (isDestroyed) return@post
            if (failure != null) {
                status.text = readableFailure(failure)
                content.addView(button(R.string.retry).apply {
                    setOnClickListener { loadSocialList(profile, kind, cursor, accumulated) }
                })
                return@post
            }
            val combined = (accumulated + page.items).distinctBy { it.profile.email.lowercase() }
            showSocialList(profile, kind, combined, page.nextCursor)
        } }
    }

    private fun showSocialList(
        profile: AppProfile,
        kind: String,
        items: List<SocialListItem>,
        nextCursor: String,
    ) {
        val content = form(if (kind == "followers") R.string.followers else R.string.following)
        if (items.isEmpty()) content.addView(TextView(this).apply {
            setText(if (kind == "followers") R.string.empty_followers else R.string.empty_following)
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(48), dp(16), dp(48))
        }) else items.forEach { content.addView(socialCard(profile, kind, it)) }
        if (nextCursor.isNotEmpty()) content.addView(button(R.string.load_more).apply {
            setOnClickListener { loadSocialList(profile, kind, nextCursor, items) }
        })
        content.addView(button(R.string.back_home).apply { setOnClickListener { loadProfile() } })
        displayMain(content, profile, "home", "social_$kind")
    }

    private fun socialCard(owner: AppProfile, kind: String, item: SocialListItem): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(16), dp(20), dp(16))
        background = GradientDrawable().apply {
            setColor(color(R.color.app_surface)); cornerRadius = dp(16).toFloat()
            setStroke(dp(1), color(R.color.app_outline))
        }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        ).apply { setMargins(0, dp(6), 0, dp(6)) }
        addView(TextView(context).apply { text = item.profile.name; textSize = 18f })
        val details = listOf(item.profile.profession, item.profile.country).filter(String::isNotBlank).joinToString(" · ")
        if (details.isNotEmpty()) addView(TextView(context).apply { text = details; textSize = 14f })
        val relationLabel = when {
            item.relationship.isMutual -> R.string.mutual_follow
            item.relationship.followsYou -> R.string.follows_you
            else -> 0
        }
        if (relationLabel != 0) addView(TextView(context).apply { setText(relationLabel); textSize = 13f })
        if (!item.relationship.isSelf) addView(button(
            if (item.relationship.isFollowing) R.string.unfollow else R.string.follow,
        ).apply {
            setOnClickListener {
                isEnabled = false
                appApi.setFollowing(item.profile.email, !item.relationship.isFollowing).whenComplete { _, failure ->
                    mainHandler.post {
                        if (isDestroyed) return@post
                        if (failure == null) loadSocialList(owner, kind)
                        else {
                            isEnabled = true
                            text = readableFailure(failure)
                        }
                    }
                }
            }
        })
    }

    private fun showNotifications(profile: AppProfile) {
        notificationProfile = profile
        val content = form(R.string.notifications)
        val status = statusView()
        content.addView(TextView(this).apply { setText(R.string.notifications_explanation) })
        content.addView(status)
        when (notificationPermission.state(this)) {
            NotificationPermissionState.GRANTED -> {
                status.setText(R.string.notification_permission_granted)
                content.addView(button(R.string.sync_notifications).apply { setOnClickListener { syncNotifications(status) } })
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE &&
                    !notificationPermission.canUseFullScreenIntent()
                ) {
                    content.addView(TextView(this).apply { setText(R.string.full_screen_call_explanation) })
                    content.addView(button(R.string.open_full_screen_call_settings).apply {
                        setOnClickListener {
                            openSettingsSafely(notificationPermission.fullScreenSettingsIntent(), status)
                        }
                    })
                } else {
                    content.addView(TextView(this).apply { setText(R.string.incoming_call_alerts_ready) })
                }
            }
            NotificationPermissionState.REQUESTABLE -> content.addView(
                button(R.string.allow_notifications).apply { setOnClickListener { requestNotificationPermission() } },
            )
            NotificationPermissionState.EXPLANATION_REQUIRED -> {
                status.setText(R.string.notification_permission_rationale)
                content.addView(button(R.string.allow_notifications).apply { setOnClickListener { requestNotificationPermission() } })
            }
            NotificationPermissionState.SETTINGS_REQUIRED -> {
                status.setText(R.string.notification_settings_required)
                content.addView(button(R.string.open_notification_settings).apply {
                    setOnClickListener {
                        openSettingsSafely(notificationPermission.notificationSettingsIntent(), status)
                    }
                })
            }
        }
        content.addView(button(R.string.back_home).apply { setOnClickListener { showHome(profile) } })
        displayMain(content, profile, "home", "notifications")
    }

    private fun openSettingsSafely(intent: Intent, status: TextView) {
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            status.setText(R.string.settings_unavailable)
        } catch (_: SecurityException) {
            status.setText(R.string.settings_unavailable)
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            notificationProfile?.let(::showNotifications)
            return
        }
        notificationPermission.markRequestStarted()
        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_PERMISSION_REQUEST)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != NOTIFICATION_PERMISSION_REQUEST) return
        val profile = notificationProfile ?: return
        showNotifications(profile)
    }

    private fun syncNotifications(status: TextView) {
        if (FirebaseApp.getApps(this).isEmpty()) {
            status.setText(R.string.firebase_not_configured)
            return
        }
        status.setText(R.string.syncing_notifications)
        legacyFcmTokenTask().addOnCompleteListener { task ->
            if (isDestroyed) return@addOnCompleteListener
            if (!task.isSuccessful) {
                status.setText(R.string.notification_sync_failed)
                return@addOnCompleteListener
            }
            val token = task.result
            if (!PushTokenValidator.isValid(token)) {
                status.setText(R.string.notification_sync_failed)
                return@addOnCompleteListener
            }
            appApi.registerPush(
                applicationGraph.deviceIdentity.id(), token, BuildConfig.VERSION_NAME,
                Locale.getDefault().toLanguageTag(),
            ).whenComplete { _, failure -> mainHandler.post {
                if (!isDestroyed) status.setText(
                    if (failure == null) R.string.notifications_ready else R.string.notification_sync_failed,
                )
            } }
        }
    }

    @Suppress("DEPRECATION") // Server delivery still targets FCM registration tokens, not Firebase installation IDs.
    private fun legacyFcmTokenTask() = FirebaseMessaging.getInstance().token

    private fun loadMatches(profile: AppProfile) {
        val content = form(R.string.ai_matches)
        val status = statusView().apply { setText(R.string.loading_matches) }
        content.addView(status)
        content.addView(button(R.string.back_home).apply { setOnClickListener { showHome(profile) } })
        displayMain(content, profile, "matches")
        appApi.matches().whenComplete { matches, failure -> mainHandler.post {
            if (isDestroyed) return@post
            if (failure != null) {
                status.text = readableFailure(failure)
                content.addView(button(R.string.retry).apply { setOnClickListener { loadMatches(profile) } })
            } else {
                content.removeView(status)
                if (matches.isEmpty()) content.addView(TextView(this).apply {
                    setText(R.string.no_matches); gravity = Gravity.CENTER
                    setPadding(dp(16), dp(48), dp(16), dp(48))
                }, 1)
                else matches.asReversed().forEach { match -> content.addView(matchCard(match), 1) }
            }
        } }
    }

    private fun matchCard(match: AiMatch): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(16), dp(20), dp(16))
        background = GradientDrawable().apply {
            setColor(color(R.color.app_match_surface)); cornerRadius = dp(16).toFloat()
            setStroke(dp(1), color(R.color.app_primary))
        }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        ).apply { setMargins(0, dp(8), 0, dp(8)) }
        addView(TextView(context).apply {
            text = match.profile.name; textSize = 21f
        })
        addView(TextView(context).apply {
            text = getString(R.string.match_score, match.score, match.level)
        })
        val details = listOf(match.profile.profession, match.profile.country).filter(String::isNotBlank).joinToString(" · ")
        if (details.isNotEmpty()) addView(TextView(context).apply { text = details })
        match.reasons.forEach { reason -> addView(TextView(context).apply { text = getString(R.string.match_reason, reason) }) }
    }

    private fun loadFeed(profile: AppProfile) {
        val content = form(R.string.feed)
        val status = statusView().apply { setText(R.string.loading_feed) }
        val back = button(R.string.back_home).apply { setOnClickListener { showHome(profile) } }
        content.addView(status)
        content.addView(back)
        displayMain(content, profile, "feed")
        fun requestPage(cursor: String, loading: TextView) {
            appApi.feed(cursor).whenComplete { page, failure -> mainHandler.post {
                if (isDestroyed || !content.isAttachedToWindow) return@post
                if (failure != null) {
                    loading.text = readableFailure(failure)
                    val retryPage = button(R.string.retry)
                    retryPage.setOnClickListener {
                        content.removeView(retryPage)
                        loading.setText(R.string.loading_feed)
                        requestPage(cursor, loading)
                    }
                    content.addView(retryPage, content.indexOfChild(back))
                    return@post
                }
                content.removeView(loading)
                if (cursor.isEmpty() && page.posts.isEmpty()) content.addView(TextView(this).apply {
                    setText(R.string.empty_feed); gravity = Gravity.CENTER
                    setPadding(dp(16), dp(48), dp(16), dp(48))
                }, content.indexOfChild(back))
                page.posts.forEach { post -> content.addView(feedCard(post), content.indexOfChild(back)) }
                if (page.nextCursor.isNotEmpty()) content.addView(button(R.string.load_more).apply {
                    setOnClickListener {
                        content.removeView(this)
                        val moreStatus = statusView().apply { setText(R.string.loading_feed) }
                        content.addView(moreStatus, content.indexOfChild(back))
                        requestPage(page.nextCursor, moreStatus)
                    }
                }, content.indexOfChild(back))
            } }
        }
        requestPage("", status)
    }

    private fun feedCard(post: FeedPost): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(16), dp(20), dp(16))
        background = GradientDrawable().apply {
            setColor(color(R.color.app_surface)); cornerRadius = dp(16).toFloat()
            setStroke(dp(1), color(R.color.app_outline))
        }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        ).apply { setMargins(0, dp(8), 0, dp(8)) }
        addView(TextView(context).apply { text = post.authorName; textSize = 20f })
        val metadata = listOf(post.type, post.location, post.date).filter(String::isNotBlank).joinToString(" · ")
        if (metadata.isNotEmpty()) addView(TextView(context).apply { text = metadata; textSize = 13f })
        if (post.text.isNotEmpty()) addView(TextView(context).apply {
            text = post.text; textSize = 17f; setPadding(0, dp(10), 0, dp(6))
        })
        if (post.imageUrls.isNotEmpty()) {
            val galleryUrls = post.imageUrls.take(4)
            val gallery = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
            val galleryWidth = (resources.displayMetrics.widthPixels - dp(64)).coerceAtLeast(dp(240))
            val galleryLoaders = mutableListOf<() -> Unit>()
            galleryUrls.forEachIndexed { index, imageUrl ->
                val mediaSlot = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    layoutParams = LinearLayout.LayoutParams(galleryWidth, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                        marginEnd = if (index < galleryUrls.lastIndex) dp(8) else 0
                    }
                }
                val mediaStatus = TextView(context).apply {
                    setText(R.string.media_waiting)
                    minHeight = dp(120)
                    gravity = Gravity.CENTER
                    accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
                }
                val retryImage = button(R.string.retry).apply {
                    visibility = View.GONE
                    isEnabled = false
                    contentDescription = getString(
                        R.string.media_retry_description,
                        post.authorName,
                        (index + 1).toString(),
                        galleryUrls.size.toString(),
                    )
                }
                mediaSlot.addView(mediaStatus)
                mediaSlot.addView(retryImage)
                mediaSlot.addView(TextView(context).apply {
                    text = getString(R.string.media_position, (index + 1).toString(), galleryUrls.size.toString())
                    gravity = Gravity.CENTER
                })
                gallery.addView(mediaSlot)
                var advancedToNext = false
                fun startImageLoad() {
                    mediaStatus.setText(R.string.media_loading)
                    retryImage.visibility = View.GONE
                    retryImage.isEnabled = false
                    val imageLoad = applicationGraph.imageLoader.load(imageUrl)
                    imageLoads += imageLoad
                    imageLoad.whenComplete { bitmap, failure -> mainHandler.post {
                        imageLoads -= imageLoad
                        if (isDestroyed || mediaSlot.parent !== gallery || !gallery.isAttachedToWindow) {
                            bitmap?.recycle()
                            return@post
                        }
                        if (failure != null) {
                            mediaStatus.setText(R.string.media_load_failed)
                            retryImage.visibility = View.VISIBLE
                            retryImage.isEnabled = true
                        } else {
                            displayedBitmaps += bitmap
                            val position = mediaSlot.indexOfChild(mediaStatus)
                            mediaSlot.removeView(mediaStatus)
                            mediaSlot.removeView(retryImage)
                            mediaSlot.addView(ImageView(context).apply {
                                setImageBitmap(bitmap)
                                adjustViewBounds = true
                                maxHeight = dp(420)
                                contentDescription = getString(
                                    R.string.feed_image_description_position,
                                    post.authorName,
                                    (index + 1).toString(),
                                    galleryUrls.size.toString(),
                                )
                            }, position)
                        }
                        if (!advancedToNext) {
                            advancedToNext = true
                            galleryLoaders.getOrNull(index + 1)?.invoke()
                        }
                    } }
                }
                retryImage.setOnClickListener {
                    if (retryImage.isEnabled) startImageLoad()
                }
                galleryLoaders += ::startImageLoad
            }
            runWhenVisible(gallery) { galleryLoaders.firstOrNull()?.invoke() }
            addView(HorizontalScrollView(context).apply {
                isHorizontalScrollBarEnabled = false
                contentDescription = getString(R.string.feed_gallery_description, galleryUrls.size.toString())
                addView(gallery)
            })
        } else if (post.hasMedia) addView(TextView(context).apply { setText(R.string.media_not_loaded) })
        if (post.hashtags.isNotEmpty()) addView(TextView(context).apply {
            text = post.hashtags.joinToString(" ") { "#$it" }
        })
        var liked = post.liked
        var saved = post.saved
        var likesCount = post.likesCount
        var commentsCount = post.commentsCount
        var savesCount = post.savesCount
        val counts = TextView(context)
        val interactionStatus = TextView(context).apply {
            visibility = View.GONE
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        val likeButton = button(if (liked) R.string.unlike_post else R.string.like_post)
        val saveButton = button(if (saved) R.string.unsave_post else R.string.save_post)
        val commentButton = button(R.string.comment_post)
        val commentInput = multiLineField(R.string.comment_hint, "").apply {
            minLines = 2
            maxLines = 4
            filters = arrayOf(InputFilter.LengthFilter(1_000))
        }
        val sendComment = button(R.string.send_comment)
        val cancelComment = button(R.string.cancel)
        val commentComposer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            addView(commentInput)
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                addView(sendComment, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addView(cancelComment, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            })
        }
        fun bindEngagement() {
            counts.text = getString(R.string.feed_counts, likesCount, commentsCount, savesCount)
            likeButton.setText(if (liked) R.string.unlike_post else R.string.like_post)
            saveButton.setText(if (saved) R.string.unsave_post else R.string.save_post)
        }
        fun toggle(button: Button, action: String) {
            button.isEnabled = false
            interactionStatus.visibility = View.GONE
            appApi.toggleFeedInteraction(post.id, action).whenComplete { result, failure -> mainHandler.post {
                if (isDestroyed || !this.isAttachedToWindow) return@post
                button.isEnabled = true
                if (failure != null) {
                    interactionStatus.text = readableFailure(failure)
                    interactionStatus.visibility = View.VISIBLE
                } else {
                    if (action == "like") liked = result.active else saved = result.active
                    likesCount = result.likesCount
                    commentsCount = result.commentsCount
                    savesCount = result.savesCount
                    bindEngagement()
                }
            } }
        }
        likeButton.setOnClickListener { if (likeButton.isEnabled) toggle(likeButton, "like") }
        saveButton.setOnClickListener { if (saveButton.isEnabled) toggle(saveButton, "save") }
        commentButton.setOnClickListener {
            commentComposer.visibility = View.VISIBLE
            commentInput.requestFocus()
        }
        cancelComment.setOnClickListener { commentComposer.visibility = View.GONE }
        sendComment.setOnClickListener {
            sendComment.isEnabled = false
            interactionStatus.visibility = View.GONE
            runCatching { appApi.addFeedComment(post.id, commentInput.text.toString()) }
                .onSuccess { future -> future.whenComplete { result, failure -> mainHandler.post {
                    if (isDestroyed || !this.isAttachedToWindow) return@post
                    sendComment.isEnabled = true
                    if (failure != null) {
                        interactionStatus.text = readableFailure(failure)
                        interactionStatus.visibility = View.VISIBLE
                    } else {
                        likesCount = result.likesCount
                        commentsCount = result.commentsCount
                        savesCount = result.savesCount
                        bindEngagement()
                        commentInput.text.clear()
                        commentComposer.visibility = View.GONE
                        interactionStatus.setText(R.string.comment_sent)
                        interactionStatus.visibility = View.VISIBLE
                    }
                } } }
                .onFailure {
                    sendComment.isEnabled = true
                    interactionStatus.text = readableFailure(it)
                    interactionStatus.visibility = View.VISIBLE
                }
        }
        bindEngagement()
        addView(counts)
        addView(LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(likeButton, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(commentButton, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(saveButton, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        })
        addView(commentComposer)
        addView(interactionStatus)
    }

    private fun loadChats(profile: AppProfile) {
        val content = form(R.string.messages)
        val status = statusView().apply { setText(R.string.loading_chats) }
        content.addView(status)
        content.addView(button(R.string.back_home).apply { setOnClickListener { showHome(profile) } })
        displayMain(content, profile, "messages")
        appApi.chats(profile.email).whenComplete { chats, failure -> mainHandler.post {
            if (isDestroyed) return@post
            if (failure != null) {
                status.text = readableFailure(failure)
                content.addView(button(R.string.retry).apply { setOnClickListener { loadChats(profile) } })
            } else {
                content.removeView(status)
                if (chats.isEmpty()) content.addView(TextView(this).apply {
                    setText(R.string.empty_chats); gravity = Gravity.CENTER
                    setPadding(dp(16), dp(48), dp(16), dp(48))
                }, 1)
                else chats.asReversed().forEach { chat -> content.addView(chatSummaryCard(profile, chat), 1) }
            }
        } }
    }

    private fun chatSummaryCard(profile: AppProfile, chat: ChatSummary): View = Button(this).apply {
        isAllCaps = false
        val preview = if (chat.lastMessage.text.isNotEmpty()) chat.lastMessage.text.take(90) else getString(R.string.media_message)
        text = getString(R.string.chat_preview, chat.user.name, preview)
        gravity = Gravity.START or Gravity.CENTER_VERTICAL
        minHeight = dp(48)
        setPadding(dp(16), dp(12), dp(16), dp(12))
        setOnClickListener { loadChat(profile, chat.user.email) }
    }

    private fun loadChat(profile: AppProfile, otherEmail: String) {
        currentPrimarySection = "messages"
        currentNestedScreen = "none"
        val content = form(R.string.chat)
        val status = statusView().apply { setText(R.string.loading_messages) }
        content.addView(status)
        content.addView(button(R.string.back_chats).apply { setOnClickListener { loadChats(profile) } })
        display(content)
        appApi.chat(profile.email, otherEmail).whenComplete { thread, failure -> mainHandler.post {
            if (isDestroyed) return@post
            if (failure != null) {
                status.text = readableFailure(failure)
                content.addView(button(R.string.retry).apply { setOnClickListener { loadChat(profile, otherEmail) } })
            } else showChatThread(profile, thread)
        } }
    }

    private fun showChatThread(profile: AppProfile, thread: ChatThread) {
        currentPrimarySection = "messages"
        currentNestedScreen = "none"
        val content = formText(thread.user.name)
        val callActions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(button(R.string.audio_call).apply {
                setOnClickListener { showCallPreflight(profile, thread.user, "audio") }
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(button(R.string.video_call).apply {
                setOnClickListener { showCallPreflight(profile, thread.user, "video") }
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        content.addView(callActions)
        if (thread.autoTranslationEnabled) content.addView(TextView(this).apply {
            text = getString(
                if (thread.translationProviderAvailable) R.string.translation_active else R.string.translation_unavailable,
                thread.translationLanguage,
            )
            gravity = Gravity.CENTER
        })
        if (thread.messages.isEmpty()) content.addView(TextView(this).apply {
            setText(R.string.empty_messages); gravity = Gravity.CENTER
            setPadding(dp(16), dp(40), dp(16), dp(40))
        }) else thread.messages.forEach { content.addView(messageBubble(it)) }
        val input = multiLineField(R.string.message_hint, "").apply {
            minLines = 2; maxLines = 5; filters = arrayOf(InputFilter.LengthFilter(2_000))
        }
        val send = button(R.string.send)
        val status = statusView()
        content.addView(input); content.addView(send); content.addView(status)
        content.addView(button(R.string.back_chats).apply { setOnClickListener { loadChats(profile) } })
        send.setOnClickListener {
            send.isEnabled = false; status.setText(R.string.sending)
            runCatching { appApi.sendMessage(profile.email, thread.user.email, input.text.toString()) }
                .onSuccess { future -> future.whenComplete { _, failure -> mainHandler.post {
                    if (isDestroyed) return@post
                    send.isEnabled = true
                    if (failure == null) {
                        input.text.clear(); loadChat(profile, thread.user.email)
                    } else status.text = readableFailure(failure)
                } } }
                .onFailure { send.isEnabled = true; status.text = readableFailure(it) }
        }
        display(content)
    }

    private fun showCallPreflight(profile: AppProfile, other: AppProfile, callType: String) {
        currentPrimarySection = "messages"
        currentNestedScreen = "none"
        val content = form(if (callType == "video") R.string.video_call else R.string.audio_call)
        content.addView(TextView(this).apply {
            text = getString(R.string.calling_user, other.name)
            gravity = Gravity.CENTER
        })
        val status = statusView().apply { setText(R.string.checking_call_access) }
        content.addView(status)
        content.addView(button(R.string.back_chat).apply {
            setOnClickListener { loadChat(profile, other.email) }
        })
        display(content)
        appApi.resolveCallRoom(other.email, callType).whenComplete { room, failure -> mainHandler.post {
            if (isDestroyed) return@post
            when {
                failure != null -> status.text = readableFailure(failure)
                !BuildConfig.WEBRTC_ARTIFACT_PRESENT -> status.setText(R.string.webrtc_artifact_required)
                else -> status.text = getString(R.string.call_room_ready_runtime_pending, room.callId.take(12))
            }
        } }
    }

    private fun messageBubble(message: ChatMessage): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(16), dp(10), dp(16), dp(10))
        gravity = if (message.mine) Gravity.END else Gravity.START
        background = GradientDrawable().apply {
            setColor(color(if (message.mine) R.color.app_message_sent else R.color.app_surface_variant))
            cornerRadius = dp(16).toFloat()
        }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        ).apply {
            setMargins(if (message.mine) dp(40) else 0, dp(5), if (message.mine) 0 else dp(40), dp(5))
        }
        addView(TextView(context).apply {
            text = if (message.text.isNotEmpty()) message.text else getString(R.string.media_message)
            textSize = 16f
        })
        if (message.translatedText.isNotEmpty()) addView(TextView(context).apply {
            text = getString(R.string.translated_message, message.translationLanguage, message.translatedText)
            setPadding(0, dp(6), 0, 0)
        })
        if (message.time.isNotEmpty()) addView(TextView(context).apply { text = message.time; textSize = 11f })
    }

    private fun showProfileEditor(profile: AppProfile) {
        currentPrimarySection = "home"
        currentNestedScreen = "profile_editor"
        val content = form(R.string.edit_profile)
        val initial = ProfileDraftMemory.read(profile.email) ?: ProfileDraft(
            profile.bio,
            profile.profession,
            profile.lookingFor,
            profile.goals.joinToString(", "),
            profile.interests.joinToString(", "),
            profile.skills.joinToString(", "),
            profile.languages.joinToString(", "),
        )
        val bio = multiLineField(R.string.bio_hint, initial.bio)
        val profession = field(R.string.profession_hint).apply { setText(initial.profession) }
        val lookingFor = field(R.string.looking_for_hint).apply { setText(initial.lookingFor) }
        val goals = field(R.string.goals_hint).apply { setText(initial.goals) }
        val interests = field(R.string.interests_hint).apply { setText(initial.interests) }
        val skills = field(R.string.skills_hint).apply { setText(initial.skills) }
        val languages = field(R.string.languages_hint).apply { setText(initial.languages) }
        val save = button(R.string.save_profile)
        val cancel = button(R.string.cancel)
        val status = statusView()
        listOf(bio, profession, lookingFor, goals, interests, skills, languages, save, cancel, status)
            .forEach(content::addView)
        val rememberDraft = {
            ProfileDraftMemory.write(
                profile.email,
                ProfileDraft(
                    bio.text.toString(), profession.text.toString(), lookingFor.text.toString(),
                    goals.text.toString(), interests.text.toString(), skills.text.toString(), languages.text.toString(),
                ),
            )
        }
        watchChanges(listOf(bio, profession, lookingFor, goals, interests, skills, languages), rememberDraft)
        cancel.setOnClickListener {
            ProfileDraftMemory.clear(profile.email)
            showHome(profile)
        }
        save.setOnClickListener {
            val update = ProfileUpdate(
                bio.text.toString(), profession.text.toString(), lookingFor.text.toString(), goals.text.toString(),
                interests.text.toString(), skills.text.toString(), languages.text.toString(),
            )
            save.isEnabled = false; cancel.isEnabled = false; status.setText(R.string.working)
            runCatching { appApi.updateProfile(update) }.onSuccess { future ->
                future.whenComplete { updated, failure -> mainHandler.post {
                    if (isDestroyed) return@post
                    save.isEnabled = true; cancel.isEnabled = true
                    if (failure == null) {
                        ProfileDraftMemory.clear(profile.email)
                        showHome(updated)
                    } else status.text = readableFailure(failure)
                } }
            }.onFailure {
                save.isEnabled = true; cancel.isEnabled = true; status.text = readableFailure(it)
            }
        }
        display(content)
    }

    private fun watchChanges(fields: List<EditText>, changed: () -> Unit) {
        fields.forEach { field ->
            field.addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(value: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(value: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(value: Editable?) = changed()
            })
        }
    }

    private fun readableFailure(failure: Throwable): String {
        val mapped = UserFacingFailureMapper.map(failure)
        return mapped.validationMessage ?: getString(when (mapped.kind) {
            FailureKind.OFFLINE -> R.string.error_offline
            FailureKind.TIMEOUT -> R.string.error_timeout
            FailureKind.SESSION_EXPIRED -> R.string.error_session_expired
            FailureKind.SERVICE_UNAVAILABLE -> R.string.error_service_unavailable
            FailureKind.INVALID_INPUT -> R.string.error_invalid_input
            FailureKind.GENERIC -> R.string.request_failed
        })
    }

    private fun form(title: Int) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(28), dp(20), dp(24))
        addView(TextView(context).apply {
            setText(title); textSize = 28f; gravity = Gravity.CENTER
            ViewCompat.setAccessibilityHeading(this, true)
        })
    }

    private fun formText(title: String) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(28), dp(20), dp(24))
        addView(TextView(context).apply {
            text = title; textSize = 28f; gravity = Gravity.CENTER
            ViewCompat.setAccessibilityHeading(this, true)
        })
    }

    private fun field(hint: Int, type: Int = InputType.TYPE_CLASS_TEXT) = EditText(this).apply {
        setHint(hint); inputType = type; maxLines = 1; minHeight = dp(48)
    }

    private fun passwordField() = field(
        R.string.password_hint,
        InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD,
    )

    private fun multiLineField(hint: Int, value: String) = EditText(this).apply {
        setHint(hint)
        setText(value)
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        minLines = 3
        maxLines = 6
    }

    private fun button(label: Int) = Button(this).apply { setText(label); minHeight = dp(48) }
    private fun buttonText(label: String) = Button(this).apply { text = label; isAllCaps = false; minHeight = dp(48) }
    private fun statusView() = TextView(this).apply {
        gravity = Gravity.CENTER
        visibility = View.VISIBLE
        accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
    }
    private fun display(content: LinearLayout) {
        cancelImageLoads()
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(content) }
        applySystemInsets(scroll)
        setContentView(scroll)
    }

    private fun displayMain(
        content: LinearLayout,
        profile: AppProfile,
        selected: String,
        nestedScreen: String = "none",
    ) {
        cancelImageLoads()
        require(selected in PRIMARY_SECTIONS)
        require(nestedScreen in RESTORABLE_NESTED_SCREENS)
        currentPrimarySection = selected
        currentNestedScreen = nestedScreen
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(color(R.color.app_background))
        }
        applySystemInsets(root)
        root.addView(ScrollView(this).apply {
            isFillViewport = true
            addView(content)
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        val navigation = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(6), dp(4), dp(6), dp(4))
            elevation = dp(8).toFloat()
            setBackgroundColor(color(R.color.app_surface))
        }
        listOf(
            PrimaryNavItem("home", R.string.nav_home, R.drawable.ic_nav_home) { showHome(profile) },
            PrimaryNavItem("matches", R.string.nav_matches, R.drawable.ic_nav_ai) { loadMatches(profile) },
            PrimaryNavItem("feed", R.string.nav_feed, R.drawable.ic_nav_feed) { loadFeed(profile) },
            PrimaryNavItem("messages", R.string.nav_messages, R.drawable.ic_nav_messages) { loadChats(profile) },
        ).forEach { item ->
            navigation.addView(button(item.label).apply {
                isAllCaps = false
                minHeight = dp(48)
                textSize = 11f
                compoundDrawablePadding = dp(2)
                setCompoundDrawablesRelativeWithIntrinsicBounds(0, item.icon, 0, 0)
                setTextColor(color(if (item.key == selected) R.color.app_primary else R.color.app_nav_inactive))
                compoundDrawablesRelative.filterNotNull().forEach { drawable ->
                    drawable.setTint(color(if (item.key == selected) R.color.app_primary else R.color.app_nav_inactive))
                }
                background = GradientDrawable().apply {
                    setColor(color(if (item.key == selected) R.color.app_primary_container else R.color.app_transparent))
                    cornerRadius = dp(14).toFloat()
                }
                contentDescription = getString(item.label)
                isSelected = item.key == selected
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
                setOnClickListener { if (item.key != selected) item.action() }
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        root.addView(navigation, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setContentView(root)
    }

    private fun cancelImageLoads() {
        imageLoads.toList().forEach { it.cancel(true) }
        imageLoads.clear()
        displayedBitmaps.forEach { if (!it.isRecycled) it.recycle() }
        displayedBitmaps.clear()
    }

    private fun runWhenVisible(view: View, action: () -> Unit) {
        var started = false
        lateinit var scrollListener: ViewTreeObserver.OnScrollChangedListener
        lateinit var attachListener: View.OnAttachStateChangeListener
        fun removeObserver() {
            if (view.viewTreeObserver.isAlive) view.viewTreeObserver.removeOnScrollChangedListener(scrollListener)
        }
        fun checkVisibility() {
            val visibleBounds = Rect()
            if (!started && view.isAttachedToWindow && view.getGlobalVisibleRect(visibleBounds) && visibleBounds.height() > 0) {
                started = true
                removeObserver()
                view.removeOnAttachStateChangeListener(attachListener)
                action()
            }
        }
        scrollListener = ViewTreeObserver.OnScrollChangedListener(::checkVisibility)
        attachListener = object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(attached: View) {
                attached.viewTreeObserver.addOnScrollChangedListener(scrollListener)
                attached.post(::checkVisibility)
            }

            override fun onViewDetachedFromWindow(detached: View) {
                removeObserver()
            }
        }
        view.addOnAttachStateChangeListener(attachListener)
        if (view.isAttachedToWindow) attachListener.onViewAttachedToWindow(view)
    }

    private fun applySystemInsets(view: View) {
        val initialLeft = view.paddingLeft
        val initialTop = view.paddingTop
        val initialRight = view.paddingRight
        val initialBottom = view.paddingBottom
        ViewCompat.setOnApplyWindowInsetsListener(view) { target, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            target.setPadding(
                initialLeft + bars.left,
                initialTop + bars.top,
                initialRight + bars.right,
                initialBottom + bars.bottom,
            )
            insets
        }
        ViewCompat.requestApplyInsets(view)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density + 0.5f).toInt()
    private fun color(resource: Int): Int = ContextCompat.getColor(this, resource)

    private companion object {
        const val NOTIFICATION_PERMISSION_REQUEST = 4101
        const val PRIMARY_SECTION_STATE = "primary_section"
        const val NESTED_SCREEN_STATE = "nested_screen"
        val PRIMARY_SECTIONS = setOf("home", "matches", "feed", "messages")
        val RESTORABLE_NESTED_SCREENS = setOf(
            "none", "social_followers", "social_following", "notifications", "profile_editor",
        )
    }
}
