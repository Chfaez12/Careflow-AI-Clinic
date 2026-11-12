"use client";

import { useState } from 'react';
import {
  Button,
  EmptyInline,
  HeaderIntro,
  Icon,
  Panel,
  SearchTools,
  StatusBadge,
  dateLabel,
  pretty,
} from '../shared/ui';
import { request } from '../../lib/api';

export function PlatformPage({ page, data, setSearch, search, notify, reload }) {
  const items = Array.isArray(data) ? data : [];
  const [detail, setDetail] = useState(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [clinicAction, setClinicAction] = useState('');
  const [confirmName, setConfirmName] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const isClinics = page === 'Clinics';

  const closeDetail = () => {
    if (detailBusy || actionBusy) return;
    setDetail(null);
    setClinicAction('');
    setConfirmName('');
    setDetailError('');
    setActionError('');
  };

  const openUser = async (userId) => {
    setDetail({ kind: 'user', data: null });
    setDetailBusy(true);
    setDetailError('');
    try {
      const result = await request(`/auth/platform/users/${userId}`);
      setDetail({ kind: 'user', data: result });
    } catch (error) {
      setDetailError(error.message);
    } finally {
      setDetailBusy(false);
    }
  };

  const openClinic = async (clinicId) => {
    setDetail({ kind: 'clinic', data: null, members: [] });
    setDetailBusy(true);
    setDetailError('');
    try {
      const [clinic, members] = await Promise.all([
        request(`/auth/platform/clinics/${clinicId}`),
        request(`/auth/platform/clinics/${clinicId}/members`),
      ]);
      setDetail({ kind: 'clinic', data: clinic, members });
    } catch (error) {
      setDetailError(error.message);
    } finally {
      setDetailBusy(false);
    }
  };

  const submitClinicAction = async (event) => {
    event.preventDefault();
    if (!detail?.data?.id || !clinicAction) return;
    setActionBusy(true);
    setActionError('');
    try {
      const path = `/auth/platform/clinics/${detail.data.id}`;
      const body = { confirm_clinic_name: confirmName };
      if (clinicAction === 'delete') {
        await request(path, { method: 'DELETE', body });
        notify('Clinic deleted');
      } else {
        await request(`${path}/restore`, { method: 'POST', body });
        notify('Clinic restored');
      }
      setClinicAction('');
      setConfirmName('');
      setDetail(null);
      reload();
    } catch (error) {
      setActionError(error.message);
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <>
      <HeaderIntro
        eyebrow="PLATFORM ADMINISTRATION"
        title={isClinics ? 'Clinic community' : 'People on CareFlow'}
        description={isClinics
          ? 'Review clinic workspaces, membership, and access.'
          : 'Find people and review their platform access.'}
      />
      <Panel
        title={page}
        subtitle={`${items.length} records`}
        action={<SearchTools value={search} onChange={setSearch} placeholder={`Search ${page.toLowerCase()}`} />}
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {isClinics ? <><th>CLINIC</th><th>SLUG</th><th>CONTACT</th><th>STATUS</th><th /></> : <><th>PERSON</th><th>EMAIL</th><th>ROLE</th><th>STATUS</th><th /> </>}
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={item.id}>
                  {isClinics ? <>
                    <td><div className="patient-cell"><div className={`avatar avatar-${index % 4}`}><Icon name="building" size={17} /></div><strong>{item.name}</strong></div></td>
                    <td className="mono-id">{item.slug}</td>
                    <td>{item.email || '—'}</td>
                    <td><StatusBadge value={item.deleted_at ? 'Deleted' : item.is_active ? 'Active' : 'Inactive'} /></td>
                  </> : <>
                    <td><strong>{item.full_name || 'CareFlow user'}</strong></td>
                    <td>{item.email}</td>
                    <td>{item.is_super_admin ? 'Platform owner' : pretty(item.role || 'Clinic member')}</td>
                    <td><StatusBadge value={item.deleted_at ? 'Deleted' : item.is_active ? 'Active' : 'Inactive'} /></td>
                  </>}
                  <td><button className="button button-quiet compact" onClick={() => isClinics ? openClinic(item.id) : openUser(item.id)}>View details</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <EmptyInline text={`No ${page.toLowerCase()} found.`} />}
        </div>
      </Panel>

      {detail && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDetail(); }}>
          <section className="modal-card platform-detail-card" role="dialog" aria-modal="true" aria-labelledby="platform-detail-title">
            <div className="modal-header">
              <div>
                <span className="eyebrow muted-eyebrow">{detail.kind === 'clinic' ? 'CLINIC WORKSPACE' : 'PLATFORM USER'}</span>
                <h2 id="platform-detail-title">{detail.data?.name || detail.data?.profile?.full_name || (detailBusy ? 'Loading details…' : 'Details')}</h2>
              </div>
              <button className="icon-button" type="button" aria-label="Close details" disabled={detailBusy || actionBusy} onClick={closeDetail}><Icon name="close" /></button>
            </div>
            {detailError && <div className="form-message">{detailError}</div>}
            {detailBusy && <div className="page-loading"><span className="spinner dark" />Loading details…</div>}
            {!detailBusy && detail.data && detail.kind === 'clinic' && (
              <>
                <div className="platform-detail-grid">
                  <DetailItem label="Clinic name" value={detail.data.name} />
                  <DetailItem label="Slug" value={detail.data.slug} />
                  <DetailItem label="Contact email" value={detail.data.email} />
                  <DetailItem label="Phone" value={detail.data.phone} />
                  <DetailItem label="Timezone" value={detail.data.timezone} />
                  <DetailItem label="Created" value={dateLabel(detail.data.created_at)} />
                  <DetailItem label="Members" value={detail.data.member_count} />
                  <div className="platform-detail-item"><span>Status</span><StatusBadge value={detail.data.deleted_at ? 'Deleted' : detail.data.is_active ? 'Active' : 'Inactive'} /></div>
                </div>
                <Panel title="Clinic members" subtitle={`${detail.members?.length || 0} memberships`}>
                  <div className="table-wrap">
                    <table><thead><tr><th>NAME</th><th>EMAIL</th><th>ROLE</th><th>STATUS</th></tr></thead>
                      <tbody>{(detail.members || []).map((member) => <tr key={member.membership.id}><td>{member.profile.full_name || 'CareFlow user'}</td><td>{member.profile.email}</td><td>{pretty(member.membership.role)}</td><td><StatusBadge value={pretty(member.membership.status)} /></td></tr>)}</tbody>
                    </table>
                    {!detail.members?.length && <EmptyInline text="No clinic members found." />}
                  </div>
                </Panel>
                <div className="platform-detail-actions">
                  {detail.data.deleted_at
                    ? <button className="button button-primary" onClick={() => { setClinicAction('restore'); setActionError(''); }}>Restore clinic</button>
                    : <button className="button button-danger" onClick={() => { setClinicAction('delete'); setActionError(''); }}>Delete clinic</button>}
                </div>
                {clinicAction && <form className="platform-confirm-form" onSubmit={submitClinicAction}>
                  <strong>{clinicAction === 'delete' ? 'Confirm clinic deletion' : 'Confirm clinic restoration'}</strong>
                  <p className="modal-copy">Type <b>{detail.data.name}</b> to confirm. {clinicAction === 'delete' ? 'This removes the clinic from active access; it can be restored later.' : 'This restores the clinic using its previous active status.'}</p>
                  <input aria-label="Confirm clinic name" value={confirmName} onChange={(event) => setConfirmName(event.target.value)} required minLength={2} maxLength={150} />
                  {actionError && <div className="form-message">{actionError}</div>}
                  <div className="modal-actions"><Button quiet type="button" disabled={actionBusy} onClick={() => { setClinicAction(''); setConfirmName(''); setActionError(''); }}>Cancel</Button><button className={clinicAction === 'delete' ? 'button button-danger' : 'button button-primary'} disabled={actionBusy || confirmName.trim().toLocaleLowerCase() !== detail.data.name.trim().toLocaleLowerCase()}>{actionBusy ? 'Saving…' : clinicAction === 'delete' ? 'Delete clinic' : 'Restore clinic'}</button></div>
                </form>}
              </>
            )}
            {!detailBusy && detail.data && detail.kind === 'user' && (
              <>
                <div className="platform-detail-grid">
                  <DetailItem label="Full name" value={detail.data.profile.full_name} />
                  <DetailItem label="Email" value={detail.data.profile.email} />
                  <DetailItem label="Phone" value={detail.data.profile.phone_number} />
                  <DetailItem label="Created" value={dateLabel(detail.data.profile.created_at)} />
                  <DetailItem label="Platform owner" value={detail.data.profile.is_super_admin ? 'Yes' : 'No'} />
                  <div className="platform-detail-item"><span>Status</span><StatusBadge value={detail.data.profile.deleted_at ? 'Deleted' : detail.data.profile.is_active ? 'Active' : 'Inactive'} /></div>
                </div>
                <Panel title="Clinic memberships" subtitle={`${detail.data.memberships?.length || 0} memberships`}>
                  <div className="table-wrap"><table><thead><tr><th>CLINIC</th><th>ROLE</th><th>STATUS</th></tr></thead>
                    <tbody>{(detail.data.memberships || []).map((membership) => <tr key={membership.id}><td>{membership.clinic?.name || membership.clinic_id}</td><td>{pretty(membership.role)}</td><td><StatusBadge value={pretty(membership.status)} /></td></tr>)}</tbody>
                  </table>{!detail.data.memberships?.length && <EmptyInline text="This user has no clinic memberships." />}</div>
                </Panel>
              </>
            )}
            <div className="modal-actions"><Button quiet disabled={detailBusy || actionBusy} onClick={closeDetail}>Close</Button></div>
          </section>
        </div>
      )}
    </>
  );
}

function DetailItem({ label, value }) {
  return <div className="platform-detail-item"><span>{label}</span><strong>{value ?? '—'}</strong></div>;
}
