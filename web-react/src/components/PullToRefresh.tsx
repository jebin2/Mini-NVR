import { useEffect, useRef, useState } from 'react'
import './PullToRefresh.css'

export default function PullToRefresh() {
    const [pullState, setPullState] = useState<'idle' | 'pulling' | 'ready' | 'refreshing'>('idle')
    const touchStartY = useRef(0)
    const isPulling = useRef(false)

    useEffect(() => {
        const handleTouchStart = (e: TouchEvent) => {
            if (window.scrollY === 0) {
                touchStartY.current = e.touches[0].clientY
                isPulling.current = true
                setPullState('idle')
            }
        }

        const handleTouchMove = (e: TouchEvent) => {
            if (!isPulling.current) return
            const y = e.touches[0].clientY
            const diff = y - touchStartY.current

            if (diff > 0 && window.scrollY === 0) {
                if (diff > 250) {
                    setPullState('ready')
                } else if (diff > 50) {
                    setPullState('pulling')
                }
            } else {
                setPullState('idle')
            }
        }

        const handleTouchEnd = async (e: TouchEvent) => {
            if (!isPulling.current) return
            isPulling.current = false

            const y = e.changedTouches[0].clientY
            const diff = y - touchStartY.current

            if (diff > 250 && window.scrollY === 0) {
                await hardRefresh()
            } else {
                setPullState('idle')
            }
        }

        document.addEventListener('touchstart', handleTouchStart, { passive: true })
        document.addEventListener('touchmove', handleTouchMove, { passive: true })
        document.addEventListener('touchend', handleTouchEnd)

        return () => {
            document.removeEventListener('touchstart', handleTouchStart)
            document.removeEventListener('touchmove', handleTouchMove)
            document.removeEventListener('touchend', handleTouchEnd)
        }
    }, [])

    async function hardRefresh() {
        setPullState('refreshing')

        try {
            // Unregister service workers
            if ('serviceWorker' in navigator) {
                const registrations = await navigator.serviceWorker.getRegistrations()
                for (const registration of registrations) {
                    await registration.unregister()
                }
            }
            // Clear caches
            if ('caches' in window) {
                const keys = await caches.keys()
                await Promise.all(keys.map(key => caches.delete(key)))
            }
            // Hard reload
            window.location.reload()
        } catch (error) {
            console.error('Hard refresh failed:', error)
            window.location.reload()
        }
    }

    const getMessage = () => {
        switch (pullState) {
            case 'pulling': return 'Pull to hard refresh...'
            case 'ready': return 'Release for HARD Refresh!'
            case 'refreshing': return 'Updating...'
            default: return ''
        }
    }

    if (pullState === 'idle') return null

    return (
        <div className={`refresh-indicator ${pullState}`}>
            {getMessage()}
        </div>
    )
}
