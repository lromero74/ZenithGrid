/**
 * SynthEngine — Web Audio API wrapper for real-time music synthesis.
 *
 * Provides oscillator channels with ADSR envelopes, synthesized drums,
 * and optional filter/delay effects. Game-agnostic.
 */

interface ChannelState {
  name: string
  type: OscillatorType | 'noise'
  gainNode: GainNode
  filterNode?: BiquadFilterNode
  delayNode?: DelayNode
  delayGain?: GainNode
  baseGain: number
}

// ADSR envelope times (seconds)
const ATTACK = 0.01
const DECAY = 0.05
const SUSTAIN_LEVEL = 0.7
const RELEASE = 0.08

/**
 * Web Audio synthesis engine. Create one per game, call init() from a user gesture.
 */
export class SynthEngine {
  private ctx: AudioContext | null = null
  private masterGain: GainNode | null = null
  private channels = new Map<string, ChannelState>()
  private noiseBuffer: AudioBuffer | null = null

  /** Initialize AudioContext. Must be called from a user gesture (click/tap) for iOS. */
  init(): void {
    if (this.ctx) return
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    this.ctx = new AC()
    // Resume immediately — must happen in user gesture context for iOS/Chrome
    this.ctx.resume()
    this.masterGain = this.ctx.createGain()
    this.masterGain.gain.value = 0.7
    this.masterGain.connect(this.ctx.destination)
    this.noiseBuffer = this.createNoiseBuffer()
  }

  /** Pre-generate a white noise buffer for drums. */
  private createNoiseBuffer(): AudioBuffer {
    const ctx = this.ctx!
    const buffer = ctx.createBuffer(1, ctx.sampleRate * 0.5, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < data.length; i++) {
      data[i] = Math.random() * 2 - 1
    }
    return buffer
  }

  /**
   * Create a named channel (instrument voice).
   * Call after init(). Effects are optional.
   */
  createChannel(
    name: string,
    type: OscillatorType | 'noise',
    gain: number,
    effects?: { filter?: number; delay?: number; delayFeedback?: number },
  ): void {
    if (!this.ctx || !this.masterGain) return

    const gainNode = this.ctx.createGain()
    gainNode.gain.value = gain

    let filterNode: BiquadFilterNode | undefined
    let delayNode: DelayNode | undefined
    let delayGain: GainNode | undefined

    // Build signal chain: gainNode → [filter] → [delay] → masterGain
    let output: AudioNode = this.masterGain

    if (effects?.delay) {
      delayNode = this.ctx.createDelay(1.0)
      delayNode.delayTime.value = effects.delay
      delayGain = this.ctx.createGain()
      delayGain.gain.value = effects.delayFeedback ?? 0.3
      // Delay feedback loop
      delayNode.connect(delayGain)
      delayGain.connect(delayNode)
      // Delay wet signal → master
      delayNode.connect(this.masterGain)
      // Dry signal will also go to master; delay taps off the chain
      output = this.masterGain
    }

    if (effects?.filter) {
      filterNode = this.ctx.createBiquadFilter()
      filterNode.type = 'lowpass'
      filterNode.frequency.value = effects.filter
      filterNode.Q.value = 2
      filterNode.connect(output)
      if (delayNode) gainNode.connect(delayNode)
      output = filterNode
    } else if (delayNode) {
      // No filter but has delay — connect gain to both master and delay
      gainNode.connect(delayNode)
    }

    gainNode.connect(output)

    this.channels.set(name, { name, type, gainNode, filterNode, delayNode, delayGain, baseGain: gain })
  }

  /**
   * Schedule a note on a channel.
   * @param channel - Channel name
   * @param freq - Frequency in Hz (0 = rest, skipped)
   * @param startTime - AudioContext time to start
   * @param duration - Duration in seconds
   * @param velocity - Volume 0–1 (default 0.8)
   */
  playNote(
    channel: string, freq: number, startTime: number, duration: number,
    velocity: number = 0.8,
    adsr?: { attack: number; decay: number; sustain: number; release: number },
  ): void {
    if (!this.ctx || freq <= 0) return
    const ch = this.channels.get(channel)
    if (!ch) return

    const osc = this.ctx.createOscillator()
    osc.type = ch.type === 'noise' ? 'square' : ch.type as OscillatorType
    osc.frequency.value = freq

    const env = this.ctx.createGain()
    env.gain.value = 0

    // ADSR envelope — use per-channel override or global defaults
    const a = adsr?.attack ?? ATTACK
    const d = adsr?.decay ?? DECAY
    const s = adsr?.sustain ?? SUSTAIN_LEVEL
    const r = adsr?.release ?? RELEASE

    const peak = velocity
    env.gain.setValueAtTime(0, startTime)
    env.gain.linearRampToValueAtTime(peak, startTime + a)
    env.gain.linearRampToValueAtTime(peak * s, startTime + a + d)
    // Hold sustain, then release
    const releaseStart = startTime + duration - r
    if (releaseStart > startTime + a + d) {
      env.gain.setValueAtTime(peak * s, releaseStart)
    }
    env.gain.linearRampToValueAtTime(0.001, startTime + duration)

    osc.connect(env)
    env.connect(ch.gainNode)

    osc.start(startTime)
    osc.stop(startTime + duration + 0.01)
  }

  /**
   * Play a synthesized drum hit.
   * @param type - 'kick' | 'snare' | 'hihat' | 'clap'
   * @param startTime - AudioContext time
   * @param velocity - Volume 0–1 (default 0.8)
   */
  playDrum(type: 'kick' | 'snare' | 'hihat' | 'clap', startTime: number, velocity: number = 0.8): void {
    if (!this.ctx || !this.masterGain) return

    switch (type) {
      case 'kick':
        this.playKick(startTime, velocity)
        break
      case 'snare':
        this.playSnare(startTime, velocity)
        break
      case 'hihat':
        this.playHiHat(startTime, velocity)
        break
      case 'clap':
        this.playClap(startTime, velocity)
        break
    }
  }

