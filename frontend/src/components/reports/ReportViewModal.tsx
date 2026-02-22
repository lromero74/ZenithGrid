import { X, Download } from 'lucide-react'

interface ReportViewModalProps {
  isOpen: boolean
  onClose: () => void
  htmlContent: string | null
  title: string
  onDownloadPdf?: () => void
  hasPdf?: boolean
}

export function ReportViewModal({
  isOpen, onClose, htmlContent, title, onDownloadPdf, hasPdf
}: ReportViewModalProps) {
  if (!isOpen || !htmlContent) return null

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="w-full max-w-4xl h-[90vh] bg-slate-800 rounded-lg shadow-2xl border border-slate-700 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700 shrink-0">
          <h3 className="text-lg font-semibold text-white truncate">{title}</h3>
          <div className="flex items-center gap-2">
            {hasPdf && onDownloadPdf && (
              <button
                onClick={onDownloadPdf}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Download className="w-4 h-4" />
                PDF
              </button>
            )}
            <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Report Content — isolated iframe */}
        <div className="flex-1 overflow-hidden">
          <iframe
            srcDoc={htmlContent}
            className="w-full h-full border-0"
            title="Report Preview"
            sandbox="allow-same-origin allow-scripts"
          />
        </div>
      </div>
    </div>
  )
}
