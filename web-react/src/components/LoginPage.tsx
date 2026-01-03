import { useEffect } from 'react'
import { GoogleSignInButton } from '@jebin2/googleauthservice/client/src'
import './LoginPage.css'

interface LoginPageProps {
    onLoginSuccess: () => void
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
    // const googleButtonRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        // Trigger a session check after successful Google login
        const handleMessage = () => {
            onLoginSuccess()
        }

        // Listen for auth state changes
        window.addEventListener('auth-success', handleMessage)
        return () => window.removeEventListener('auth-success', handleMessage)
    }, [onLoginSuccess])

    return (
        <div className="login-wrapper">
            <div className="login-card">
                <div className="login-header">
                    <h2>📺 See Me</h2>
                    <p>NVR System Authentication</p>
                </div>

                <div className="login-content">
                    <GoogleSignInButton
                        width={300}
                        text="Sign in with Google"
                    />
                </div>
            </div>
        </div>
    )
}
