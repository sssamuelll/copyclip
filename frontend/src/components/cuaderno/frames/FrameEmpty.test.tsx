import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FrameEmpty } from './FrameEmpty'
import type { EntryCue } from '../../../types/api'

const CUE: EntryCue = {
  file_path: 'src/copyclip/intelligence/capture.py',
  last_contact_days: 41,
  ai_burst_days: 19,
  last_contact_source: 'git',
  never_human_touched: false,
  analyzed_age_days: 3,
  stale: false,
}

describe('FrameEmpty — entry cue', () => {
  it('without a cue, keeps the default first-time copy (silent, nothing invented)', () => {
    render(<FrameEmpty onAsk={() => {}} />)
    expect(screen.getByText(/First time in this project/)).toBeInTheDocument()
    expect(screen.queryByText(/AI burst/)).toBeNull()
  })

  it('with a cue, surfaces the computed gap instead of the first-time copy', () => {
    const { container } = render(<FrameEmpty onAsk={() => {}} entryCue={CUE} />)
    expect(screen.queryByText(/First time in this project/)).toBeNull()
    const text = container.textContent ?? ''
    expect(text).toContain('src/copyclip/intelligence/capture.py')
    expect(text).toMatch(/AI burst shaped/)
    expect(text).toMatch(/~19 days ago/)
    expect(text).toMatch(/haven't been back in 41 days/)
  })

  it('cue starter launches an ask about that file', async () => {
    const onAsk = vi.fn()
    render(<FrameEmpty onAsk={onAsk} entryCue={CUE} />)
    await userEvent.click(
      screen.getByRole('button', { name: /why does .*capture\.py exist/i }),
    )
    expect(onAsk).toHaveBeenCalledTimes(1)
    expect(onAsk.mock.calls[0][0]).toContain('src/copyclip/intelligence/capture.py')
  })

  it('a stale cue hedges the claim to the age of the last analysis', () => {
    const { container } = render(
      <FrameEmpty onAsk={() => {}} entryCue={{ ...CUE, stale: true, analyzed_age_days: 20 }} />,
    )
    expect(container.textContent).toMatch(/as of the last analysis ~20 days ago/i)
  })

  it('a fresh cue does not hedge', () => {
    const { container } = render(<FrameEmpty onAsk={() => {}} entryCue={CUE} />)
    expect(container.textContent).not.toMatch(/as of the last analysis/i)
  })

  it('never_human_touched says so instead of claiming a return gap', () => {
    const { container } = render(
      <FrameEmpty onAsk={() => {}} entryCue={{ ...CUE, never_human_touched: true }} />,
    )
    expect(container.textContent).toMatch(/no human commit has ever touched it/i)
    expect(container.textContent).not.toMatch(/haven't been back in/)
  })

  it('the three generic starters survive in both states', () => {
    const { rerender } = render(<FrameEmpty onAsk={() => {}} />)
    expect(screen.getByRole('button', { name: /what does this project do/i })).toBeInTheDocument()
    rerender(<FrameEmpty onAsk={() => {}} entryCue={CUE} />)
    expect(screen.getByRole('button', { name: /what does this project do/i })).toBeInTheDocument()
  })
})
