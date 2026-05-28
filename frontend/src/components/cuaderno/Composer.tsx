import { useState, type FormEvent } from 'react'

type Props = {
  onSubmit: (text: string) => void
  disabled?: boolean
  placeholder?: string
}

export function Composer({
  onSubmit,
  disabled,
  placeholder = 'ask whatever you want…',
}: Props) {
  const [value, setValue] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!value.trim()) return
    onSubmit(value)
    setValue('')
  }

  return (
    <div className="composer-wrap">
      <form className="composer" onSubmit={handleSubmit}>
        <span className="prefix">›</span>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          spellCheck={false}
        />
        <button className="send" type="submit" disabled={!value.trim() || disabled}>
          ↵
        </button>
      </form>
    </div>
  )
}
