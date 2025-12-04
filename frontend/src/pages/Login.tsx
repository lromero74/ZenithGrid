/**
 * Login Page
 *
 * Simple login form with email/password authentication.
 * Includes signup modal with terms of service agreement.
 */

import { useState, FormEvent } from 'react'
import { Activity, Lock, Mail, AlertCircle, User, X, CheckSquare, Square } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { login, signup } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Signup modal state
  const [showSignup, setShowSignup] = useState(false)
  const [signupEmail, setSignupEmail] = useState('')
  const [signupPassword, setSignupPassword] = useState('')
  const [signupConfirmPassword, setSignupConfirmPassword] = useState('')
  const [signupDisplayName, setSignupDisplayName] = useState('')
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const [signupError, setSignupError] = useState<string | null>(null)
  const [isSigningUp, setIsSigningUp] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      await login(email, password)
      // Login successful - AuthContext will update and App will show main content
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSignup = async (e: FormEvent) => {
    e.preventDefault()
    setSignupError(null)

    // Validation
    if (signupPassword !== signupConfirmPassword) {
      setSignupError('Passwords do not match')
      return
    }

    if (signupPassword.length < 8) {
      setSignupError('Password must be at least 8 characters')
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
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4">
      {/* Logo and Title */}
      <div className="flex items-center space-x-3 mb-8">
        <Activity className="w-10 h-10 text-blue-500" />
        <div>
          <h1 className="text-3xl font-bold text-white">Zenith Grid</h1>
          <p className="text-sm text-slate-400">Multi-Strategy Trading Platform</p>
        </div>
      </div>

      {/* Login Card */}
      <div className="w-full max-w-md bg-slate-800 rounded-lg shadow-xl border border-slate-700 p-8">
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

        {/* Create Account Link */}
        <div className="mt-6 text-center">
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
      </div>

      {/* Footer */}
      <p className="mt-8 text-sm text-slate-500">
        &copy; {new Date().getFullYear()} Romero Tech Solutions
      </p>

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
                      className="w-full pl-10 pr-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
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
                      className="w-full pl-10 pr-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
                </div>

                {/* Terms of Service */}
                <div className="bg-slate-700/50 rounded-lg p-4 border border-slate-600">
                  <h4 className="text-sm font-semibold text-white mb-3">End User License Agreement & Risk Disclosure</h4>
                  <div className="text-xs text-slate-300 space-y-2 max-h-48 overflow-y-auto mb-4 pr-2">
                    <p className="font-semibold text-slate-200">END USER LICENSE AGREEMENT</p>
                    <p>
                      This End User License Agreement ("Agreement") is a legal agreement between you ("User") and Romero Tech Solutions ("Company") for the use of Zenith Grid automated trading bot software ("Software").
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
                      <strong>9. Release of Liability:</strong> YOU HEREBY RELEASE, WAIVE, AND FOREVER DISCHARGE THE COMPANY, ITS OWNERS, OFFICERS, EMPLOYEES, AGENTS, AND AFFILIATES FROM ANY AND ALL LIABILITY, CLAIMS, DEMANDS, ACTIONS, OR CAUSES OF ACTION WHATSOEVER ARISING OUT OF OR RELATED TO ANY LOSS, DAMAGE, OR INJURY THAT MAY BE SUSTAINED BY YOU AS A RESULT OF USING THIS SOFTWARE, INCLUDING BUT NOT LIMITED TO FINANCIAL LOSSES FROM TRADING ACTIVITIES.
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
                      I have read, understood, and agree to the End User License Agreement and Risk Disclosure. I acknowledge that automated trading involves substantial risk of loss, I assume sole liability for all trading outcomes, and I release the Company from all liability related to my use of this Software.
                    </span>
                  </button>
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={isSigningUp || !signupEmail || !signupPassword || !signupConfirmPassword || !agreedToTerms}
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
