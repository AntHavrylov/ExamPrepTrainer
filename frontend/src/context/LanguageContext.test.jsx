import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { LanguageProvider, useLanguage } from './LanguageContext'
import { translations } from '../i18n/translations'

function Probe() {
  const { language, setLanguage, t } = useLanguage()
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="greeting">{t('app.title')}</span>
      <span data-testid="interpolated">{t('training.questionNumber', { n: 3 })}</span>
      <span data-testid="missing-key-fallback">{t('this.key.does.not.exist')}</span>
      <button onClick={() => setLanguage('uk')}>switch to uk</button>
      <button onClick={() => setLanguage('not-a-real-language')}>switch to bogus</button>
    </div>
  )
}

describe('LanguageContext', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('defaults to English and persists a language change to localStorage', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )

    expect(screen.getByTestId('language')).toHaveTextContent('en')
    expect(screen.getByTestId('interpolated')).toHaveTextContent('Question 3')

    act(() => {
      screen.getByText('switch to uk').click()
    })

    expect(screen.getByTestId('language')).toHaveTextContent('uk')
    expect(localStorage.getItem('prep_trainer_language')).toBe('uk')
  })

  it('ignores attempts to set an unsupported language', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )

    act(() => {
      screen.getByText('switch to bogus').click()
    })

    expect(screen.getByTestId('language')).toHaveTextContent('en')
  })

  it('falls back to the key itself when a translation is missing', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )

    expect(screen.getByTestId('missing-key-fallback')).toHaveTextContent('this.key.does.not.exist')
  })

  it('throws when used outside a LanguageProvider', () => {
    expect(() => render(<Probe />)).toThrow('useLanguage must be used within LanguageProvider')
  })
})

describe('translations completeness', () => {
  it('uk and ru define every key that en defines', () => {
    const enKeys = Object.keys(translations.en).sort()
    expect(Object.keys(translations.uk).sort()).toEqual(enKeys)
    expect(Object.keys(translations.ru).sort()).toEqual(enKeys)
  })
})
