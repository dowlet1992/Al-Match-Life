package com.almatchlife.app

import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ProfileDraftMemoryTest {
    private val draft = ProfileDraft("bio", "profession", "looking", "goals", "interests", "skills", "languages")

    @AfterTest
    fun reset() = ProfileDraftMemory.clear()

    @Test
    fun draftIsOwnerBoundAndOwnerComparisonIsNormalized() {
        ProfileDraftMemory.write(" USER@Example.com ", draft)

        assertEquals(draft, ProfileDraftMemory.read("user@example.com"))
        assertNull(ProfileDraftMemory.read("other@example.com"))
    }

    @Test
    fun scopedClearCannotDeleteAnotherOwnersDraft() {
        ProfileDraftMemory.write("user@example.com", draft)

        ProfileDraftMemory.clear("other@example.com")
        assertEquals(draft, ProfileDraftMemory.read("user@example.com"))
        ProfileDraftMemory.clear("user@example.com")
        assertNull(ProfileDraftMemory.read("user@example.com"))
    }
}
