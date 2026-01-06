import { useState, useEffect } from 'react'
import { GoogleUser, signOut } from '@jebin2/googleauthservice/client/src'
import Header from './Header'
import CameraGrid from './CameraGrid'
import ExpandedView from './ExpandedView'
import { fetchLive, fetchStorage, Channel } from '../services/api'
import './MainApp.css'

interface MainAppProps {
    user: GoogleUser
}

export default function MainApp({ user: _user }: MainAppProps) {
    const [view, setView] = useState<'grid' | 'expanded'>('grid')
    const [channels, setChannels] = useState<Record<string, Channel>>({})
    const [storage, setStorage] = useState<string>('Loading...')
    const [currentCam, setCurrentCam] = useState<string>('')
    const [isLoading, setIsLoading] = useState(true)  // Loading state

    useEffect(() => {
        loadData()

        // Refresh data periodically
        const interval = setInterval(loadData, 30000)
        return () => clearInterval(interval)
    }, [])

    async function loadData() {
        try {
            const [liveData, storageData] = await Promise.all([
                fetchLive(),
                fetchStorage(),
            ])
            setChannels(liveData.channels || {})
            setStorage(storageData.summary || 'Unknown')
        } catch (err) {
            console.error('Failed to load data:', err)
        } finally {
            setIsLoading(false)
        }
    }

    function openCamera(camId: string) {
        setCurrentCam(camId)
        setView('expanded')
    }

    function goBack() {
        setView('grid')
    }

    async function handleLogout() {
        try {
            await fetch('/api/logout', { method: 'POST', credentials: 'include' })
            await signOut()
            window.location.reload()
        } catch (err) {
            console.error('Logout failed:', err)
        }
    }

    return (
        <div className="main-app">
            <Header
                storage={storage}
                showBack={view === 'expanded'}
                onBack={goBack}
                onLogout={handleLogout}
            />

            <main>
                {view === 'grid' ? (
                    <CameraGrid
                        channels={channels}
                        onOpenCamera={openCamera}
                        isLoading={isLoading}
                    />
                ) : (
                    <ExpandedView camId={currentCam} channels={channels} />
                )}
            </main>
        </div>
    )
}
