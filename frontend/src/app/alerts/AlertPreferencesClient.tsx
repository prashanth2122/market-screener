"use client";

import { useEffect, useMemo, useState } from "react";

type AlertPreferences = {
  alert_channel_telegram_enabled: boolean;
  alert_channel_email_enabled: boolean;
  alert_dispatch_symbol_limit: number;
  alert_dispatch_lookback_hours: number;
  alert_dispatch_signal_allowlist: string;
  alert_dispatch_min_score: number;
  alert_max_per_day: number;
  alert_cooldown_minutes: number;
};

const STORAGE_KEY = "marketScreener.alertPreferences.v1";

const DEFAULTS: AlertPreferences = {
  alert_channel_telegram_enabled: true,
  alert_channel_email_enabled: false,
  alert_dispatch_symbol_limit: 150,
  alert_dispatch_lookback_hours: 72,
  alert_dispatch_signal_allowlist: "strong_buy,buy",
  alert_dispatch_min_score: 70,
  alert_max_per_day: 5,
  alert_cooldown_minutes: 60,
};

function clampInt(value: number, minimum: number, maximum: number): number {
  if (!Number.isFinite(value)) {
    return minimum;
  }
  return Math.min(maximum, Math.max(minimum, Math.round(value)));
}

function clampFloat(value: number, minimum: number, maximum: number): number {
  if (!Number.isFinite(value)) {
    return minimum;
  }
  return Math.min(maximum, Math.max(minimum, value));
}

function parsePreferences(raw: unknown): AlertPreferences {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return DEFAULTS;
  }
  const record = raw as Record<string, unknown>;
  return {
    alert_channel_telegram_enabled: record.alert_channel_telegram_enabled !== false,
    alert_channel_email_enabled: record.alert_channel_email_enabled === true,
    alert_dispatch_symbol_limit: clampInt(
      Number(record.alert_dispatch_symbol_limit ?? DEFAULTS.alert_dispatch_symbol_limit),
      1,
      200,
    ),
    alert_dispatch_lookback_hours: clampInt(
      Number(record.alert_dispatch_lookback_hours ?? DEFAULTS.alert_dispatch_lookback_hours),
      1,
      24 * 30,
    ),
    alert_dispatch_signal_allowlist: String(
      record.alert_dispatch_signal_allowlist ?? DEFAULTS.alert_dispatch_signal_allowlist,
    ).trim(),
    alert_dispatch_min_score: clampFloat(
      Number(record.alert_dispatch_min_score ?? DEFAULTS.alert_dispatch_min_score),
      0,
      100,
    ),
    alert_max_per_day: clampInt(
      Number(record.alert_max_per_day ?? DEFAULTS.alert_max_per_day),
      1,
      50,
    ),
    alert_cooldown_minutes: clampInt(
      Number(record.alert_cooldown_minutes ?? DEFAULTS.alert_cooldown_minutes),
      1,
      24 * 60,
    ),
  };
}

function buildEnvOverrides(preferences: AlertPreferences): string {
  const lines = [
    `ALERT_CHANNEL_TELEGRAM_ENABLED=${preferences.alert_channel_telegram_enabled ? "true" : "false"}`,
    `ALERT_CHANNEL_EMAIL_ENABLED=${preferences.alert_channel_email_enabled ? "true" : "false"}`,
    `ALERT_DISPATCH_SYMBOL_LIMIT=${preferences.alert_dispatch_symbol_limit}`,
    `ALERT_DISPATCH_LOOKBACK_HOURS=${preferences.alert_dispatch_lookback_hours}`,
    `ALERT_DISPATCH_SIGNAL_ALLOWLIST=${preferences.alert_dispatch_signal_allowlist}`,
    `ALERT_DISPATCH_MIN_SCORE=${preferences.alert_dispatch_min_score}`,
    `ALERT_MAX_PER_DAY=${preferences.alert_max_per_day}`,
    `ALERT_COOLDOWN_MINUTES=${preferences.alert_cooldown_minutes}`,
  ];
  return lines.join("\n");
}

