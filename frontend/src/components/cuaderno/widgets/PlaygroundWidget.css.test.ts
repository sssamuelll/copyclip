/**
 * Asserts that every CSS class emitted by the trace branch of PlaygroundWidget
 * has a corresponding rule in cuaderno.css.  The token system (--neg /
 * --neg-ink / --neg-line) was added in commit aa87666; these tests verify
 * those tokens are actually consumed by .playground-trace-raised.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const cssPath = resolve(__dirname, '../../../styles/cuaderno.css')
const css = readFileSync(cssPath, 'utf-8')

const REQUIRED_SELECTORS = [
  '.playground-trace',
  '.playground-trace-file',
  '.playground-trace-steps',
  '.playground-trace-step',
  '.playground-trace-step--call',
  '.playground-trace-step--line',
  '.playground-trace-step--return',
  '.playground-trace-step--raise',
  '.playground-trace-lineno',
  '.playground-trace-vars',
  '.playground-trace-varname',
  '.playground-trace-varval',
  '.playground-trace-raised',
  '.playground-truncated-badge',
]

describe('cuaderno.css — trace widget classes', () => {
  for (const selector of REQUIRED_SELECTORS) {
    it(`declares ${selector}`, () => {
      // Match the selector either as a standalone rule or as part of a
      // compound selector (e.g. ".playground-trace-step--call" inside
      // ".playground-trace-step--call,").  Escape the special chars for regex.
      const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/--/g, '--')
      expect(css, `Missing CSS rule for "${selector}" in cuaderno.css`).toMatch(
        new RegExp(escaped),
      )
    })
  }

  it('.playground-trace-raised uses --neg token (exception band)', () => {
    // Find the raised rule and confirm it references at least one --neg token
    const raisedBlockMatch = css.match(/\.playground-trace-raised\s*\{([^}]+)\}/)
    expect(
      raisedBlockMatch,
      '.playground-trace-raised rule must be present in cuaderno.css',
    ).not.toBeNull()
    const block = raisedBlockMatch![1]
    expect(block, '.playground-trace-raised must reference a --neg token').toMatch(/--neg/)
  })
})
