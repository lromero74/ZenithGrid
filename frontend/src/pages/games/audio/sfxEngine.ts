/**
 * SFXEngine — Procedural sound effects synthesizer using Web Audio API.
 *
 * Provides synthesis primitives (noise bursts, tone pulses, pitch sweeps,
 * FM tones, filtered noise) that effect recipes compose into game SFX.
 * Each play has natural random variation so no two plays sound identical.
 *
 * Shares AudioContext with the music SynthEngine (or creates its own).
 */

interface ADSR {
  attack: number
  decay: number
  sustain: number  // 0–1 level
  release: number
}

const DEFAULT_ADSR: ADSR = { attack: 0.005, decay: 0.03, sustain: 0.6, release: 0.05 }

export class SFXEngine {
  private ctx: AudioContext | null = null
  private masterGain: GainNode | null = null
  private noiseBuffer: AudioBuffer | null = null
  private volume = 0.5
  private muted = false
  private ownsContext = false

  // ---- Lifecycle ----

  /** Initialize. Accepts a shared AudioContext (from music engine) or creates its own. */
  init(sharedCtx?: AudioContext): void {
    if (this.ctx) return

    if (sharedCtx) {
      this.ctx = sharedCtx
      this.ownsContext = false
    } else {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      this.ctx = new AC()
      this.ctx.resume()
      this.ownsContext = true
    }

    this.masterGain = this.ctx.createGain()
    this.masterGain.gain.value = this.muted ? 0 : this.volume
    this.masterGain.connect(this.ctx.destination)
    this.noiseBuffer = this.createNoiseBuffer()
  }

  /** Set SFX volume 0–1 (independent from music). */
  setVolume(vol: number): void {
    this.volume = Math.max(0, Math.min(1, vol))
    if (this.masterGain && !this.muted) {
      this.masterGain.gain.value = this.volume
    }
  }

  /** Mute/unmute SFX. */
  setMuted(muted: boolean): void {
    this.muted = muted
    if (this.masterGain) {
      this.masterGain.gain.value = muted ? 0 : this.volume
    }
  }

  /** Get current AudioContext time. */
  getTime(): number {
    return this.ctx?.currentTime ?? 0
  }

  /** Dispose — close context (only if we own it) and clean up. */
  dispose(): void {
    this.masterGain?.disconnect()
    if (this.ownsContext) {
      this.ctx?.close()
    }
    this.ctx = null
    this.masterGain = null
    this.noiseBuffer = null
  }

  // ---- Variation helper (static for testability) ----

  /**
   * Apply jitter to a base value.
   * variation: 0–1 random value. pct: max deviation as fraction (0.1 = ±10%).
   */
  static jitter(base: number, variation: number, pct: number): number {
    return base * (1 + (variation - 0.5) * 2 * pct)
  }

  // ---- Synthesis Primitives ----

  /**
   * Filtered noise burst — clicks, rain drops, impacts.
   * Routes: BufferSource → BiquadFilter → GainNode (envelope) → master
   */
  noiseBurst(
    time: number, dur: number, filterType: BiquadFilterType,
    freq: number, Q: number, gain: number,
    filterEndFreq?: number,
  ): void {
    if (!this.ctx || !this.masterGain || !this.noiseBuffer) return

    const src = this.ctx.createBufferSource()
    src.buffer = this.noiseBuffer

    const filter = this.ctx.createBiquadFilter()
    filter.type = filterType
    filter.frequency.setValueAtTime(freq, time)
    filter.Q.value = Q

    if (filterEndFreq !== undefined) {
      filter.frequency.linearRampToValueAtTime(filterEndFreq, time + dur)
    }

    const env = this.ctx.createGain()
    env.gain.setValueAtTime(gain, time)
    env.gain.exponentialRampToValueAtTime(0.001, time + dur)

    src.connect(filter)
    filter.connect(env)
    env.connect(this.masterGain)

    src.start(time)
    src.stop(time + dur + 0.01)
  }

  /**
   * Tonal pulse — beeps, chimes, tonal hits.
   * Routes: Oscillator → GainNode (ADSR) → master
   */
  tonePulse(
    time: number, freq: number, dur: number, oscType: OscillatorType,
    gain: number, adsr?: ADSR,
  ): void {
    if (!this.ctx || !this.masterGain) return

    const a = adsr ?? DEFAULT_ADSR
    const osc = this.ctx.createOscillator()
    osc.type = oscType
    osc.frequency.value = freq

    const env = this.ctx.createGain()
    env.gain.setValueAtTime(0, time)
    env.gain.linearRampToValueAtTime(gain, time + a.attack)
    env.gain.linearRampToValueAtTime(gain * a.sustain, time + a.attack + a.decay)

    const releaseStart = time + dur - a.release
    if (releaseStart > time + a.attack + a.decay) {
      env.gain.setValueAtTime(gain * a.sustain, releaseStart)
    }
    env.gain.linearRampToValueAtTime(0.001, time + dur)

    osc.connect(env)
    env.connect(this.masterGain)
    osc.start(time)
    osc.stop(time + dur + 0.01)
  }

