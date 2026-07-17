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

const h1Text = (container: HTMLElement) =>
  container.querySelector('h1')?.textContent ?? ''

describe('FrameEmpty — entry cue', () => {
  it('without a cue, renders neutral copy with NO unwitnessed claims (no "first time", no burst)', () => {
    const { container } = render(<FrameEmpty onAsk={() => {}} />)
    expect(screen.getByText(/What interests you\?/)).toBeInTheDocument()
    // "First time in this project" was a claim the system cannot witness — gone.
    expect(container.textContent).not.toMatch(/first time/i)
    expect(container.textContent).not.toMatch(/AI burst/)
  })

  it('with a fresh cue, surfaces the computed gap in witnessed present tense', () => {
    const { container } = render(<FrameEmpty onAsk={() => {}} entryCue={CUE} />)
    const text = container.textContent ?? ''
    expect(text).toContain('src/copyclip/intelligence/capture.py')
    expect(text).toMatch(/AI burst shaped/)
    expect(text).toMatch(/~19 days ago/)
    expect(text).toMatch(/haven't been back in 41 days/)
    expect(text).not.toMatch(/first time/i)
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

  it('a stale cue rescopes the GAP CLAIM ITSELF in the headline — never a present-tense gap', () => {
    const { container } = render(
      <FrameEmpty onAsk={() => {}} entryCue={{ ...CUE, stale: true, analyzed_age_days: 20 }} />,
    )
    const h1 = h1Text(container)
    // the claim carries its own scope, in past tense, inside the h1
    expect(h1).toMatch(/As of the last analysis ~20 days ago, you hadn't been back in 41 days\./)
    // the unhedged present-tense form must NOT appear anywhere
    expect(container.textContent).not.toMatch(/You haven't been back/)
    // the burst fact itself stays unhedged — it is a witnessed commit
    expect(h1).toMatch(/AI burst shaped/)
  })

  it('a fresh cue does not hedge', () => {
    const { container } = render(<FrameEmpty onAsk={() => {}} entryCue={CUE} />)
    expect(container.textContent).not.toMatch(/as of the last analysis/i)
  })

  it('never_human_touched: present claim when fresh, past + scoped when stale', () => {
    const fresh = render(
      <FrameEmpty onAsk={() => {}} entryCue={{ ...CUE, never_human_touched: true }} />,
    )
    expect(fresh.container.textContent).toMatch(/No human commit has ever touched it\./)
    expect(fresh.container.textContent).not.toMatch(/been back/)
    fresh.unmount()

    const stale = render(
      <FrameEmpty
        onAsk={() => {}}
        entryCue={{ ...CUE, never_human_touched: true, stale: true, analyzed_age_days: 20 }}
      />,
    )
    const h1 = h1Text(stale.container)
    expect(h1).toMatch(/As of the last analysis ~20 days ago, no human commit had touched it\./)
    expect(stale.container.textContent).not.toMatch(/has ever touched/)
  })

  it('last_contact_days=0 never renders "0 days" — the same-day touch is phrased honestly', () => {
    const { container } = render(
      <FrameEmpty onAsk={() => {}} entryCue={{ ...CUE, last_contact_days: 0 }} />,
    )
    expect(container.textContent).toMatch(/You touched it earlier today — the burst came after\./)
    expect(container.textContent).not.toMatch(/0 days/)
  })

  it('singular day counts render "1 day", never "1 days"', () => {
    const { container } = render(
      <FrameEmpty onAsk={() => {}} entryCue={{ ...CUE, last_contact_days: 1, ai_burst_days: 1 }} />,
    )
    expect(container.textContent).toMatch(/~1 day ago/)
    expect(container.textContent).toMatch(/back in 1 day\./)
    expect(container.textContent).not.toMatch(/1 days/)
  })

  it('ai_burst_days=0 renders "today"', () => {
    const { container } = render(
      <FrameEmpty onAsk={() => {}} entryCue={{ ...CUE, ai_burst_days: 0 }} />,
    )
    expect(h1Text(container)).toMatch(/shaped .* today\./)
  })

  it('the three generic starters survive in both states', () => {
    const { rerender } = render(<FrameEmpty onAsk={() => {}} />)
    expect(screen.getByRole('button', { name: /what does this project do/i })).toBeInTheDocument()
    rerender(<FrameEmpty onAsk={() => {}} entryCue={CUE} />)
    expect(screen.getByRole('button', { name: /what does this project do/i })).toBeInTheDocument()
  })
})
