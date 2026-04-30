import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './sidebar'
import { Topbar } from './topbar'
import { CmdK } from './cmdk'

export function AppLayout() {
  const [cmdkOpen, setCmdkOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmdkOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="sf-app">
      <Sidebar />
      <div className="sf-main">
        <Topbar onOpenCmdK={() => setCmdkOpen(true)} />
        <div className="sf-content">
          <Outlet />
        </div>
      </div>
      <CmdK open={cmdkOpen} onClose={() => setCmdkOpen(false)} />
    </div>
  )
}
