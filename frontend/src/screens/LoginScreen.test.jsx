import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../context/AuthContext'
import { LanguageProvider } from '../context/LanguageContext'
import LoginScreen from './LoginScreen'

describe('LoginScreen', () => {
  it('renders the login form by default and toggles to register', () => {
    render(
      <LanguageProvider>
        <AuthProvider>
          <LoginScreen />
        </AuthProvider>
      </LanguageProvider>,
    )

    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()

    fireEvent.click(screen.getByText("Don't have an account? Register"))

    expect(screen.getByRole('heading', { name: 'Register' })).toBeInTheDocument()
  })
})
