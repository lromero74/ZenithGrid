/**
 * MusicToggle — reusable mute/unmute buttons for game music and SFX.
 *
 * Used by all games that integrate the music engine via useGameMusic
 * and/or the SFX engine via useGameSFX.
 */

import { useState, useCallback } from 'react'
import { Music, Music2, Volume2, VolumeX } from 'lucide-react'
import type { GameMusicControls } from '../audio/useGameMusic'
import type { GameSFXControls } from '../audio/useGameSFX'

interface MusicToggleProps {
  music: GameMusicControls
  sfx?: GameSFXControls
}

export function MusicToggle({ music, sfx }: MusicToggleProps) {
  const [musicMuted, setMusicMuted] = useState(() => music.isMuted())
  const [sfxMuted, setSfxMuted] = useState(() => sfx?.isMuted() ?? false)

  const toggleMusic = useCallback(() => {
    music.init()
    const newMuted = music.toggleMute()
    setMusicMuted(newMuted)
  }, [music])

  const toggleSfx = useCallback(() => {
    if (!sfx) return
    sfx.init()
    const newMuted = sfx.toggleMute()
    setSfxMuted(newMuted)
  }, [sfx])

  const btnClass = (muted: boolean) =>
    `flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
      muted
        ? 'bg-slate-700/50 text-slate-400 border border-slate-600/30 hover:bg-slate-700'
        : 'bg-purple-600/20 text-purple-400 border border-purple-500/30'
    }`

  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={toggleMusic}
        className={btnClass(musicMuted)}
        title={musicMuted ? 'Unmute music' : 'Mute music'}
      >
        {musicMuted ? <Music2 className="w-3 h-3" /> : <Music className="w-3 h-3" />}
        Music
      </button>
      {sfx && (
        <button
          onClick={toggleSfx}
          className={btnClass(sfxMuted)}
          title={sfxMuted ? 'Unmute SFX' : 'Mute SFX'}
        >
          {sfxMuted ? <VolumeX className="w-3 h-3" /> : <Volume2 className="w-3 h-3" />}
          SFX
        </button>
      )}
    </div>
  )
}
