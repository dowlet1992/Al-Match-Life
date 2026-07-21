package com.almatchlife.core.android

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Person
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Build
import com.almatchlife.core.PushEventType
import com.almatchlife.core.VoipCallPayload

@SuppressLint("ApplySharedPref", "UseKtx") // Durable dedupe must finish before notification delivery.
class IncomingCallNotifier(
    private val context: Context,
    private val notificationManager: NotificationManager,
    private val smallIcon: Int,
    private val actionReceiver: ComponentName,
    private val callActivity: ComponentName,
    private val ledger: SharedPreferences,
) {
    fun receive(payload: VoipCallPayload): Boolean {
        if (payload.eventType == PushEventType.CALL_CANCELLED) {
            ledger.edit().remove(ledgerKey(payload)).commit()
            notificationManager.cancel(notificationId(payload))
            return false
        }
        if (ledger.contains(ledgerKey(payload))) return false
        if (!ledger.edit().putString(ledgerKey(payload), payload.eventId).commit()) return false
        try {
            ensureChannel()
            notificationManager.notify(notificationId(payload), buildIncoming(payload))
        } catch (failure: RuntimeException) {
            ledger.edit().remove(ledgerKey(payload)).commit()
            throw failure
        }
        return true
    }

    fun clear(payload: VoipCallPayload) {
        ledger.edit().remove(ledgerKey(payload)).commit()
        notificationManager.cancel(notificationId(payload))
    }

    private fun buildIncoming(payload: VoipCallPayload): Notification {
        val answer = actionIntent("com.almatchlife.call.ANSWER", payload, 1)
        val decline = actionIntent("com.almatchlife.call.DECLINE", payload, 2)
        val content = activityIntent(payload, 3)
        val builder = Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(smallIcon)
            .setCategory(Notification.CATEGORY_CALL)
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .setContentTitle("Incoming Al Match Life call")
            .setContentText("Open the app to view caller details")
            .setContentIntent(content)
            .setOngoing(true)
            .setAutoCancel(false)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val caller = Person.Builder().setName("Al Match Life").setImportant(true).build()
            builder.setStyle(Notification.CallStyle.forIncomingCall(caller, decline, answer))
        } else {
            addLegacyActions(builder, decline, answer)
        }
        if (canUseFullScreenIntent()) builder.setFullScreenIntent(content, true)
        return builder.build()
    }

    @Suppress("DEPRECATION")
    private fun addLegacyActions(builder: Notification.Builder, decline: PendingIntent, answer: PendingIntent) {
        builder.setPriority(Notification.PRIORITY_MAX)
            .addAction(Notification.Action.Builder(0, "Decline", decline).build())
            .addAction(Notification.Action.Builder(0, "Answer", answer).build())
    }

    private fun canUseFullScreenIntent(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE || notificationManager.canUseFullScreenIntent()

    private fun actionIntent(action: String, payload: VoipCallPayload, offset: Int): PendingIntent {
        val intent = Intent(action).setComponent(actionReceiver)
            .setPackage(context.packageName)
            .putExtra("call_id", payload.callId)
            .putExtra("call_type", payload.callType.wireValue)
            .putExtra("call_event_id", payload.eventId)
        return PendingIntent.getBroadcast(
            context, notificationId(payload) + offset, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun activityIntent(payload: VoipCallPayload, offset: Int): PendingIntent {
        val intent = Intent().setComponent(callActivity).setPackage(context.packageName)
            .putExtra("call_id", payload.callId)
            .putExtra("call_type", payload.callType.wireValue)
            .putExtra("call_event_id", payload.eventId)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        return PendingIntent.getActivity(
            context, notificationId(payload) + offset, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun ensureChannel() {
        notificationManager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Incoming calls", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Incoming Al Match Life audio and video calls"
                lockscreenVisibility = Notification.VISIBILITY_PRIVATE
            },
        )
    }

    private fun notificationId(payload: VoipCallPayload): Int = payload.stableUuid.hashCode()
    private fun ledgerKey(payload: VoipCallPayload): String = "active_${payload.stableUuid}"

    private companion object { const val CHANNEL_ID = "incoming_calls_v1" }
}
