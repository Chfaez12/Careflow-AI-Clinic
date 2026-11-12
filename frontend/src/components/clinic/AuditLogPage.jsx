"use client";

import { useState } from 'react';
import { Button, EmptyInline, HeaderIntro, Panel, StatusBadge, dateLabel } from '../shared/ui';
import { request, downloadFile } from '../../lib/api';

export function AuditLogPage({ data, clinicId, notify }) {
  const [events, setEvents] = useState(Array.isArray(data) ? data : []);
  const [patientId, setPatientId] = useState('');
  const [action, setAction] = useState('');
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async (nextOffset = 0) => {
    setBusy(true);
    setError('');
    try {
      const params = new URLSearchParams({ limit: '100', offset: String(nextOffset) });
      if (patientId.trim()) params.set('patient_id', patientId.trim());
      if (action.trim()) params.set('action', action.trim());
      const result = await request(`/auth/clinics/${clinicId}/audit-log?${params}`);
      setEvents(result);
      setOffset(nextOffset);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const exportPatient = async (format) => {
    if (!patientId.trim()) {
      setError('Enter a patient ID to export that patient’s audit history.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const path = `/auth/clinics/${clinicId}/audit-log/patients/${patientId.trim()}/export.${format}`;
      await downloadFile(path, `patient-audit.${format}`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return <>
    <HeaderIntro eyebrow="CLINIC GOVERNANCE" title="Audit log" description="Review access and activity recorded for your clinic." />
    <Panel title="Filter activity" subtitle="Filter by patient or action. Patient exports include the complete audit history for that patient.">
      <form className="audit-filter-form" onSubmit={(event) => { event.preventDefault(); load(0); }}>
        <label className="field"><span>Patient ID <small>(optional UUID)</small></span><input value={patientId} onChange={(event) => setPatientId(event.target.value)} placeholder="Patient UUID" /></label>
        <label className="field"><span>Action <small>(optional)</small></span><input value={action} onChange={(event) => setAction(event.target.value)} placeholder="e.g. patient.updated" /></label>
        <div className="audit-filter-actions"><Button type="submit" disabled={busy}>{busy ? 'Loading…' : 'Apply filters'}</Button><Button quiet type="button" disabled={busy || !patientId.trim()} onClick={() => exportPatient('csv')}>Export CSV</Button><Button quiet type="button" disabled={busy || !patientId.trim()} onClick={() => exportPatient('pdf')}>Export PDF</Button></div>
      </form>
      {error && <div className="form-message">{error}</div>}
    </Panel>
    <Panel title="Recorded events" subtitle={`${events.length} events on this page`}>
      <div className="table-wrap"><table><thead><tr><th>WHEN</th><th>ACTION</th><th>RESOURCE</th><th>PATIENT</th><th>ACTOR</th><th>DETAILS</th></tr></thead><tbody>
        {events.map((event) => <tr key={event.id}><td>{dateLabel(event.created_at)}<small className="sub-cell">{new Date(event.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</small></td><td><strong>{event.action}</strong></td><td>{event.resource_type}<small className="sub-cell">{event.resource_id || '—'}</small></td><td className="mono-id">{event.patient_id || '—'}</td><td className="mono-id">{event.actor_user_id || event.actor_staff_id || 'System'}</td><td>{event.details ? JSON.stringify(event.details) : '—'}</td></tr>)}
      </tbody></table>{!events.length && <EmptyInline text="No audit events match these filters." />}</div>
      <div className="audit-pagination"><Button quiet disabled={busy || offset === 0} onClick={() => load(Math.max(0, offset - 100))}>Previous</Button><span>Rows {offset + 1}–{offset + events.length}</span><Button quiet disabled={busy || events.length < 100} onClick={() => load(offset + 100)}>Next</Button></div>
    </Panel>
  </>;
}
