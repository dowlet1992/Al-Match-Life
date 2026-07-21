package com.almatchlife.app

/**
 * Process-private editor recovery. Draft text is deliberately never written to
 * a Bundle, preferences, logs, or disk. It survives Activity recreation only.
 */
internal data class ProfileDraft(
    val bio: String,
    val profession: String,
    val lookingFor: String,
    val goals: String,
    val interests: String,
    val skills: String,
    val languages: String,
)

internal object ProfileDraftMemory {
    private data class Entry(val owner: String, val draft: ProfileDraft)

    private var entry: Entry? = null

    @Synchronized
    fun read(ownerEmail: String): ProfileDraft? = entry
        ?.takeIf { it.owner == ownerEmail.normalizedOwner() }
        ?.draft

    @Synchronized
    fun write(ownerEmail: String, draft: ProfileDraft) {
        entry = Entry(ownerEmail.normalizedOwner(), draft)
    }

    @Synchronized
    fun clear(ownerEmail: String? = null) {
        if (ownerEmail == null || entry?.owner == ownerEmail.normalizedOwner()) entry = null
    }

    private fun String.normalizedOwner(): String = trim().lowercase()
}
