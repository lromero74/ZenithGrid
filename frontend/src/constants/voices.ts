export interface TTSVoice {
  id: string
  name: string
  gender: 'Female' | 'Male'
  locale: string
  style?: string
  desc?: string
  child?: boolean  // True for child/minor voices (content filtering)
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
  { id: 'ana', name: 'Ana', gender: 'Female', locale: 'US', child: true },
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
  { id: 'maisie', name: 'Maisie', gender: 'Female', locale: 'UK', child: true },
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

// Child voice IDs — used for adult content filtering
export const CHILD_VOICE_IDS: Set<string> = new Set(
  TTS_VOICES.filter(v => v.child).map(v => v.id)
)

// Keywords that flag content as unsuitable for child voices (case-insensitive).
// Errs on the side of caution — a false positive just means an adult voice reads it instead.
export const ADULT_CONTENT_KEYWORDS: string[] = [
  // Sexual content
  'sexual', 'sexuality', 'sexually', 'sex worker',
  'intercourse', 'orgasm', 'erotic', 'erotica',
  'seduction', 'seduce', 'foreplay', 'kink', 'kinky', 'fetish',
  'arousal', 'aroused', 'libido', 'pleasure',
  'pornography', 'pornographic', 'porn',
  'prostitution', 'prostitute', 'escort service',
  'strip club', 'stripper', 'lap dance',
  'rape', 'raped', 'rapist', 'raping',
  'sexual assault', 'sexually assaulted',
  'molestation', 'molested', 'molester',
  'pedophile', 'paedophile', 'pedophilia',
  'trafficking', 'sex trafficking',
  'transsexual', 'transexual',

  // Guns and weapons
  'firearm', 'firearms', 'handgun', 'pistol', 'revolver',
  'rifle', 'shotgun', 'assault rifle', 'semi-automatic',
  'ammunition', 'ammo', 'bullet', 'bullets',
  'gunshot', 'gunfire', 'shooter', 'gunman',
  'mass shooting', 'school shooting',

  // Alcohol
  'alcohol', 'alcoholic', 'alcoholism',
  'drunk', 'drunken', 'intoxicated', 'intoxication',
  'beer', 'whiskey', 'vodka', 'tequila', 'rum',
  'cocktail', 'liquor', 'wine',
  'binge drinking', 'hangover',
  'brewery', 'distillery', 'bartender',

  // Smoking and tobacco
  'smoking', 'cigarette', 'cigarettes', 'tobacco',
  'vaping', 'vape', 'e-cigarette', 'nicotine',
  'cigar', 'cigars',

  // Drugs
  'cocaine', 'heroin', 'methamphetamine', 'meth',
  'fentanyl', 'opioid', 'opioids', 'opiate',
  'marijuana', 'cannabis', 'weed',
  'ecstasy', 'mdma', 'lsd', 'psychedelic',
  'drug abuse', 'drug addict', 'drug addiction',
  'overdose', 'overdosed',
  'drug dealer', 'drug trafficking', 'cartel',
  'narcotics', 'narcotic',

  // Violence
  'murder', 'murdered', 'murderer', 'murders',
  'homicide', 'manslaughter', 'infanticide',
  'serial killer', 'assassination', 'assassinated',
  'genocide', 'ethnic cleansing',
  'torture', 'tortured',
  'dismember', 'dismembered', 'dismemberment',
  'decapitate', 'decapitated', 'beheading',
  'suicide bombing', 'suicide bomber',
  'stabbing', 'stabbed to death',
  'child abuse', 'domestic violence',
  'violent crime', 'violent attack',
  'bloodshed', 'bloodbath', 'massacre',
  'bombing', 'terrorist', 'terrorism',
  'hostage', 'kidnapping', 'kidnapped',
  'beating', 'beaten to death',
  'arson', 'arsonist',
]

// Precompiled regex for efficient matching
const _adultPattern = new RegExp(
  '\\b(' + ADULT_CONTENT_KEYWORDS.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\b',
  'i'
)

/** Returns true if text contains adult content keywords */
export function containsAdultContent(text: string): boolean {
  return _adultPattern.test(text)
}