  /**
   * Pitch sweep — frequency glide (laser, jump sounds).
   * Routes: Oscillator (freq ramp) → GainNode (envelope) → master
   */
  pitchSweep(
    time: number, freqStart: number, freqEnd: number, dur: number,
    oscType: OscillatorType, gain: number,
  ): void {
    if (!this.ctx || !this.masterGain) return

    const osc = this.ctx.createOscillator()
    osc.type = oscType
    osc.frequency.setValueAtTime(freqStart, time)
    osc.frequency.linearRampToValueAtTime(freqEnd, time + dur)

    const env = this.ctx.createGain()
    env.gain.setValueAtTime(gain, time)
    env.gain.exponentialRampToValueAtTime(0.001, time + dur)

    osc.connect(env)
    env.connect(this.masterGain)
    osc.start(time)
    osc.stop(time + dur + 0.01)
  }

  /**
   * FM synthesis tone — bells, metallic sounds.
   * Routes: ModOsc → DepthGain → Carrier.frequency, Carrier → GainNode → master
   */
  fmTone(
    time: number, carrierFreq: number, modRatio: number, modDepth: number,
    dur: number, gain: number,
  ): void {
    if (!this.ctx || !this.masterGain) return

    const modFreq = carrierFreq * modRatio

    // Modulator
    const mod = this.ctx.createOscillator()
    mod.type = 'sine'
    mod.frequency.value = modFreq
    const modGain = this.ctx.createGain()
    modGain.gain.value = modDepth

    // Carrier
    const carrier = this.ctx.createOscillator()
    carrier.type = 'sine'
    carrier.frequency.value = carrierFreq

    // FM routing: mod → modGain → carrier.frequency
    mod.connect(modGain)
    modGain.connect(carrier.frequency)

    // Envelope
    const env = this.ctx.createGain()
    env.gain.setValueAtTime(gain, time)
    env.gain.exponentialRampToValueAtTime(0.001, time + dur)

    carrier.connect(env)
    env.connect(this.masterGain)

    mod.start(time)
    carrier.start(time)
    mod.stop(time + dur + 0.01)
    carrier.stop(time + dur + 0.01)
  }

  /**
   * Sustained filtered noise — wind, rain, water ambience.
   * Routes: BufferSource (loop) → BiquadFilter (optional LFO) → GainNode → master
   */
  filteredNoise(
    time: number, dur: number, filterType: BiquadFilterType,
    freq: number, Q: number, gain: number,
    lfoRate?: number, lfoDepth?: number,
  ): GainNode | null {
    if (!this.ctx || !this.masterGain || !this.noiseBuffer) return null

    const src = this.ctx.createBufferSource()
    src.buffer = this.noiseBuffer
    src.loop = true

    const filter = this.ctx.createBiquadFilter()
    filter.type = filterType
    filter.frequency.value = freq
    filter.Q.value = Q

    // Optional LFO on filter frequency
    if (lfoRate && lfoDepth) {
      const lfo = this.ctx.createOscillator()
      lfo.type = 'sine'
      lfo.frequency.value = lfoRate
      const lfoGain = this.ctx.createGain()
      lfoGain.gain.value = lfoDepth
      lfo.connect(lfoGain)
      lfoGain.connect(filter.frequency)
      lfo.start(time)
      if (dur < 100) lfo.stop(time + dur + 0.01) // Don't stop ambient LFOs
    }

    const env = this.ctx.createGain()
    env.gain.setValueAtTime(gain, time)

    src.connect(filter)
    filter.connect(env)
    env.connect(this.masterGain)

    src.start(time)
    if (dur < 100) { // Finite duration
      env.gain.exponentialRampToValueAtTime(0.001, time + dur)
      src.stop(time + dur + 0.01)
    }

    return env // Return gain node so caller can stop ambient effects
  }

  // ---- Internal ----

  /** Pre-generate a 0.5s white noise buffer. */
  private createNoiseBuffer(): AudioBuffer {
    const ctx = this.ctx!
    const len = Math.floor(ctx.sampleRate * 0.5)
    const buffer = ctx.createBuffer(1, len, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < data.length; i++) {
      data[i] = Math.random() * 2 - 1
    }
    return buffer
  }
}
