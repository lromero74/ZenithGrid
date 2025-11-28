import { useState } from 'react'
import { AccountsManagement } from '../components/AccountsManagement'
import { AddAccountModal } from '../components/AddAccountModal'
import { BlacklistManager } from '../components/BlacklistManager'

export default function Settings() {
  const [showAddAccountModal, setShowAddAccountModal] = useState(false)

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Settings</h2>
      </div>

      {/* Accounts Management Section */}
      <AccountsManagement onAddAccount={() => setShowAddAccountModal(true)} />

      {/* Coin Blacklist Section */}
      <BlacklistManager />

      {/* Add Account Modal */}
      <AddAccountModal
        isOpen={showAddAccountModal}
        onClose={() => setShowAddAccountModal(false)}
      />
    </div>
  )
}
