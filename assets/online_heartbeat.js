(function () {
    function sendBye() {
        try {
            var sid = sessionStorage.getItem('client-id');
            if (!sid) return;
            var data = JSON.stringify({ session_id: sid });
            if (navigator.sendBeacon) {
                var blob = new Blob([data], { type: 'application/json' });
                navigator.sendBeacon('/bye', blob);
            } else {
                // Fallback (async fire-and-forget)
                fetch('/bye', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: data, keepalive: true }).catch(() => { });
            }
        } catch (e) { }
    }
    // Tab wird geschlossen oder wechselt Seite
    window.addEventListener('beforeunload', sendBye);
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') sendBye();
    });
})();
