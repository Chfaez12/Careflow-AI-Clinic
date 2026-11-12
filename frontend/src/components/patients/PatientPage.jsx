"use client";

import { useState } from 'react';
import { Button, EmptyInline, HeaderIntro, Icon, Panel, SearchTools, StatusBadge, dateLabel, initials, pretty, timeLabel } from '../shared/ui';
import { request, downloadFile } from '../../lib/api';

export function PatientPage({ role, data, search, setSearch, setModal, clinicId, reload, notify }) {
  const patients = Array.isArray(data) ? data : data?.items || [];
  const canCreate = !['patient', 'nurse'].includes(role);
  const isClinicAdmin = role === 'clinic_admin';
  const isDoctor = role === 'doctor';
  const isNurse = role === 'nurse';
  const [chart, setChart] = useState(null);
  const [chartBusy, setChartBusy] = useState(false);
  const [chartError, setChartError] = useState('');
  const [saving, setSaving] = useState(false);
  const [edit, setEdit] = useState(false);
  const [staffOptions, setStaffOptions] = useState([]);
  const [staffId, setStaffId] = useState('');
  const [timelineOffset, setTimelineOffset] = useState(0);
  const [timelineBusy, setTimelineBusy] = useState(false);

  const openChart = async (patientId) => {
    setChart({ patient: null, timeline: [], assignments: [] });
    setChartBusy(true);
    setChartError('');
    setEdit(false);
    try {
      if (isDoctor) {
        const doctorChart = await request(`/auth/clinics/${clinicId}/doctor/patients/${patientId}/chart`);
        setChart({ ...doctorChart, doctorChart: true, timeline: [], timelineHasMore: false });
        return;
      }
      const tasks = [
        request(`/auth/clinics/${clinicId}/patients/${patientId}`),
        request(`/auth/clinics/${clinicId}/patients/${patientId}/timeline?limit=100&offset=0`),
      ];
      if (isClinicAdmin) {
        tasks.push(request(`/auth/clinics/${clinicId}/care-team/assignments?patient_id=${patientId}`));
        tasks.push(request(`/auth/clinics/${clinicId}/messages/internal-recipients`));
      } else if (isNurse) {
        tasks.push(request(`/auth/clinics/${clinicId}/nurse/patients/${patientId}/vitals?limit=100`));
      }
      const results = await Promise.all(tasks);
      const [patient, timeline] = results;
      const assignments = isClinicAdmin ? results[2] : [];
      const recipients = isClinicAdmin ? results[3] : [];
      const vitals = isNurse ? results[2] : [];
      setChart({ patient, timeline: timeline.items || [], timelineHasMore: timeline.has_more, assignments, vitals });
      setStaffOptions(recipients.filter((item) => ['doctor', 'nurse'].includes(item.role)));
      setTimelineOffset((timeline.items || []).length);
    } catch (error) {
      setChartError(error.message);
    } finally {
      setChartBusy(false);
    }
  };

  const loadAssignments = async (patientId) => {
    const assignments = await request(`/auth/clinics/${clinicId}/care-team/assignments?patient_id=${patientId}`);
    setChart((current) => current ? { ...current, assignments } : current);
  };

  const savePatient = async (event) => {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget));
    const body = {
      first_name: form.first_name,
      last_name: form.last_name,
      external_patient_id: form.external_patient_id || null,
      date_of_birth: form.date_of_birth || null,
      sex: form.sex || null,
      phone: form.phone || null,
      email: form.email || null,
      address: form.address || null,
      emergency_contact_name: form.emergency_contact_name || null,
      emergency_contact_phone: form.emergency_contact_phone || null,
    };
    setSaving(true);
    setChartError('');
    try {
      const patient = await request(`/auth/clinics/${clinicId}/patients/${chart.patient.id}`, { method: 'PATCH', body });
      setChart((current) => ({ ...current, patient }));
      setEdit(false);
      notify('Patient record updated');
      reload();
    } catch (error) {
      setChartError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const assignStaff = async (event) => {
    event.preventDefault();
    if (!staffId || !chart?.patient) return;
    setSaving(true);
    setChartError('');
    try {
      await request(`/auth/clinics/${clinicId}/care-team/assignments`, {
        method: 'POST',
        body: { patient_id: chart.patient.id, staff_member_id: staffId },
      });
      setStaffId('');
      await loadAssignments(chart.patient.id);
      notify('Care-team member assigned');
    } catch (error) {
      setChartError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const removeAssignment = async (assignment) => {
    if (!window.confirm(`Remove ${assignment.staff_name} from this patient’s care team?`)) return;
    setSaving(true);
    setChartError('');
    try {
      await request(`/auth/clinics/${clinicId}/care-team/assignments/${assignment.id}`, { method: 'DELETE' });
      await loadAssignments(chart.patient.id);
      notify('Care-team assignment removed');
    } catch (error) {
      setChartError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const loadMoreTimeline = async () => {
    setTimelineBusy(true);
    try {
      const result = await request(`/auth/clinics/${clinicId}/patients/${chart.patient.id}/timeline?limit=100&offset=${timelineOffset}`);
      setChart((current) => ({ ...current, timeline: [...current.timeline, ...(result.items || [])], timelineHasMore: result.has_more }));
      setTimelineOffset((offset) => offset + (result.items || []).length);
    } catch (error) {
      setChartError(error.message);
    } finally {
      setTimelineBusy(false);
    }
  };

  const exportAudit = async (format) => {
    try {
      await downloadFile(`/auth/clinics/${clinicId}/audit-log/patients/${chart.patient.id}/export.${format}`, `patient-audit.${format}`);
    } catch (error) {
      setChartError(error.message);
    }
  };

  return <>
    <HeaderIntro eyebrow="PEOPLE FIRST" title={role === 'doctor' || role === 'nurse' ? 'The people in your care.' : 'Patients'} description="Every patient record, thoughtfully organized and easy to reach." action={canCreate && <Button icon="plus" onClick={() => setModal({ type: 'patient' })}>Add patient</Button>} />
    <Panel title="Patient directory" subtitle={`${patients.length} records in your view`} action={<SearchTools value={search} onChange={setSearch} />}>
      {patients.length ? <div className="table-wrap"><table><thead><tr><th>PATIENT</th><th>DATE OF BIRTH</th><th>CONTACT</th><th>RECORD ID</th><th>ADDED</th><th /></tr></thead><tbody>
        {patients.map((patient, index) => <tr key={patient.id}><td><div className="patient-cell"><div className={`avatar avatar-${index % 4}`}>{initials(`${patient.first_name} ${patient.last_name}`)}</div><span><strong>{patient.first_name} {patient.last_name}</strong><small>{patient.email || 'Patient record'}</small></span></div></td><td>{dateLabel(patient.date_of_birth)}</td><td>{patient.phone || '—'}</td><td><span className="mono-id">{patient.external_patient_id || patient.id?.slice(0, 8)}</span></td><td>{dateLabel(patient.created_at)}</td><td><button className="button button-quiet compact" onClick={() => openChart(patient.id)}>View chart</button></td></tr>)}
      </tbody></table></div> : <div className="empty-state"><span>✳</span><h3>No patient records yet</h3><p>Add your first patient or import existing records to get started.</p>{canCreate && <Button icon="plus" onClick={() => setModal({ type: 'patient' })}>Add patient</Button>}</div>}
    </Panel>

    {chart && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setChart(null); }}>
      <section className="modal-card patient-chart-card" role="dialog" aria-modal="true" aria-labelledby="patient-chart-title">
        <div className="modal-header"><div><span className="eyebrow muted-eyebrow">PATIENT CHART</span><h2 id="patient-chart-title">{chart.patient ? `${chart.patient.first_name} ${chart.patient.last_name}` : 'Loading patient…'}</h2></div><button className="icon-button" aria-label="Close patient chart" disabled={saving} onClick={() => setChart(null)}><Icon name="close" /></button></div>
        {chartBusy && <div className="page-loading"><span className="spinner dark" />Loading patient chart…</div>}
        {chartError && <div className="form-message">{chartError}</div>}
        {!chartBusy && chart.patient && <>
          <div className="patient-chart-toolbar"><div><StatusBadge value="Active record" /><span className="mono-id">ID {chart.patient.id}</span></div><div className="table-actions">{isClinicAdmin && <><Button quiet compact onClick={() => exportAudit('csv')}>Audit CSV</Button><Button quiet compact onClick={() => exportAudit('pdf')}>Audit PDF</Button><Button quiet compact onClick={() => setEdit((value) => !value)}>{edit ? 'Cancel edit' : 'Edit record'}</Button></>}</div></div>
          {edit && isClinicAdmin ? <form className="patient-edit-form" onSubmit={savePatient}>
            <div className="field-row"><PatientField label="First name" name="first_name" value={chart.patient.first_name} required/><PatientField label="Last name" name="last_name" value={chart.patient.last_name} required/></div>
            <div className="field-row"><PatientField label="Date of birth" name="date_of_birth" type="date" value={chart.patient.date_of_birth}/><PatientField label="Sex" name="sex" value={chart.patient.sex}/></div>
            <div className="field-row"><PatientField label="Email" name="email" type="email" value={chart.patient.email}/><PatientField label="Phone" name="phone" value={chart.patient.phone}/></div>
            <PatientField label="External patient ID" name="external_patient_id" value={chart.patient.external_patient_id}/>
            <PatientField label="Address" name="address" value={chart.patient.address}/>
            <div className="field-row"><PatientField label="Emergency contact" name="emergency_contact_name" value={chart.patient.emergency_contact_name}/><PatientField label="Emergency contact phone" name="emergency_contact_phone" value={chart.patient.emergency_contact_phone}/></div>
            <div className="modal-actions"><Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save patient record'}</Button></div>
          </form> : <div className="patient-facts-grid"><PatientFact label="Date of birth" value={dateLabel(chart.patient.date_of_birth)}/><PatientFact label="Sex" value={pretty(chart.patient.sex || '—')}/><PatientFact label="Email" value={chart.patient.email}/><PatientFact label="Phone" value={chart.patient.phone}/><PatientFact label="External ID" value={chart.patient.external_patient_id}/><PatientFact label="Address" value={chart.patient.address}/><PatientFact label="Emergency contact" value={chart.patient.emergency_contact_name}/><PatientFact label="Emergency phone" value={chart.patient.emergency_contact_phone}/></div>}
          {isClinicAdmin && <Panel title="Care team" subtitle="Assign active doctors or nurses to this patient.">
            <form className="care-team-assign-form" onSubmit={assignStaff}><select value={staffId} onChange={(event) => setStaffId(event.target.value)} required><option value="">Choose a doctor or nurse</option>{staffOptions.map((staff) => <option key={staff.staff_member_id} value={staff.staff_member_id}>{staff.full_name} · {pretty(staff.role)}</option>)}</select><Button type="submit" disabled={saving || !staffId}>Assign staff</Button></form>
            <div className="table-wrap"><table><thead><tr><th>STAFF MEMBER</th><th>ROLE</th><th>ASSIGNED</th><th /></tr></thead><tbody>{(chart.assignments || []).map((assignment) => <tr key={assignment.id}><td>{assignment.staff_name}</td><td>{pretty(assignment.staff_role)}</td><td>{dateLabel(assignment.assigned_at)}</td><td><button className="button button-quiet compact" disabled={saving} onClick={() => removeAssignment(assignment)}>Remove</button></td></tr>)}</tbody></table>{!chart.assignments?.length && <EmptyInline text="No staff are assigned to this patient yet." />}</div>
          </Panel>}
          {isNurse && <VitalsHistory vitals={chart.vitals || []} />}
          {isDoctor && chart.doctorChart && <DoctorChartSections chart={chart} clinicId={clinicId} notify={notify}/>}
          {!isDoctor && <Panel title="Patient timeline" subtitle="A chronological view of appointments, visits, and record activity.">
            <div className="patient-timeline">{chart.timeline?.map((event, index) => <article className="patient-timeline-item" key={`${event.resource_id}-${index}`}><div className="timeline-point"/><div><div className="timeline-event-head"><strong>{event.title}</strong><span>{dateLabel(event.occurred_at)}</span></div><div className="timeline-event-meta"><StatusBadge value={event.event_type}/>{event.status && <StatusBadge value={event.status}/>}<small>{event.source}</small></div>{event.summary && <p>{event.summary}</p>}</div></article>)}{!chart.timeline?.length && <EmptyInline text="No timeline events are available for this patient." />}</div>
            {chart.timelineHasMore && <div className="timeline-more"><Button quiet disabled={timelineBusy} onClick={loadMoreTimeline}>{timelineBusy ? 'Loading…' : 'Load older events'}</Button></div>}
          </Panel>}
        </>}
      </section>
    </div>}
  </>;
}

function DoctorChartSections({chart,clinicId,notify}) {
  const [allergies,setAllergies]=useState(chart.allergies||[]),[conditions,setConditions]=useState(chart.conditions||[]),[medications,setMedications]=useState(chart.medications||[]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const mutate=async(path,method,body,success)=>{setBusy(true);setError('');try{await request(`/auth/clinics/${clinicId}/doctor/${path}`,{method,body});const fresh=await request(`/auth/clinics/${clinicId}/doctor/patients/${chart.patient.id}/chart`);setAllergies(fresh.allergies||[]);setConditions(fresh.conditions||[]);setMedications(fresh.medications||[]);notify(success)}catch(ex){setError(ex.message)}finally{setBusy(false)}};
  return <><div className="content-grid"><Panel title="Allergies" subtitle="Active allergy records are considered by the prescription checker."><form className="availability-form" onSubmit={e=>{e.preventDefault();const f=Object.fromEntries(new FormData(e.currentTarget));mutate(`patients/${chart.patient.id}/allergies`,'POST',{substance:f.substance,reaction:f.reaction||null,severity:f.severity||null},'Allergy recorded');e.currentTarget.reset()}}><Field label="Substance" name="substance" required/><Field label="Reaction" name="reaction"/><label className="field"><span>Severity</span><select name="severity"><option value="">Not specified</option><option value="mild">Mild</option><option value="moderate">Moderate</option><option value="severe">Severe</option></select></label><Button type="submit" disabled={busy}>Add allergy</Button></form>{allergies.map(item=><div className="record-line" key={item.id}><span><strong>{item.substance}</strong><small>{item.reaction||'Reaction not recorded'} · {pretty(item.severity||'unspecified')} · {pretty(item.status)}</small></span><Button quiet compact disabled={busy} onClick={()=>mutate(`allergies/${item.id}`,'PATCH',{status:item.status==='active'?'resolved':'active'},'Allergy status updated')}>{item.status==='active'?'Resolve':'Reactivate'}</Button></div>)}</Panel>
  <Panel title="Medical conditions" subtitle="Maintain the patient’s active problem list."><form className="availability-form" onSubmit={e=>{e.preventDefault();const f=Object.fromEntries(new FormData(e.currentTarget));mutate(`patients/${chart.patient.id}/conditions`,'POST',{name:f.name,code:f.code||null,code_system:f.code_system||null,onset_date:f.onset_date||null,notes:f.notes||null},'Condition recorded');e.currentTarget.reset()}}><Field label="Condition" name="name" required/><div className="field-row"><Field label="Code" name="code"/><Field label="Code system" name="code_system"/></div><Field label="Onset date" name="onset_date" type="date"/><Field label="Notes" name="notes"/><Button type="submit" disabled={busy}>Add condition</Button></form>{conditions.map(item=><div className="record-line" key={item.id}><span><strong>{item.name}</strong><small>{pretty(item.status)}{item.onset_date?` · Since ${dateLabel(item.onset_date)}`:''}</small></span><Button quiet compact disabled={busy} onClick={()=>mutate(`conditions/${item.id}`,'PATCH',{status:item.status==='active'?'resolved':'active'},'Condition status updated')}>{item.status==='active'?'Resolve':'Reactivate'}</Button></div>)}</Panel></div>
  {error&&<div className="form-message">{error}</div>}
  <Panel title="Current medications" subtitle="Discontinuation records the current date as the medication end date."><div className="table-wrap"><table><thead><tr><th>MEDICATION</th><th>DOSE / ROUTE</th><th>FREQUENCY</th><th>STATUS</th><th/></tr></thead><tbody>{medications.map(item=><tr key={item.id}><td>{item.name}</td><td>{[item.dose,item.route].filter(Boolean).join(' · ')||'—'}</td><td>{item.frequency||'—'}</td><td><StatusBadge value={item.status}/></td><td>{item.status==='active'&&<Button quiet compact disabled={busy} onClick={()=>mutate(`medications/${item.id}/discontinue`,'POST',undefined,'Medication discontinued')}>Discontinue</Button>}</td></tr>)}</tbody></table>{!medications.length&&<EmptyInline text="No medication records."/>}</div></Panel>
  <div className="content-grid"><Panel title="Appointments" subtitle="Patient appointment history"><div className="record-section">{(chart.appointments||[]).map(item=><div className="record-line" key={item.id}><span>{dateLabel(item.starts_at)} · {timeLabel(item.starts_at)}</span><StatusBadge value={item.status}/></div>)}{!chart.appointments?.length&&<EmptyInline text="No appointments recorded."/>}</div></Panel><Panel title="Visits" subtitle="Past and current clinical visits"><div className="record-section">{(chart.visits||[]).map(item=><div className="record-line" key={item.id}><span>{dateLabel(item.started_at)} · {pretty(item.status)}</span><code>{item.id.slice(0,8)}</code></div>)}{!chart.visits?.length&&<EmptyInline text="No visits recorded."/>}</div></Panel></div>
  <Panel title="Recent vitals" subtitle="Most recent observations first"><VitalsHistory vitals={chart.vitals||[]}/></Panel></>;
}

function PatientField({ label, name, value, type = 'text', required = false }) {
  return <label className="field"><span>{label}</span><input name={name} type={type} required={required} defaultValue={value || ''} /></label>;
}

function PatientFact({ label, value }) {
  return <div className="patient-fact"><span>{label}</span><strong>{value || '—'}</strong></div>;
}

function VitalsHistory({ vitals }) {
  return <Panel title="Vital observations" subtitle={`${vitals.length} recent observations · newest first`}>
    <div className="table-wrap"><table><thead><tr><th>RECORDED</th><th>BLOOD PRESSURE</th><th>HEART RATE</th><th>RESPIRATION</th><th>TEMPERATURE</th><th>O₂</th><th>WEIGHT</th><th>PAIN</th><th>NOTES</th></tr></thead><tbody>
      {vitals.map((vital) => <tr key={vital.id}>
        <td>{dateLabel(vital.recorded_at)}<small className="sub-cell">{timeLabel(vital.recorded_at)}</small></td>
        <td>{vital.blood_pressure_systolic != null ? `${vital.blood_pressure_systolic}/${vital.blood_pressure_diastolic} mmHg` : '—'}</td>
        <td>{vital.heart_rate != null ? `${vital.heart_rate} bpm` : '—'}</td>
        <td>{vital.respiratory_rate != null ? `${vital.respiratory_rate}/min` : '—'}</td>
        <td>{vital.temperature_c != null ? `${vital.temperature_c} °C` : '—'}</td>
        <td>{vital.oxygen_saturation != null ? `${vital.oxygen_saturation}%` : '—'}</td>
        <td>{vital.weight_kg != null ? `${vital.weight_kg} kg` : '—'}</td>
        <td>{vital.pain_score ?? '—'}</td>
        <td>{vital.notes || '—'}</td>
      </tr>)}
    </tbody></table>{!vitals.length && <EmptyInline text="No vital observations have been recorded yet." />}</div>
  </Panel>;
}
