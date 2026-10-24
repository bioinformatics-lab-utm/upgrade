import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import './Profile.css';

const ROLE_LABELS = {
  lab_technician: 'Lab technician',
  public_health_official: 'Public health official',
  researcher: 'Researcher',
  admin: 'Administrator',
};

// Same rules as the backend (routes/auth.py: validate_password)
const PASSWORD_RULES = [
  { label: 'At least 8 characters', test: (p) => p.length >= 8 },
  { label: 'One uppercase letter', test: (p) => /[A-Z]/.test(p) },
  { label: 'One lowercase letter', test: (p) => /[a-z]/.test(p) },
  { label: 'One digit', test: (p) => /\d/.test(p) },
  { label: 'One special character', test: (p) => /[!@#$%^&*(),.?":{}|<>]/.test(p) },
];

const formatDate = (iso, withTime = false) => {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
};

const errorMessage = (err, fallback) =>
  err.response?.data?.error || (err.response ? fallback : 'Network error. Please check your connection.');

function Message({ message }) {
  if (!message) return null;
  return (
    <div className={`profile-message profile-message-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>
      {message.text}
    </div>
  );
}

function Profile({ user: sessionUser, onUserUpdate, onLogout }) {
  const [profile, setProfile] = useState(null);
  const [loadError, setLoadError] = useState('');

  const [fullName, setFullName] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState(null);

  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' });
  const [showPasswords, setShowPasswords] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState(null);

  // null until loaded
  const [emailNotifications, setEmailNotifications] = useState(null);
  const [savingNotifications, setSavingNotifications] = useState(false);
  const [notificationMessage, setNotificationMessage] = useState(null);

  const loadProfile = useCallback(async () => {
    try {
      const { data } = await api.get('/api/auth/me');
      setProfile(data.user);
      setFullName(data.user.full_name || '');
      setLoadError('');
    } catch (err) {
      setLoadError(errorMessage(err, 'Could not load your profile.'));
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    api.get('/api/notifications/preferences')
      .then(({ data }) => setEmailNotifications(Boolean(data.preferences?.email)))
      .catch((err) => setNotificationMessage({ type: 'error', text: errorMessage(err, 'Could not load your notification settings.') }));
  }, []);

  const handleEmailNotificationsChange = async (e) => {
    const enabled = e.target.checked;
    setNotificationMessage(null);
    setSavingNotifications(true);
    try {
      const { data } = await api.put('/api/notifications/preferences', { email: enabled });
      setEmailNotifications(Boolean(data.preferences.email));
      setNotificationMessage({
        type: 'success',
        text: enabled ? 'You will get an email when an analysis finishes.' : 'Emails turned off. Notifications still appear under the bell icon.',
      });
    } catch (err) {
      setNotificationMessage({ type: 'error', text: errorMessage(err, 'Could not save your notification settings.') });
    } finally {
      setSavingNotifications(false);
    }
  };

  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    setProfileMessage(null);
    setSavingProfile(true);
    try {
      const { data } = await api.put('/api/auth/me', { full_name: fullName });
      setProfile(data.user);
      setFullName(data.user.full_name || '');
      onUserUpdate?.({ full_name: data.user.full_name });
      setProfileMessage({ type: 'success', text: 'Profile saved.' });
    } catch (err) {
      setProfileMessage({ type: 'error', text: errorMessage(err, 'Could not save your profile.') });
    } finally {
      setSavingProfile(false);
    }
  };

  const handlePasswordChange = (e) => {
    setPasswords({ ...passwords, [e.target.name]: e.target.value });
    setPasswordMessage(null);
  };

  const rules = PASSWORD_RULES.map((rule) => ({ ...rule, met: rule.test(passwords.next) }));
  const confirmMismatch = passwords.confirm !== '' && passwords.confirm !== passwords.next;
  const sameAsCurrent = passwords.next !== '' && passwords.next === passwords.current;
  const canSubmitPassword =
    passwords.current !== '' &&
    rules.every((rule) => rule.met) &&
    passwords.confirm === passwords.next &&
    !sameAsCurrent;

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmitPassword) return;
    setPasswordMessage(null);
    setSavingPassword(true);
    try {
      await api.post('/api/auth/change-password', {
        current_password: passwords.current,
        new_password: passwords.next,
      });
      setPasswords({ current: '', next: '', confirm: '' });
      setPasswordMessage({ type: 'success', text: 'Password changed. Use the new password next time you sign in.' });
      loadProfile();
    } catch (err) {
      setPasswordMessage({ type: 'error', text: errorMessage(err, 'Could not change your password.') });
    } finally {
      setSavingPassword(false);
    }
  };

  // Show what the session already knows while the full profile loads
  const shown = profile || sessionUser || {};
  const username = shown.username || '';
  const passwordInputType = showPasswords ? 'text' : 'password';
  const nameUnchanged = fullName.trim() === (profile?.full_name || '');

  return (
    <div className="profile-page">
      <header className="profile-hero">
        <div className="profile-hero-avatar" aria-hidden="true">
          {username.substring(0, 2).toUpperCase()}
        </div>
        <div className="profile-hero-text">
          <h1>{shown.full_name || username}</h1>
          <p>
            @{username}
            {profile?.user_type && (
              <span className="profile-badge">{ROLE_LABELS[profile.user_type] || profile.user_type}</span>
            )}
          </p>
        </div>
        <button type="button" className="profile-button profile-button-secondary" onClick={onLogout}>
          Sign out
        </button>
      </header>

      {loadError && (
        <div className="profile-message profile-message-error" role="alert">
          {loadError}
          <button type="button" className="profile-link-button" onClick={loadProfile}>Try again</button>
        </div>
      )}

      <div className="profile-grid">
        <section className="profile-card" aria-labelledby="profile-account-title">
          <h2 id="profile-account-title">Account</h2>

          <dl className="profile-details">
            <div>
              <dt>Username</dt>
              <dd>{username || '—'}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>
                {shown.email || '—'}
                {profile && profile.email_verified !== undefined && (
                  <span className={`profile-badge ${profile.email_verified ? 'profile-badge-success' : 'profile-badge-warning'}`}>
                    {profile.email_verified ? 'Verified' : 'Not verified'}
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt>Member since</dt>
              <dd>{formatDate(profile?.created_at)}</dd>
            </div>
            <div>
              <dt>Last sign-in</dt>
              <dd>{formatDate(profile?.last_login, true)}</dd>
            </div>
          </dl>

          <form onSubmit={handleProfileSubmit} className="profile-form">
            <div className="profile-field">
              <label htmlFor="profile-full-name">Full name</label>
              <input
                type="text"
                id="profile-full-name"
                value={fullName}
                onChange={(e) => { setFullName(e.target.value); setProfileMessage(null); }}
                placeholder="Your name"
                maxLength={100}
                autoComplete="name"
                disabled={!profile}
              />
            </div>

            <Message message={profileMessage} />

            <button
              type="submit"
              className="profile-button profile-button-primary"
              disabled={!profile || savingProfile || nameUnchanged}
            >
              {savingProfile ? 'Saving…' : 'Save changes'}
            </button>
          </form>
        </section>

        <section className="profile-card" aria-labelledby="profile-password-title">
          <h2 id="profile-password-title">Password</h2>
          <p className="profile-card-hint">
            {profile?.password_changed_at
              ? `Last changed on ${formatDate(profile.password_changed_at)}.`
              : 'Choose a strong password that you do not use elsewhere.'}
          </p>

          <form onSubmit={handlePasswordSubmit} className="profile-form">
            {/* Lets password managers attach the new password to the right account */}
            <input type="text" name="username" value={username} autoComplete="username" readOnly hidden />

            <div className="profile-field">
              <label htmlFor="profile-current-password">Current password</label>
              <input
                type={passwordInputType}
                id="profile-current-password"
                name="current"
                value={passwords.current}
                onChange={handlePasswordChange}
                autoComplete="current-password"
                required
              />
            </div>

            <div className="profile-field">
              <label htmlFor="profile-new-password">New password</label>
              <input
                type={passwordInputType}
                id="profile-new-password"
                name="next"
                value={passwords.next}
                onChange={handlePasswordChange}
                autoComplete="new-password"
                aria-describedby="profile-password-rules"
                required
              />
              {sameAsCurrent && (
                <span className="profile-field-error">The new password must be different from the current one.</span>
              )}
            </div>

            <ul id="profile-password-rules" className="profile-rules">
              {rules.map((rule) => (
                <li key={rule.label} className={rule.met ? 'met' : ''}>
                  <span aria-hidden="true">{rule.met ? '✓' : '○'}</span>
                  {rule.label}
                </li>
              ))}
            </ul>

            <div className="profile-field">
              <label htmlFor="profile-confirm-password">Confirm new password</label>
              <input
                type={passwordInputType}
                id="profile-confirm-password"
                name="confirm"
                value={passwords.confirm}
                onChange={handlePasswordChange}
                autoComplete="new-password"
                aria-invalid={confirmMismatch}
                required
              />
              {confirmMismatch && (
                <span className="profile-field-error">The passwords do not match.</span>
              )}
            </div>

            <label className="profile-checkbox">
              <input
                type="checkbox"
                checked={showPasswords}
                onChange={(e) => setShowPasswords(e.target.checked)}
              />
              Show passwords
            </label>

            <Message message={passwordMessage} />

            <button
              type="submit"
              className="profile-button profile-button-primary"
              disabled={!canSubmitPassword || savingPassword}
            >
              {savingPassword ? 'Changing…' : 'Change password'}
            </button>
          </form>
        </section>

        <section className="profile-card" aria-labelledby="profile-notifications-title">
          <h2 id="profile-notifications-title">Notifications</h2>
          <p className="profile-card-hint">
            The bell icon in the header shows when your samples start running and when their analysis finishes.
          </p>

          <label className="profile-switch">
            <span className="profile-switch-text">
              <span className="profile-switch-label">Email me when an analysis finishes</span>
              <span className="profile-switch-hint">
                Sent to {shown.email || 'your email address'} when a sample completes or fails.
              </span>
            </span>
            <input
              type="checkbox"
              role="switch"
              checked={Boolean(emailNotifications)}
              onChange={handleEmailNotificationsChange}
              disabled={emailNotifications === null || savingNotifications}
            />
            <span className="profile-switch-track" aria-hidden="true" />
          </label>

          <Message message={notificationMessage} />
        </section>
      </div>
    </div>
  );
}

export default Profile;
