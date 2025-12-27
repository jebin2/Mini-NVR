export const CONFIG = {
    apiBase: '/api',
    go2rtcPort: 1984,              // go2rtc streaming server port
    gridRefreshInterval: 10000,    // 10 seconds - live channel status refresh
    storageRefreshInterval: 60000, // 60 seconds - storage usage refresh
    liveThresholdSeconds: 15       // Consider file "live" if modified within this time
};
