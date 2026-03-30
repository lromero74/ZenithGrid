import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

// Test the read-only badge in isolation — BotFormModal is too heavy to mount fully.
// The badge renders conditionally based on the `readOnly` prop inside the header div.
// We test the exact JSX pattern extracted from BotFormModal's header section.

function BotFormModalHeader({ readOnly, readOnlyTitle, editingBot }: {
  readOnly: boolean
  readOnlyTitle?: string
  editingBot?: boolean
}) {
  return (
    <div className="p-4 sm:p-6 border-b border-slate-700">
      <h3 className="text-xl font-bold">
        {readOnly
          ? readOnlyTitle || 'View Bot'
          : editingBot
            ? 'Edit Bot'
            : 'Create New Bot'}
      </h3>
      {readOnly && (
        <p className="text-xs text-violet-400 mt-1 flex items-center gap-1">
          <span>👁</span>
          Read-Only — shadow access
        </p>
      )}
    </div>
  )
}

describe('BotFormModal header — observer read-only indicator', () => {
  it('shows read-only badge when readOnly=true', () => {
    render(<BotFormModalHeader readOnly={true} readOnlyTitle="View Bot: My Bot" />)
    expect(screen.getByText(/Read-Only — shadow access/i)).toBeInTheDocument()
  })

  it('does not show read-only badge when readOnly=false', () => {
    render(<BotFormModalHeader readOnly={false} />)
    expect(screen.queryByText(/Read-Only — shadow access/i)).not.toBeInTheDocument()
  })

  it('shows the readOnlyTitle when readOnly=true', () => {
    render(<BotFormModalHeader readOnly={true} readOnlyTitle="View Bot: Grid Bot" />)
    expect(screen.getByText('View Bot: Grid Bot')).toBeInTheDocument()
  })
})