  /** Kick: sine 150→50Hz pitch drop + gain decay. */
  private playKick(time: number, vel: number): void {
    const ctx = this.ctx!
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(150, time)
    osc.frequency.exponentialRampToValueAtTime(50, time + 0.1)

    const gain = ctx.createGain()
    gain.gain.setValueAtTime(vel * 0.8, time)
    gain.gain.exponentialRampToValueAtTime(0.001, time + 0.3)

    osc.connect(gain)
    gain.connect(this.masterGain!)
    osc.start(time)
    osc.stop(time + 0.3)
  }

  /** Snare: triangle 200Hz + noise burst, bandpass filtered. */
  private playSnare(time: number, vel: number): void {
    const ctx = this.ctx!

    // Tonal body
    const osc = ctx.createOscillator()
    osc.type = 'triangle'
    osc.frequency.value = 200
    const oscGain = ctx.createGain()
    oscGain.gain.setValueAtTime(vel * 0.4, time)
    oscGain.gain.exponentialRampToValueAtTime(0.001, time + 0.12)
    osc.connect(oscGain)
    oscGain.connect(this.masterGain!)
    osc.start(time)
    osc.stop(time + 0.12)

    // Noise burst
    const noise = this.createNoiseSource()
    if (!noise) return
    const filter = ctx.createBiquadFilter()
    filter.type = 'bandpass'
    filter.frequency.value = 3000
    filter.Q.value = 0.5
    const noiseGain = ctx.createGain()
    noiseGain.gain.setValueAtTime(vel * 0.6, time)
    noiseGain.gain.exponentialRampToValueAtTime(0.001, time + 0.15)
    noise.connect(filter)
    filter.connect(noiseGain)
    noiseGain.connect(this.masterGain!)
    noise.start(time)
    noise.stop(time + 0.15)
  }

  /** Hi-hat: noise burst, highpass 8kHz, short decay. */
  private playHiHat(time: number, vel: number): void {
    const ctx = this.ctx!
    const noise = this.createNoiseSource()
    if (!noise) return

    const filter = ctx.createBiquadFilter()
    filter.type = 'highpass'
    filter.frequency.value = 8000
    const gain = ctx.createGain()
    gain.gain.setValueAtTime(vel * 0.3, time)
    gain.gain.exponentialRampToValueAtTime(0.001, time + 0.06)

    noise.connect(filter)
    filter.connect(gain)
    gain.connect(this.masterGain!)
    noise.start(time)
    noise.stop(time + 0.06)
  }

  /** Clap: noise burst with slight delay echo. */
  private playClap(time: number, vel: number): void {
    const ctx = this.ctx!

    // Two layered noise bursts for clap texture
    for (const offset of [0, 0.01]) {
      const noise = this.createNoiseSource()
      if (!noise) continue
      const filter = ctx.createBiquadFilter()
      filter.type = 'bandpass'
      filter.frequency.value = 2000
      filter.Q.value = 1
      const gain = ctx.createGain()
      gain.gain.setValueAtTime(vel * 0.5, time + offset)
      gain.gain.exponentialRampToValueAtTime(0.001, time + offset + 0.1)
      noise.connect(filter)
      filter.connect(gain)
      gain.connect(this.masterGain!)
      noise.start(time + offset)
      noise.stop(time + offset + 0.1)
    }
  }

  /** Create a BufferSource from the pre-generated noise buffer. */
  private createNoiseSource(): AudioBufferSourceNode | null {
    if (!this.ctx || !this.noiseBuffer) return null
    const src = this.ctx.createBufferSource()
    src.buffer = this.noiseBuffer
    return src
  }

  /** Set a channel's gain (for intensity transitions). */
  setChannelGain(name: string, gain: number): void {
    const ch = this.channels.get(name)
    if (!ch) return
    ch.gainNode.gain.value = gain
    ch.baseGain = gain
  }

  /** Set master output gain 0–1. */
  setMasterGain(gain: number): void {
    if (this.masterGain) this.masterGain.gain.value = gain
  }

  /**
   * Fade master gain to near-zero over durationMs.
   * Uses linearRampToValueAtTime for smooth transition.
   * @param durationMs - Fade duration in milliseconds
   * @param onComplete - Optional callback fired after fade completes
   */
  fadeOut(durationMs: number, onComplete?: () => void): void {
    if (!this.ctx || !this.masterGain) return

    const now = this.ctx.currentTime
    this.masterGain.gain.setValueAtTime(this.masterGain.gain.value, now)
    this.masterGain.gain.linearRampToValueAtTime(0.001, now + durationMs / 1000)

    if (onComplete) {
      setTimeout(onComplete, durationMs)
    }
  }

  /** Get current AudioContext time. */
  getTime(): number {
    return this.ctx?.currentTime ?? 0
  }

  /** Suspend AudioContext (pause processing). */
  async suspend(): Promise<void> {
    await this.ctx?.suspend()
  }

  /** Resume AudioContext. */
  async resume(): Promise<void> {
    await this.ctx?.resume()
  }

  /** Get the underlying AudioContext (for sharing with SFX engine). */
  getAudioContext(): AudioContext | null {
    return this.ctx
  }

  /** Dispose — close context and clear channels. */
  dispose(): void {
    this.channels.forEach(ch => {
      ch.gainNode.disconnect()
      ch.filterNode?.disconnect()
      ch.delayNode?.disconnect()
      ch.delayGain?.disconnect()
    })
    this.channels.clear()
    this.ctx?.close()
    this.ctx = null
    this.masterGain = null
  }
}
