import './Header.css'

interface HeaderProps {
    showBack: boolean
    onBack: () => void
    onLogout: () => void
}

export default function Header({ showBack, onBack, onLogout }: HeaderProps) {
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
                <img src="/icon-192.png" alt="See Me" className="header-logo" />
            </div>
            <div className="header-controls">
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
