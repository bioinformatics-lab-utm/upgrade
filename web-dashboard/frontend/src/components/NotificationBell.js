import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import './NotificationBell.css';

const POLL_INTERVAL_MS = 30000;

const TYPE_META = {
  pipeline_running: { tone: 'info', icon: 'play' },
  pipeline_completed: { tone: 'success', icon: 'check' },
  pipeline_failed: { tone: 'danger', icon: 'alert' },
  pipeline_cancelled: { tone: 'muted', icon: 'stop' },
};

function TypeIcon({ icon }) {
  const common = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round' };
  switch (icon) {
    case 'play':
      return <svg {...common}><polygon points="7 4 19 12 7 20 7 4" /></svg>;
    case 'check':
      return <svg {...common}><polyline points="20 6 9 17 4 12" /></svg>;
    case 'alert':
      return <svg {...common}><line x1="12" y1="7" x2="12" y2="13" /><circle cx="12" cy="17" r="0.6" fill="currentColor" /></svg>;
    default:
      return <svg {...common}><rect x="6" y="6" width="12" height="12" rx="1.5" /></svg>;
  }
}

const relativeTime = (iso) => {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
};

// Where clicking a notification takes the user
const targetOf = (n) => {
  if (n.type === 'pipeline_completed') return `/results/${n.sample_code || n.pipeline_id}`;
  return n.pipeline_id ? `/pipeline/${n.pipeline_id}/monitor` : null;
};

function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const containerRef = useRef(null);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/notifications', { params: { limit: 20 }, timeout: 15000 });
      setNotifications(data.notifications || []);
      setUnread(data.unread_count || 0);
      setLoadFailed(false);
    } catch (err) {
      setLoadFailed(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  // Poll while the tab is visible, and refresh as soon as it becomes visible again
  useEffect(() => {
    load();
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') load();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [load]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const toggle = () => {
    if (!open) load();
    setOpen(!open);
  };

  const markRead = (id) => {
    setNotifications((list) => list.map((n) => (n.notification_id === id ? { ...n, read: true } : n)));
    setUnread((count) => Math.max(0, count - 1));
    api.post(`/api/notifications/${id}/read`).catch(() => load());
  };

  const markAllRead = () => {
    setNotifications((list) => list.map((n) => ({ ...n, read: true })));
    setUnread(0);
    api.post('/api/notifications/read-all').catch(() => load());
  };

  const openNotification = (n) => {
    if (!n.read) markRead(n.notification_id);
    const target = targetOf(n);
    setOpen(false);
    if (target) navigate(target);
  };

  const badge = unread > 9 ? '9+' : String(unread);

  return (
    <div className="notification-bell" ref={containerRef}>
      <button
        type="button"
        className={`action-btn ${open ? 'is-open' : ''}`}
        onClick={toggle}
        title="Notifications"
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-haspopup="true"
        aria-expanded={open}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        {unread > 0 && <span className="notification-badge">{badge}</span>}
      </button>

      {open && (
        <div className="notification-panel" role="dialog" aria-label="Notifications">
          <div className="notification-panel-header">
            <h3>Notifications</h3>
            {unread > 0 && (
              <button type="button" className="notification-link-button" onClick={markAllRead}>
                Mark all as read
              </button>
            )}
          </div>

          <div className="notification-list">
            {!loaded && <div className="notification-empty">Loading…</div>}

            {loaded && loadFailed && notifications.length === 0 && (
              <div className="notification-empty">
                Could not load notifications.
                <button type="button" className="notification-link-button" onClick={load}>Try again</button>
              </div>
            )}

            {loaded && !loadFailed && notifications.length === 0 && (
              <div className="notification-empty">
                <strong>No notifications yet</strong>
                You will see here when your samples start running and when their analysis finishes.
              </div>
            )}

            {notifications.map((n) => {
              const meta = TYPE_META[n.type] || TYPE_META.pipeline_cancelled;
              return (
                <button
                  type="button"
                  key={n.notification_id}
                  className={`notification-item ${n.read ? '' : 'unread'}`}
                  onClick={() => openNotification(n)}
                >
                  <span className={`notification-icon tone-${meta.tone}`} aria-hidden="true">
                    <TypeIcon icon={meta.icon} />
                  </span>
                  <span className="notification-body">
                    <span className="notification-title">{n.title}</span>
                    <span className="notification-message">{n.message}</span>
                    <span className="notification-time">{relativeTime(n.created_at)}</span>
                  </span>
                  {!n.read && <span className="notification-dot" aria-label="Unread" />}
                </button>
              );
            })}
          </div>

          <div className="notification-panel-footer">
            <Link to="/profile" onClick={() => setOpen(false)}>Email notification settings</Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default NotificationBell;
