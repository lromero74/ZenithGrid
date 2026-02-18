/**
 * Login Page
 *
 * Simple login form with email/password authentication.
 * Includes signup modal with terms of service agreement.
 */

import { useState, useRef, useEffect, FormEvent } from 'react'
import { Truck, Lock, Mail, AlertCircle, User, X, CheckSquare, Square, Shield, ArrowLeft, TrendingUp, BarChart3, Zap, Check, Smartphone, RefreshCw } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useBrand } from '../contexts/BrandContext'
import { PasswordStrengthMeter, isPasswordValid } from '../components/PasswordStrengthMeter'
import { ForgotPassword } from '../components/ForgotPassword'

export default function Login() {
  const { login, signup, mfaPending, mfaMethods, verifyMFA, verifyMFAEmailCode, resendMFAEmail, cancelMFA } = useAuth()
  const { brand, brandImageUrl } = useBrand()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // MFA verification state
  const [mfaCode, setMfaCode] = useState('')
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [isVerifyingMFA, setIsVerifyingMFA] = useState(false)
  const [rememberDevice, setRememberDevice] = useState(false)
  const [mfaTab, setMfaTab] = useState<'totp' | 'email_code' | 'email_link'>('totp')
  const [emailCode, setEmailCode] = useState('')
  const [isResendingEmail, setIsResendingEmail] = useState(false)
  const [resendCooldown, setResendCooldown] = useState(0)
  const mfaInputRef = useRef<HTMLInputElement>(null)
  const emailCodeInputRef = useRef<HTMLInputElement>(null)

  // Signup modal state
  const [showSignup, setShowSignup] = useState(false)
  const [signupEmail, setSignupEmail] = useState('')
  const [signupPassword, setSignupPassword] = useState('')
  const [signupConfirmPassword, setSignupConfirmPassword] = useState('')
  const [signupDisplayName, setSignupDisplayName] = useState('')
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const [signupError, setSignupError] = useState<string | null>(null)
  const [isSigningUp, setIsSigningUp] = useState(false)
  const [showForgotPassword, setShowForgotPassword] = useState(false)

  // Set default MFA tab based on available methods
  useEffect(() => {
    if (mfaPending && mfaMethods.length > 0) {
      if (mfaMethods.includes('totp')) {
        setMfaTab('totp')
      } else if (mfaMethods.includes('email_code')) {
        setMfaTab('email_code')
      } else if (mfaMethods.includes('email_link')) {
        setMfaTab('email_link')
      }
    }
  }, [mfaPending, mfaMethods])

  // Auto-focus MFA input when MFA step or tab changes
  useEffect(() => {
    if (mfaPending) {
      if (mfaTab === 'totp' && mfaInputRef.current) {
        mfaInputRef.current.focus()
      } else if (mfaTab === 'email_code' && emailCodeInputRef.current) {
        emailCodeInputRef.current.focus()
      }
    }
  }, [mfaPending, mfaTab])

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return
    const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000)
    return () => clearTimeout(timer)
  }, [resendCooldown])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      await login(email, password)
      // Login successful or MFA pending - AuthContext handles state
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleMFASubmit = async (e: FormEvent) => {
    e.preventDefault()
    setMfaError(null)
    setIsVerifyingMFA(true)

    try {
      await verifyMFA(mfaCode, rememberDevice)
      // MFA verified - AuthContext will set user and tokens
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : 'Verification failed')
      setMfaCode('')
    } finally {
      setIsVerifyingMFA(false)
    }
  }

  const handleEmailCodeSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setMfaError(null)
    setIsVerifyingMFA(true)

    try {
      await verifyMFAEmailCode(emailCode, rememberDevice)
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : 'Verification failed')
      setEmailCode('')
    } finally {
      setIsVerifyingMFA(false)
    }
  }

  const handleResendEmail = async () => {
    if (isResendingEmail || resendCooldown > 0) return
    setIsResendingEmail(true)
    try {
      await resendMFAEmail()
      setResendCooldown(60)
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : 'Failed to resend email')
    } finally {
      setIsResendingEmail(false)
    }
  }

  const handleCancelMFA = () => {
    cancelMFA()
    setMfaCode('')
    setEmailCode('')
    setMfaError(null)
  }

  const handleSignup = async (e: FormEvent) => {
    e.preventDefault()
    setSignupError(null)

    // Validation
    if (signupPassword !== signupConfirmPassword) {
      setSignupError('Passwords do not match')
      return
    }

    if (!isPasswordValid(signupPassword)) {
      setSignupError('Password must be at least 8 characters with uppercase, lowercase, and a number')
      return
    }

    if (!agreedToTerms) {
      setSignupError('You must agree to the Terms of Service and Risk Disclaimer')
      return
    }

    setIsSigningUp(true)

    try {
      await signup(signupEmail, signupPassword, signupDisplayName || undefined)
      // Signup successful - AuthContext will update and App will show main content
    } catch (err) {
      setSignupError(err instanceof Error ? err.message : 'Signup failed')
    } finally {
      setIsSigningUp(false)
    }
  }

  const openSignupModal = () => {
    setShowSignup(true)
    setSignupError(null)
    setSignupEmail('')
    setSignupPassword('')
    setSignupConfirmPassword('')
    setSignupDisplayName('')
    setAgreedToTerms(false)
  }

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Brand background image */}
      {brand.images.loginBackground && (
        <div
          className="absolute inset-0 bg-cover bg-center opacity-[0.07] pointer-events-none"
          style={{ backgroundImage: `url(${brandImageUrl(brand.images.loginBackground)})` }}
        />
      )}
      {/* Subtle background gradient accents */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-[var(--color-primary,#00d4ff)]/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-500/5 rounded-full blur-3xl" />
      </div>

      {/* Logo and Title */}
      <div className="flex flex-col items-center mb-8 relative">
        <div className="flex items-center space-x-3 mb-3">
          <div className="relative">
            <Truck className="w-11 h-11 text-theme-primary" />
            <div className="absolute inset-0 w-11 h-11 bg-[var(--color-primary,#00d4ff)]/20 rounded-full blur-md" />
          </div>
          <h1 className="text-4xl font-bold text-white tracking-tight">{brand.loginTitle}</h1>
        </div>
        <p className="text-slate-400 text-sm tracking-wide">{brand.loginTagline}</p>
        {brand.companyLine && <p className="text-slate-500 text-xs mt-1">{brand.companyLine}</p>}
        <div className="flex items-center space-x-6 mt-4 text-xs text-slate-500">
          <span className="flex items-center space-x-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-emerald-500/70" />
            <span>Automated Trading</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <BarChart3 className="w-3.5 h-3.5 text-blue-500/70" />
            <span>AI Analysis</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-500/70" />
            <span>Grid Strategies</span>
          </span>
        </div>
      </div>

      {/* Login Card */}
      <div className="w-full max-w-md bg-slate-800/80 backdrop-blur-sm rounded-xl shadow-2xl border border-slate-700/50 p-8 relative">
        {mfaPending ? (
          <>
            {/* MFA Verification Step */}
            <div className="flex items-center space-x-3 mb-2">
              <Shield className="w-7 h-7 text-blue-400" />
              <h2 className="text-2xl font-semibold text-white">Two-Factor Authentication</h2>
            </div>
            <p className="text-slate-400 text-sm mb-6">
              Verify your identity to complete login.
            </p>

            {/* MFA Error Message */}
            {mfaError && (
              <div className="mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                <p className="text-red-400 text-sm">{mfaError}</p>
              </div>
            )}

            {/* MFA Method Tabs (only show if multiple methods) */}
            {mfaMethods.length > 1 && (
              <div className="flex rounded-lg bg-slate-700/50 p-1 mb-6">
                {mfaMethods.includes('totp') && (
                  <button
                    type="button"
                    onClick={() => { setMfaTab('totp'); setMfaError(null) }}
                    className={`flex-1 flex items-center justify-center space-x-1.5 py-2 px-3 rounded-md text-sm font-medium transition-colors ${
                      mfaTab === 'totp'
                        ? 'bg-slate-600 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Smartphone className="w-4 h-4" />
                    <span>Authenticator</span>
                  </button>
                )}
                {mfaMethods.includes('email_code') && (
                  <button
                    type="button"
                    onClick={() => { setMfaTab('email_code'); setMfaError(null) }}
                    className={`flex-1 flex items-center justify-center space-x-1.5 py-2 px-3 rounded-md text-sm font-medium transition-colors ${
                      mfaTab === 'email_code'
                        ? 'bg-slate-600 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Mail className="w-4 h-4" />
                    <span>Email Code</span>
                  </button>
                )}
                {mfaMethods.includes('email_link') && (
                  <button
                    type="button"
                    onClick={() => { setMfaTab('email_link'); setMfaError(null) }}
                    className={`flex-1 flex items-center justify-center space-x-1.5 py-2 px-3 rounded-md text-sm font-medium transition-colors ${
                      mfaTab === 'email_link'
                        ? 'bg-slate-600 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Mail className="w-4 h-4" />
                    <span>Email Link</span>
                  </button>
                )}
              </div>
            )}

            {/* TOTP Authenticator Tab */}
            {mfaTab === 'totp' && mfaMethods.includes('totp') && (
              <form onSubmit={handleMFASubmit} className="space-y-6">
                <div>
                  <label htmlFor="mfaCode" className="block text-sm font-medium text-slate-300 mb-2">
                    Authenticator Code
                  </label>
                  <input
                    ref={mfaInputRef}
                    id="mfaCode"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    required
                    autoComplete="one-time-code"
                    placeholder="000000"
                    className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white text-center text-2xl tracking-[0.5em] font-mono placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <p className="text-xs text-slate-500 mt-1">Enter the 6-digit code from your authenticator app</p>
                </div>

                <button
                  type="submit"
                  disabled={isVerifyingMFA || mfaCode.length !== 6}
                  className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800"
                >
                  {isVerifyingMFA ? (
                    <span className="flex items-center justify-center space-x-2">
                      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span>Verifying...</span>
                    </span>
                  ) : (
                    'Verify'
                  )}
                </button>
              </form>
            )}

            {/* Email Code Tab */}
            {mfaTab === 'email_code' && mfaMethods.includes('email_code') && (
              <form onSubmit={handleEmailCodeSubmit} className="space-y-6">
                <div>
                  <label htmlFor="emailCode" className="block text-sm font-medium text-slate-300 mb-2">
                    Email Verification Code
                  </label>
                  <input
                    ref={emailCodeInputRef}
                    id="emailCode"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={emailCode}
                    onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    required
                    autoComplete="one-time-code"
                    placeholder="000000"
                    className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white text-center text-2xl tracking-[0.5em] font-mono placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <p className="text-xs text-slate-500 mt-1">Enter the 6-digit code sent to your email</p>
                </div>

                <button
                  type="submit"
                  disabled={isVerifyingMFA || emailCode.length !== 6}
                  className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800"
                >
                  {isVerifyingMFA ? (
                    <span className="flex items-center justify-center space-x-2">
                      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span>Verifying...</span>
                    </span>
                  ) : (
                    'Verify'
                  )}
                </button>

                {/* Resend Code */}
                <button
                  type="button"
                  onClick={handleResendEmail}
                  disabled={isResendingEmail || resendCooldown > 0}
                  className="w-full flex items-center justify-center space-x-2 text-slate-400 hover:text-blue-400 disabled:text-slate-600 transition-colors text-sm"
                >
                  <RefreshCw className={`w-4 h-4 ${isResendingEmail ? 'animate-spin' : ''}`} />
                  <span>
                    {resendCooldown > 0 ? `Resend code (${resendCooldown}s)` : 'Resend code'}
                  </span>
                </button>
              </form>
            )}

            {/* Email Link Tab */}
            {mfaTab === 'email_link' && mfaMethods.includes('email_link') && (
              <div className="space-y-6">
                <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-6 text-center">
                  <Mail className="w-12 h-12 text-blue-400 mx-auto mb-3" />
                  <p className="text-slate-200 font-medium mb-2">Check your email</p>
                  <p className="text-slate-400 text-sm">
                    We sent a verification link to your email address. Click the link to complete your login.
                  </p>
                </div>

                {/* Resend Link */}
                <button
                  type="button"
                  onClick={handleResendEmail}
                  disabled={isResendingEmail || resendCooldown > 0}
                  className="w-full flex items-center justify-center space-x-2 text-slate-400 hover:text-blue-400 disabled:text-slate-600 transition-colors text-sm"
                >
                  <RefreshCw className={`w-4 h-4 ${isResendingEmail ? 'animate-spin' : ''}`} />
                  <span>
                    {resendCooldown > 0 ? `Resend email (${resendCooldown}s)` : 'Resend email'}
                  </span>
                </button>
              </div>
            )}

            {/* Common: Remember Device + Back */}
            <div className="mt-6 space-y-4">
              <button
                type="button"
                onClick={() => setRememberDevice(!rememberDevice)}
                className="w-full flex items-center space-x-3 text-left"
              >
                {rememberDevice ? (
                  <CheckSquare className="w-5 h-5 text-blue-500 flex-shrink-0" />
                ) : (
                  <Square className="w-5 h-5 text-slate-400 flex-shrink-0" />
                )}
                <span className="text-sm text-slate-300">Remember this device for 30 days</span>
              </button>

              <button
                type="button"
                onClick={handleCancelMFA}
                className="w-full flex items-center justify-center space-x-2 text-slate-400 hover:text-white transition-colors text-sm"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back to login</span>
              </button>
            </div>
          </>
        ) : (
          <>
            {/* Normal Login Step */}
            <h2 className="text-2xl font-semibold text-white mb-6 text-center">Sign In</h2>

            {/* Error Message */}
            {error && (
              <div className="mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {/* Login Form */}
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Email Field */}
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-2">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                    autoFocus
                    placeholder="you@example.com"
                    className="w-full pl-10 pr-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Password Field */}
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-2">
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    className="w-full pl-10 pr-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isLoading || !email || !password}
                className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800"
              >
                {isLoading ? (
                  <span className="flex items-center justify-center space-x-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Signing in...</span>
                  </span>
                ) : (
                  'Sign In'
                )}
              </button>
            </form>

            {/* Forgot Password Link */}
            <div className="mt-4 text-center">
              <button
                onClick={() => setShowForgotPassword(true)}
                className="text-slate-400 hover:text-blue-400 text-sm transition-colors"
              >
                Forgot your password?
              </button>
            </div>

            {/* Create Account Link */}
            <div className="mt-3 text-center">
              <p className="text-slate-400 text-sm">
                Don't have an account?{' '}
                <button
                  onClick={openSignupModal}
                  className="text-blue-400 hover:text-blue-300 font-medium transition-colors"
                >
                  Create Account
                </button>
              </p>
            </div>
          </>
        )}
      </div>

      {/* Footer */}
      <p className="mt-8 text-sm text-slate-500">
        &copy; {new Date().getFullYear()} Romero Tech Solutions
      </p>

      {/* Forgot Password Modal */}
      {showForgotPassword && (
        <ForgotPassword onClose={() => setShowForgotPassword(false)} />
      )}

      {/* Signup Modal */}
      {showSignup && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-lg bg-slate-800 rounded-lg shadow-2xl border border-slate-700 max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-slate-700">
              <h3 className="text-xl font-semibold text-white">Create Account</h3>
              <button
                onClick={() => setShowSignup(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6">
              {/* Error Message */}
              {signupError && (
                <div className="mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                  <p className="text-red-400 text-sm">{signupError}</p>
                </div>
              )}

              <form onSubmit={handleSignup} className="space-y-5">
                {/* Display Name Field */}
                <div>
                  <label htmlFor="signupDisplayName" className="block text-sm font-medium text-slate-300 mb-2">
                    Display Name (Optional)
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                    <input
                      id="signupDisplayName"
                      type="text"
                      value={signupDisplayName}
                      onChange={(e) => setSignupDisplayName(e.target.value)}
                      autoComplete="name"
                      placeholder="Your name"
                      className="w-full pl-10 pr-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
                </div>

                {/* Email Field */}
                <div>
                  <label htmlFor="signupEmail" className="block text-sm font-medium text-slate-300 mb-2">
                    Email Address
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                    <input
                      id="signupEmail"
                      type="email"
                      value={signupEmail}
                      onChange={(e) => setSignupEmail(e.target.value)}
                      required
                      autoComplete="email"
                      placeholder="you@example.com"
                      className="w-full pl-10 pr-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
                </div>

                {/* Password Field */}
                <div>
                  <label htmlFor="signupPassword" className="block text-sm font-medium text-slate-300 mb-2">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                    <input
                      id="signupPassword"
                      type="password"
                      value={signupPassword}
                      onChange={(e) => setSignupPassword(e.target.value)}
                      required
                      autoComplete="new-password"
                      placeholder="Minimum 8 characters"
                      className={`w-full pl-10 pr-4 py-3 bg-slate-700 border rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                        signupPassword && signupConfirmPassword && signupPassword === signupConfirmPassword
                          ? 'border-green-500 focus:ring-green-500 ring-1 ring-green-500/50'
                          : 'border-slate-600 focus:ring-blue-500'
                      }`}
                    />
                  </div>
                  <PasswordStrengthMeter password={signupPassword} />
                </div>

                {/* Confirm Password Field */}
                <div>
                  <label htmlFor="signupConfirmPassword" className="block text-sm font-medium text-slate-300 mb-2">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                    <input
                      id="signupConfirmPassword"
                      type="password"
                      value={signupConfirmPassword}
                      onChange={(e) => setSignupConfirmPassword(e.target.value)}
                      required
                      autoComplete="new-password"
                      placeholder="Re-enter your password"
                      className={`w-full pl-10 pr-12 py-3 bg-slate-700 border rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                        signupConfirmPassword && signupPassword === signupConfirmPassword
                          ? 'border-green-500 focus:ring-green-500 ring-1 ring-green-500/50'
                          : signupConfirmPassword && signupPassword !== signupConfirmPassword
                            ? 'border-red-500 focus:ring-red-500 ring-1 ring-red-500/50'
                            : 'border-slate-600 focus:ring-blue-500'
                      }`}
                    />
                    {signupConfirmPassword.length > 0 && (
                      <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
                        {signupPassword === signupConfirmPassword ? (
                          <Check className="w-5 h-5 text-green-400" />
                        ) : (
                          <span className="text-xs text-red-400">No match</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Terms of Service */}
                <div className="bg-slate-700/50 rounded-lg p-4 border border-slate-600">
                  <h4 className="text-sm font-semibold text-white mb-3">End User License Agreement & Risk Disclosure</h4>
                  <div className="text-xs text-slate-300 space-y-2 max-h-48 overflow-y-auto mb-4 pr-2">
                    <p className="font-semibold text-slate-200">END USER LICENSE AGREEMENT</p>
                    <p>
                      This End User License Agreement ("Agreement") is a legal agreement between you ("User") and {brand.company || 'the provider'} ("Company") for the use of {brand.shortName} automated trading bot software ("Software").
                    </p>
                    <p>
                      <strong>1. License Grant:</strong> Subject to the terms of this Agreement, the Company grants you a limited, non-exclusive, non-transferable, revocable license to use the Software for your personal trading activities.
                    </p>
                    <p>
                      <strong>2. Restrictions:</strong> You may not: (a) sublicense, sell, or redistribute the Software; (b) modify, reverse engineer, or create derivative works; (c) use the Software for any unlawful purpose; (d) remove any proprietary notices.
                    </p>
                    <p>
                      <strong>3. Intellectual Property:</strong> The Software and all copies remain the property of the Company. This Agreement does not transfer any ownership rights.
                    </p>
                    <p>
                      <strong>4. User Responsibilities:</strong> You are solely responsible for: (a) securing your account credentials and API keys; (b) all trading decisions and their outcomes; (c) compliance with all applicable laws in your jurisdiction; (d) tax obligations arising from trading activities; (e) monitoring your automated bots and ensuring proper configuration.
                    </p>
                    <p className="font-semibold text-yellow-400 pt-2">AUTOMATED TRADING BOT RISK DISCLOSURE</p>
                    <p>
                      <strong>5. Automated Trading Risks:</strong> The Software enables automated trading through trading bots that execute buy and sell orders without manual intervention. YOU ACKNOWLEDGE AND ACCEPT THAT:
                    </p>
                    <p className="pl-4">
                      (a) Automated bots may execute trades rapidly and continuously, potentially resulting in significant financial losses;<br/>
                      (b) Bot strategies may perform differently than expected due to market conditions, technical issues, or configuration errors;<br/>
                      (c) Past performance of any strategy does not guarantee future results;<br/>
                      (d) System downtime, network issues, or exchange API failures may prevent bots from executing as intended;<br/>
                      (e) Market volatility can cause rapid losses that exceed your initial investment;<br/>
                      (f) You are solely responsible for setting appropriate risk parameters, position sizes, and stop-loss limits.
                    </p>
                    <p>
                      <strong>6. No Guarantees of Profit:</strong> The Company makes NO guarantees regarding profits, returns, or trading performance. The Software is a tool that executes YOUR configured strategies. Losses are an inherent risk of trading.
                    </p>
                    <p>
                      <strong>7. No Investment Advice:</strong> The Software is a tool only. Nothing provided constitutes financial, investment, legal, or tax advice. The Company is not a registered investment advisor, broker, or dealer. Consult qualified professionals before making investment decisions.
                    </p>
                    <p className="font-semibold text-red-400 pt-2">ASSUMPTION OF RISK & LIABILITY</p>
                    <p>
                      <strong>8. User Assumption of All Risk:</strong> BY USING THIS SOFTWARE, YOU EXPRESSLY ACKNOWLEDGE AND AGREE THAT YOU USE THE SOFTWARE ENTIRELY AT YOUR OWN RISK. YOU ASSUME FULL AND SOLE RESPONSIBILITY FOR:
                    </p>
                    <p className="pl-4">
                      (a) All trading decisions made by you or by automated bots configured by you;<br/>
                      (b) Any and all financial losses resulting from the use of this Software;<br/>
                      (c) Proper configuration and monitoring of all trading bots;<br/>
                      (d) Understanding the strategies and risks associated with automated trading;<br/>
                      (e) Ensuring adequate funds and appropriate position sizing.
                    </p>
                    <p>
                      <strong>9. Release of Liability:</strong> YOU HEREBY RELEASE, WAIVE, AND FOREVER DISCHARGE THE COMPANY, ITS OWNERS, MEMBERS, OFFICERS, EMPLOYEES, AGENTS, AND AFFILIATES FROM ANY AND ALL LIABILITY, CLAIMS, DEMANDS, ACTIONS, OR CAUSES OF ACTION WHATSOEVER ARISING OUT OF OR RELATED TO ANY LOSS, DAMAGE, OR INJURY THAT MAY BE SUSTAINED BY YOU AS A RESULT OF USING THIS SOFTWARE, INCLUDING BUT NOT LIMITED TO FINANCIAL LOSSES FROM TRADING ACTIVITIES.
                    </p>
                    <p>
                      <strong>10. Indemnification:</strong> You agree to indemnify, defend, and hold harmless the Company from any claims, damages, losses, or expenses arising from your use of the Software or violation of this Agreement.
                    </p>
                    <p className="font-semibold text-slate-200 pt-2">LIMITATION OF LIABILITY</p>
                    <p>
                      <strong>11. Disclaimer of Warranties:</strong> THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. THE COMPANY DOES NOT WARRANT THAT THE SOFTWARE WILL BE UNINTERRUPTED, ERROR-FREE, OR SECURE.
                    </p>
                    <p>
                      <strong>12. Limitation of Liability:</strong> TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL THE COMPANY BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO LOSS OF PROFITS, LOSS OF DATA, TRADING LOSSES, OR OTHER INTANGIBLE LOSSES, REGARDLESS OF THE CAUSE OF ACTION OR THE BASIS OF THE CLAIM, EVEN IF THE COMPANY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.
                    </p>
                    <p>
                      <strong>13. Maximum Liability:</strong> IN ANY EVENT, THE COMPANY'S TOTAL LIABILITY SHALL NOT EXCEED THE AMOUNT YOU PAID FOR THE SOFTWARE IN THE TWELVE (12) MONTHS PRECEDING THE CLAIM, OR ONE HUNDRED DOLLARS ($100), WHICHEVER IS LESS.
                    </p>
                    <p className="font-semibold text-slate-200 pt-2">GENERAL PROVISIONS</p>
                    <p>
                      <strong>14. Governing Law:</strong> This Agreement shall be governed by and construed in accordance with the laws of the State of Florida, without regard to conflict of law principles. Any disputes shall be resolved in the state or federal courts located in Hillsborough County, Florida.
                    </p>
                    <p>
                      <strong>15. Severability:</strong> If any provision of this Agreement is held invalid or unenforceable, the remaining provisions shall continue in full force and effect.
                    </p>
                    <p>
                      <strong>16. Entire Agreement:</strong> This Agreement constitutes the entire agreement between you and the Company regarding the Software and supersedes all prior agreements and understandings.
                    </p>
                    <p>
                      <strong>17. Modification:</strong> The Company reserves the right to modify this Agreement at any time. Continued use of the Software after modifications constitutes acceptance of the revised terms.
                    </p>
                  </div>

                  {/* Agreement Checkbox */}
                  <button
                    type="button"
                    onClick={() => setAgreedToTerms(!agreedToTerms)}
                    className="flex items-start space-x-3 w-full text-left"
                  >
                    {agreedToTerms ? (
                      <CheckSquare className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
                    ) : (
                      <Square className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" />
                    )}
                    <span className="text-sm text-slate-300">
                      I have read, understood, and agree to the End User License Agreement and Risk Disclosure. I acknowledge that automated trading involves substantial risk of loss, I assume sole liability for all trading outcomes, and I release the Company and its owners, members, and affiliates from all liability related to my use of this Software.
                    </span>
                  </button>
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={isSigningUp || !signupEmail || !isPasswordValid(signupPassword) || signupPassword !== signupConfirmPassword || !agreedToTerms}
                  className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800"
                >
                  {isSigningUp ? (
                    <span className="flex items-center justify-center space-x-2">
                      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span>Creating account...</span>
                    </span>
                  ) : (
                    'Create Account'
                  )}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
