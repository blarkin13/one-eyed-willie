package studio.oneeyedwillie.tv

import androidx.media3.common.PlaybackException

/** What the player should do after a playback error. */
internal enum class RecoveryAction {
    /** Prepare the same direct-play source again at the current position. */
    RETRY_SAME_SOURCE,
    /** Throw away the (probably expired) HLS session and start a new one here. */
    RESTART_HLS,
    /** The original cannot be played as-is; ask the server to transcode it. */
    FALLBACK_TO_HLS,
    GIVE_UP
}

/**
 * Chooses how to recover from a player error. Kept free of Android state so it
 * can be unit tested: a dropped connection or an expired transcoding session
 * must not end playback, but a file the decoder cannot handle should not be
 * retried forever either.
 */
internal object PlaybackRecovery {
    const val MAX_ATTEMPTS = 3

    private val transient = setOf(
        PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
        PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT,
        PlaybackException.ERROR_CODE_IO_UNSPECIFIED,
        PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS,
        PlaybackException.ERROR_CODE_IO_FILE_NOT_FOUND,
        PlaybackException.ERROR_CODE_IO_READ_POSITION_OUT_OF_RANGE,
        PlaybackException.ERROR_CODE_TIMEOUT,
        PlaybackException.ERROR_CODE_BEHIND_LIVE_WINDOW
    )

    fun isTransient(code: Int) = code in transient

    fun decide(code: Int, hlsMode: Boolean, attempts: Int, fallbackUsed: Boolean): RecoveryAction =
        when {
            isTransient(code) && hlsMode ->
                if (attempts < MAX_ATTEMPTS) RecoveryAction.RESTART_HLS else RecoveryAction.GIVE_UP
            isTransient(code) ->
                when {
                    attempts < MAX_ATTEMPTS -> RecoveryAction.RETRY_SAME_SOURCE
                    !fallbackUsed -> RecoveryAction.FALLBACK_TO_HLS
                    else -> RecoveryAction.GIVE_UP
                }
            // Decoder, format and parser failures: transcoding may help, retrying will not.
            !hlsMode && !fallbackUsed -> RecoveryAction.FALLBACK_TO_HLS
            else -> RecoveryAction.GIVE_UP
        }

    /** Wait a little longer after each failed attempt (1.5 s, 3 s, 4.5 s ...). */
    fun backoffMs(attempt: Int): Long = (1500L * attempt.coerceAtLeast(1)).coerceAtMost(6000L)
}

/** Playback quality choices; ids are the values the server accepts. */
internal object Quality {
    const val AUTO = "auto"
    /** Transcoding size used when the original cannot be played directly. */
    const val DEFAULT_TRANSCODE = "720p"

    data class Option(val id: String, val label: String)

    val options = listOf(
        Option(AUTO, "Auto (original when possible)"),
        Option("1080p", "1080p"),
        Option("720p", "720p"),
        Option("480p", "480p – saves bandwidth"),
        Option("360p", "360p – slowest connections")
    )

    fun normalize(id: String?): String = options.firstOrNull { it.id == id }?.id ?: AUTO

    fun label(id: String): String = options.first { it.id == normalize(id) }.label

    /** The `quality` query value to send when starting a transcode. */
    fun transcodeParam(id: String): String =
        if (normalize(id) == AUTO) DEFAULT_TRANSCODE else normalize(id)

    /** Whether this choice may play the original file directly. */
    fun allowsDirect(id: String) = normalize(id) == AUTO
}