export default function AlertPreferencesClient() {
  const [loaded, setLoaded] = useState(false);
  const [preferences, setPreferences] = useState<AlertPreferences>(DEFAULTS);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        setPreferences(parsePreferences(JSON.parse(raw)));
      } else {
        setPreferences(DEFAULTS);
      }
    } catch {
      setPreferences(DEFAULTS);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!loaded) {
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // Ignore storage failures (private mode / quota).
    }
  }, [loaded, preferences]);

  const envOverrides = useMemo(() => buildEnvOverrides(preferences), [preferences]);

  const update = <K extends keyof AlertPreferences>(key: K, value: AlertPreferences[K]) => {
    setPreferences((current) => ({ ...current, [key]: value }));
  };

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(envOverrides);
      setCopyStatus("Copied to clipboard");
    } catch {
      setCopyStatus("Copy failed (select + copy manually)");
    }
    window.setTimeout(() => setCopyStatus(null), 2500);
  };

  return (
    <div className="prefs-shell">
      <div className="prefs-grid">
        <div className="prefs-card">
          <h3>Channels</h3>
          <p className="prefs-sub">
            These toggles control whether dispatch jobs will skip sending via that channel (via
            `.env`).
          </p>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={preferences.alert_channel_telegram_enabled}
              onChange={(event) => update("alert_channel_telegram_enabled", event.target.checked)}
            />
            <span>Telegram enabled</span>
          </label>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={preferences.alert_channel_email_enabled}
              onChange={(event) => update("alert_channel_email_enabled", event.target.checked)}
            />
            <span>Email enabled</span>
          </label>
        </div>

        <div className="prefs-card">
          <h3>Rules</h3>
          <p className="prefs-sub">
            Rule toggles for selecting actionable alerts (allowlist, thresholds, cooldown, daily
            cap).
          </p>

          <div className="prefs-fields">
            <label className="prefs-field">
              <span>Signals (CSV)</span>
              <input
                value={preferences.alert_dispatch_signal_allowlist}
                onChange={(event) =>
                  update("alert_dispatch_signal_allowlist", event.target.value)
                }
                placeholder="strong_buy,buy"
              />
            </label>
            <label className="prefs-field">
              <span>Min Score</span>
              <input
                inputMode="decimal"
                value={String(preferences.alert_dispatch_min_score)}
                onChange={(event) =>
                  update("alert_dispatch_min_score", Number(event.target.value || 0))
                }
              />
            </label>
            <label className="prefs-field">
              <span>Lookback (hours)</span>
              <input
                inputMode="numeric"
                value={String(preferences.alert_dispatch_lookback_hours)}
                onChange={(event) =>
                  update("alert_dispatch_lookback_hours", Number(event.target.value || 1))
                }
              />
            </label>
            <label className="prefs-field">
              <span>Symbol Limit</span>
              <input
                inputMode="numeric"
                value={String(preferences.alert_dispatch_symbol_limit)}
                onChange={(event) =>
                  update("alert_dispatch_symbol_limit", Number(event.target.value || 1))
                }
              />
            </label>
            <label className="prefs-field">
              <span>Max Per Day</span>
              <input
                inputMode="numeric"
                value={String(preferences.alert_max_per_day)}
                onChange={(event) => update("alert_max_per_day", Number(event.target.value || 1))}
              />
            </label>
            <label className="prefs-field">
              <span>Cooldown (minutes)</span>
              <input
                inputMode="numeric"
                value={String(preferences.alert_cooldown_minutes)}
                onChange={(event) =>
                  update("alert_cooldown_minutes", Number(event.target.value || 1))
                }
              />
            </label>
          </div>
        </div>

        <div className="prefs-card prefs-wide">
          <h3>Apply to `.env`</h3>
          <p className="prefs-sub">
            Preferences are saved in your browser, but the backend dispatch jobs read from `.env`.
            Copy these overrides into `.env`, then run dispatch scripts.
          </p>

          <div className="prefs-actions">
            <button type="button" className="primary-button" onClick={onCopy}>
              Copy `.env` overrides
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setPreferences(DEFAULTS)}
            >
              Reset defaults
            </button>
            {copyStatus ? <span className="prefs-status">{copyStatus}</span> : null}
          </div>

          <textarea className="prefs-textarea" readOnly value={envOverrides} rows={9} />

          <div className="prefs-footnote">
            <div>
              Telegram dispatch: <code>scripts/dev/run_telegram_alert_dispatch.ps1</code>
            </div>
            <div>
              Email dispatch: <code>scripts/dev/run_email_alert_dispatch.ps1</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
