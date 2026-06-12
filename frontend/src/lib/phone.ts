/**
 * Phone-input mask helpers for Kazakhstan/Russia format: +7 (XXX) XXX-XX-XX.
 * The leading "+7 (" is locked; users type the 10 trailing digits.
 */

const MAX_DIGITS = 10

/** Extract the 10 user-entered digits from any input string. */
export function extractDigits(input: string): string {
  // Drop the locked country code so the leading "7" from "+7 (" doesn't
  // count as a typed digit.
  let body: string
  if (input.startsWith('+7')) {
    body = input.slice(2)
  } else if (input.startsWith('8')) {
    body = input.slice(1)
  } else {
    body = input
  }
  let digits = body.replace(/\D+/g, '')
  // Pasted unformatted "77077880094" — drop the leading 7
  if (digits.length === 11 && digits.startsWith('7')) {
    digits = digits.slice(1)
  }
  return digits.slice(0, MAX_DIGITS)
}

/** Render the input value from raw digits, with auto-advancing separators. */
export function formatPhone(digits: string): string {
  const d = digits.replace(/\D+/g, '').slice(0, MAX_DIGITS)
  let out = '+7 ('
  if (d.length === 0) return out
  out += d.slice(0, Math.min(3, d.length))
  if (d.length < 3) return out
  out += ') '
  if (d.length === 3) return out
  out += d.slice(3, Math.min(6, d.length))
  if (d.length < 6) return out
  out += '-'
  if (d.length === 6) return out
  out += d.slice(6, Math.min(8, d.length))
  if (d.length < 8) return out
  out += '-'
  if (d.length === 8) return out
  out += d.slice(8, 10)
  return out
}

export function isPhoneComplete(digits: string): boolean {
  return digits.length === MAX_DIGITS
}

/** Normalize any input to digits-only "7XXXXXXXXXX" for the backend. */
export function toBackendPhone(input: string): string {
  const d = extractDigits(input)
  return d ? '7' + d : ''
}

export const PHONE_PLACEHOLDER = '+7 (___) ___-__-__'
