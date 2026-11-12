"use client";

import { Button, Icon } from '../shared/ui';

export function LogoutConfirmation({ onCancel, onConfirm, busy = false }) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <section
        className="modal-card logout-confirmation"
        role="dialog"
        aria-modal="true"
        aria-labelledby="logout-title"
        aria-describedby="logout-description"
      >
        <div className="modal-header">
          <div>
            <h2 id="logout-title">Sign out of CareFlow?</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Close sign-out confirmation"
            disabled={busy}
            onClick={onCancel}
          >
            <Icon name="close" />
          </button>
        </div>
        <p className="modal-copy" id="logout-description">
          You’ll need to sign in again to return to your workspace.
        </p>
        <div className="modal-actions">
          <Button quiet disabled={busy} onClick={onCancel}>Stay signed in</Button>
          <button
            className="button button-danger"
            type="button"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      </section>
    </div>
  );
}
