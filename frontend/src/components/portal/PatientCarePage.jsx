"use client";

import { useCallback, useEffect, useState } from 'react';
import { EmptyInline, HeaderIntro, Metric, Panel, StatusBadge, dateLabel, pretty } from '../shared/ui';
import { AppointmentLine } from '../dashboard/Overview';
import { request } from '../../lib/api';

const localDateTime = value => {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

export function PatientCarePage({data,page,clinicId,notify,reload}) {
  const [appointments,setAppointments]=useState(data?.appointments||[]);
  const [doctors,setDoctors]=useState([]),[waitlist,setWaitlist]=useState([]),[busy,setBusy]=useState('');
  const [earliest,setEarliest]=useState(''),[latest,setLatest]=useState(''),[doctor,setDoctor]=useState(''),[reason,setReason]=useState('');
  const refreshPortal=useCallback(async()=>{
    try { const [d,w]=await Promise.all([
      request(`/auth/clinics/${clinicId}/portal/doctors`),
      request(`/auth/clinics/${clinicId}/portal/waitlist`),
    ]); setDoctors(d); setWaitlist(w); }
    catch(error) { notify(error.message); }
  },[clinicId,notify]);
  useEffect(()=>{setAppointments(data?.appointments||[])},[data?.appointments]);
  useEffect(()=>{if(clinicId)refreshPortal()},[clinicId,refreshPortal]);

  const joinWaitlist=async event=>{
    event.preventDefault();setBusy('join');
    try { await request(`/auth/clinics/${clinicId}/portal/waitlist`,{method:'POST',body:{earliest_at:new Date(earliest).toISOString(),latest_at:new Date(latest).toISOString(),requested_staff_member_id:doctor||null,reason:reason||null}});setEarliest('');setLatest('');setDoctor('');setReason('');await refreshPortal();notify('You joined the appointment waitlist'); }
    catch(error){notify(error.message)}finally{setBusy('')}
  };
  const leaveWaitlist=async entry=>{setBusy(entry.id);try{await request(`/auth/clinics/${clinicId}/portal/waitlist/${entry.id}`,{method:'DELETE'});await refreshPortal();notify('Waitlist request cancelled')}catch(error){notify(error.message)}finally{setBusy('')}};
  const acceptOffer=async entry=>{setBusy(entry.id);try{await request(`/auth/clinics/${clinicId}/portal/waitlist/${entry.id}/accept`,{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()}});await refreshPortal();reload();notify('Appointment confirmed from your waitlist offer')}catch(error){notify(error.message)}finally{setBusy('')}};
  const nowLocal=localDateTime(new Date().toISOString());

  return <><HeaderIntro eyebrow="YOUR HEALTH" title={page==='My care'?'Your care, all in one place.':'Your health records.'} description="A clear, private view of your health information."/>
    {page==='My care'&&<div className="metric-grid"><Metric label="Upcoming appointments" value={appointments.filter(a=>new Date(a.starts_at)>new Date()).length} icon="calendar"/><Metric label="Current medications" value={data?.medications?.length||0} icon="pulse" tone="lilac"/><Metric label="Known allergies" value={data?.allergies?.length||0} icon="note" tone="peach"/></div>}
    {page==='My care'&&<Panel title="Your care team" subtitle="Doctors currently assigned to your care"><div className="record-section">{doctors.map(d=><div className="record-line" key={d.staff_member_id}><span>{d.full_name}</span><span className="subtle-text">Assigned doctor</span></div>)}{!doctors.length&&<EmptyInline text="Your assigned doctors will appear here."/>}</div></Panel>}
    {page==='My care'&&<Panel title="Appointment waitlist" subtitle="Choose a date window and optionally request a doctor. You can have one active request at a time.">
      <form className="modal-form" onSubmit={joinWaitlist}><div className="field-row"><label className="field"><span>Available from</span><input type="datetime-local" min={nowLocal} value={earliest} onChange={e=>setEarliest(e.target.value)} required/></label><label className="field"><span>Available until</span><input type="datetime-local" min={earliest||nowLocal} value={latest} onChange={e=>setLatest(e.target.value)} required/></label></div><div className="field-row"><label className="field"><span>Doctor <span className="optional-label">Optional</span></span><select value={doctor} onChange={e=>setDoctor(e.target.value)}><option value="">Any assigned doctor</option>{doctors.map(d=><option key={d.staff_member_id} value={d.staff_member_id}>{d.full_name}</option>)}</select></label><label className="field"><span>Reason <span className="optional-label">Optional</span></span><input maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Reason for the appointment"/></label></div><button className="button button-primary" disabled={busy==='join'||!earliest||!latest}>{busy==='join'?'Joining…':'Join waitlist'}</button></form>
      <div className="table-wrap"><table><thead><tr><th>DATE WINDOW</th><th>DOCTOR</th><th>STATUS / OFFER</th><th/></tr></thead><tbody>{waitlist.map(entry=>{const offered=doctors.find(d=>d.staff_member_id===entry.requested_staff_member_id)?.full_name||'Any assigned doctor';return <tr key={entry.id}><td>{dateLabel(entry.earliest_at)} – {dateLabel(entry.latest_at)}</td><td>{offered}</td><td><StatusBadge value={entry.status}/>{entry.offered_starts_at&&<small className="sub-cell">{dateLabel(entry.offered_starts_at)} · offer expires {entry.offer_expires_at?new Date(entry.offer_expires_at).toLocaleString(): 'soon'}</small>}</td><td><div className="table-actions">{entry.status==='offered'&&<button className="button button-primary compact" disabled={busy===entry.id} onClick={()=>acceptOffer(entry)}>Accept offer</button>}{['waiting','offered'].includes(entry.status)&&<button className="button button-quiet compact" disabled={busy===entry.id} onClick={()=>leaveWaitlist(entry)}>Cancel</button>}</div></td></tr>})}</tbody></table>{!waitlist.length&&<EmptyInline text="You have no active waitlist requests."/>}</div>
    </Panel>}
    <div className="content-grid"><Panel title="Appointments" subtitle="Your scheduled care">{appointments.map(a=><AppointmentLine key={a.id} item={a}/>)}{!appointments.length&&<EmptyInline text="No appointments to show."/>}</Panel><Panel title="Medications & allergies" subtitle="Information shared with your care team"><div className="record-section"><strong>Medications</strong>{(data?.medications||[]).map(m=><div className="record-line" key={m.id}><span>{m.name}</span><small>{m.dose} · {m.frequency}</small></div>)}{!data?.medications?.length&&<p className="subtle-text">No active medications listed.</p>}</div><div className="record-section"><strong>Allergies</strong>{(data?.allergies||[]).map(a=><div className="record-line" key={a.id}><span>{a.substance}</span><StatusBadge value={a.severity||a.status}/></div>)}{!data?.allergies?.length&&<p className="subtle-text">No known allergies listed.</p>}</div></Panel></div>
    <Panel title="Signed clinical notes" subtitle="Your doctor’s signed visit notes">{(data?.signed_notes||[]).map(n=><article className="clinical-note" key={n.id}><div className="note-meta">Signed {dateLabel(n.signed_at)}</div><p>{n.content}</p></article>)}{!data?.signed_notes?.length&&<EmptyInline text="Signed visit notes will appear here."/>}</Panel><Panel title="Signed orders" subtitle="Prescriptions and lab orders"><div className="table-wrap"><table><thead><tr><th>TYPE</th><th>DETAILS</th><th>STATUS</th><th>SIGNED</th></tr></thead><tbody>{(data?.signed_orders||[]).map(o=><tr key={o.id}><td>{pretty(o.order_type)}</td><td>{o.details?.name||o.notes||'—'}</td><td><StatusBadge value={o.status}/></td><td>{dateLabel(o.signed_at)}</td></tr>)}</tbody></table></div></Panel>
  </>;
}
