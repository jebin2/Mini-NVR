import './App.css'
import MainApp from './components/MainApp'
import PullToRefresh from './components/PullToRefresh'
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
      <>
        <PullToRefresh />
        <div className="login-wrapper">
          <div className="login-card">
            <div className="login-header">
              <img src="/icon-192.png" alt="See Me" className="login-logo" />
              <h2>See Me</h2>
            </div>
            <div className="login-content">
              <GoogleSignInButton width={300} />
            </div>
          </div>
        </div>
      </>
    )
  }

  // Show main app with pull-to-refresh
  return (
    <>
      <PullToRefresh />
      <MainApp user={user} />
    </>
  )
}

export default App

