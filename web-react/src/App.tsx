import './App.css'
import MainApp from './components/MainApp'
import {
  useGoogleAuth,
  GoogleSignInButton,
} from '@jebin2/googleauthservice/client/src'

function App() {
  const { user, loading } = useGoogleAuth()

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading session...</p>
      </div>
    )
  }

  // Show login if not authenticated
  if (!user) {
    return (
      <div className="login-container" style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        gap: '20px'
      }}>
        <h1>Mini-NVR Login</h1>
        <GoogleSignInButton width={300} />
      </div>
    )
  }

  // Show main app
  return <MainApp user={user} />
}

export default App
