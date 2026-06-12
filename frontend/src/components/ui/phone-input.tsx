import * as React from 'react'
import { Input } from '@/components/ui/input'
import { extractDigits, formatPhone, PHONE_PLACEHOLDER } from '@/lib/phone'

interface PhoneInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> {
  /** 10 digits after the locked "+7 (" prefix, or the full backend phone (with leading 7). */
  value: string
  /** Called with the 10 trailing digits ('' when cleared). */
  onChange: (digits: string) => void
}

/**
 * Controlled phone input with mask `+7 (XXX) XXX-XX-XX`.
 * Locks the country code: focus shows "+7 (" immediately and the user
 * only enters the 10 trailing digits.
 */
export const PhoneInput = React.forwardRef<HTMLInputElement, PhoneInputProps>(
  ({ value, onChange, onFocus, onBlur, placeholder, ...rest }, ref) => {
    // Normalize incoming value to the 10 digits the component manages.
    const digits = React.useMemo(() => extractDigits(value), [value])
    const [focused, setFocused] = React.useState(false)

    // Show empty (placeholder visible) until focused, then "+7 (" prefix.
    const display = digits.length > 0 || focused ? formatPhone(digits) : ''

    function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
      onChange(extractDigits(e.target.value))
    }

    return (
      <Input
        {...rest}
        ref={ref}
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        value={display}
        placeholder={placeholder ?? PHONE_PLACEHOLDER}
        onChange={handleChange}
        onFocus={(e) => {
          setFocused(true)
          onFocus?.(e)
        }}
        onBlur={(e) => {
          setFocused(false)
          onBlur?.(e)
        }}
      />
    )
  },
)
PhoneInput.displayName = 'PhoneInput'
