export interface TTSVoice {
  id: string
  name: string
  gender: 'Female' | 'Male'
  locale: string
  style?: string
  desc?: string
}

export const TTS_VOICES: TTSVoice[] = [
  // US voices
  { id: 'aria', name: 'Aria', gender: 'Female', locale: 'US', style: 'News', desc: 'Clear' },
  { id: 'guy', name: 'Guy', gender: 'Male', locale: 'US', style: 'News', desc: 'Authoritative' },
  { id: 'jenny', name: 'Jenny', gender: 'Female', locale: 'US', style: 'General', desc: 'Friendly' },
  { id: 'brian', name: 'Brian', gender: 'Male', locale: 'US', style: 'Casual', desc: 'Approachable' },
  { id: 'emma', name: 'Emma', gender: 'Female', locale: 'US', style: 'Casual', desc: 'Cheerful' },
  { id: 'andrew', name: 'Andrew', gender: 'Male', locale: 'US', style: 'Casual', desc: 'Warm' },
  { id: 'ava', name: 'Ava', gender: 'Female', locale: 'US' },
  { id: 'ana', name: 'Ana', gender: 'Female', locale: 'US' },
  { id: 'christopher', name: 'Christopher', gender: 'Male', locale: 'US' },
  { id: 'eric', name: 'Eric', gender: 'Male', locale: 'US' },
  { id: 'michelle', name: 'Michelle', gender: 'Female', locale: 'US' },
  { id: 'roger', name: 'Roger', gender: 'Male', locale: 'US' },
  { id: 'steffan', name: 'Steffan', gender: 'Male', locale: 'US' },
  // British voices
  { id: 'libby', name: 'Libby', gender: 'Female', locale: 'UK' },
  { id: 'sonia', name: 'Sonia', gender: 'Female', locale: 'UK' },
  { id: 'ryan', name: 'Ryan', gender: 'Male', locale: 'UK' },
  { id: 'thomas', name: 'Thomas', gender: 'Male', locale: 'UK' },
  { id: 'maisie', name: 'Maisie', gender: 'Female', locale: 'UK' },
  // Australian voices
  { id: 'natasha', name: 'Natasha', gender: 'Female', locale: 'AU' },
  { id: 'william', name: 'William', gender: 'Male', locale: 'AU' },
  // Canadian voices
  { id: 'clara', name: 'Clara', gender: 'Female', locale: 'CA' },
  { id: 'liam', name: 'Liam', gender: 'Male', locale: 'CA' },
  // Irish voices
  { id: 'connor', name: 'Connor', gender: 'Male', locale: 'IE' },
  { id: 'emily', name: 'Emily', gender: 'Female', locale: 'IE' },
  // Indian English voices
  { id: 'neerja', name: 'Neerja', gender: 'Female', locale: 'IN' },
  { id: 'prabhat', name: 'Prabhat', gender: 'Male', locale: 'IN' },
  // New Zealand voices
  { id: 'mitchell', name: 'Mitchell', gender: 'Male', locale: 'NZ' },
  { id: 'molly', name: 'Molly', gender: 'Female', locale: 'NZ' },
  // South African voices
  { id: 'leah', name: 'Leah', gender: 'Female', locale: 'ZA' },
  { id: 'luke', name: 'Luke', gender: 'Male', locale: 'ZA' },
  // Singapore voices
  { id: 'luna', name: 'Luna', gender: 'Female', locale: 'SG' },
  { id: 'wayne', name: 'Wayne', gender: 'Male', locale: 'SG' },
  // Hong Kong voices
  { id: 'sam', name: 'Sam', gender: 'Male', locale: 'HK' },
  { id: 'yan', name: 'Yan', gender: 'Female', locale: 'HK' },
  // Kenya voices
  { id: 'asilia', name: 'Asilia', gender: 'Female', locale: 'KE' },
  { id: 'chilemba', name: 'Chilemba', gender: 'Male', locale: 'KE' },
  // Nigeria voices
  { id: 'abeo', name: 'Abeo', gender: 'Male', locale: 'NG' },
  { id: 'ezinne', name: 'Ezinne', gender: 'Female', locale: 'NG' },
  // Philippines voices
  { id: 'james', name: 'James', gender: 'Male', locale: 'PH' },
  { id: 'rosa', name: 'Rosa', gender: 'Female', locale: 'PH' },
  // Tanzania voices
  { id: 'elimu', name: 'Elimu', gender: 'Male', locale: 'TZ' },
  { id: 'imani', name: 'Imani', gender: 'Female', locale: 'TZ' },
]

export const TTS_VOICES_BY_ID: Record<string, TTSVoice> = Object.fromEntries(
  TTS_VOICES.map(v => [v.id, v])
)

export const VOICE_CYCLE_IDS: string[] = TTS_VOICES
  .filter(v => ['US', 'UK', 'AU', 'CA', 'IE', 'IN', 'NZ', 'ZA'].includes(v.locale))
  .map(v => v.id)
