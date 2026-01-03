import './Header.css'

interface HeaderProps {
    storage: string
    showBack: boolean
    onBack: () => void
    onLogout: () => void
}

export default function Header({ storage, showBack, onBack, onLogout }: HeaderProps) {
    async function handleRestartYT() {
        try {
            await fetch('/api/youtube/restart', { method: 'POST', credentials: 'include' })
            alert('YouTube stream restart requested')
        } catch (err) {
            alert('Failed to restart YouTube stream')
        }
    }

    return (
        <header>
            <div className="brand">
                {showBack && (
                    <button className="btn btn-ghost" onClick={onBack}>←</button>
                )}
                <span>📺</span>
            </div>
            <div className="header-controls">
                <div className="storage-info">{storage}</div>
                <button className="btn btn-ghost desktop-only" onClick={handleRestartYT} title="Restart YouTube Stream">
                    🔄 YT
                </button>
                <button className="btn btn-ghost" onClick={onLogout}>
                    Logout
                </button>
            </div>
        </header>
    )
}
