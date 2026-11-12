"use client";

import { useState, useEffect, useMemo, useCallback } from 'react';
import { EmptyState } from '../shared/ui';
import { request } from '../../lib/api';
import { Overview } from '../dashboard/Overview';
import { PatientPage } from '../patients/PatientPage';
import { AppointmentPage } from '../scheduling/AppointmentPage';
import { MessagePage } from '../messaging/MessagePage';
import { ImportPage, TeamPage, SetupPage, WaitingRoom, ReceptionWaitlist } from '../clinic/ClinicPages';
import { BillingDashboard, ClaimsPage } from '../billing/ClaimsPage';
import { PatientCarePage } from '../portal/PatientCarePage';
import { VisitTools } from '../visits/VisitPages';
import { PlatformPage } from '../platform/PlatformPage';
import { AuditLogPage } from '../clinic/AuditLogPage';

export function PageContent({role,page,clinicId,session,notify,reload,setModal,query}){
  const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(true),[search,setSearch]=useState('');
  const path=useMemo(()=>{
    if(role==='super_admin')return page==='Clinics'?'/auth/platform/clinics':page==='Users'?'/auth/platform/users':null;
    const base=`/auth/clinics/${clinicId}`;
    if(role==='clinic_admin')return ({Overview:`${base}/setup/onboarding`,Patients:`${base}/patients?limit=100`,Appointments:`${base}/setup/appointments`,Messages:`${base}/messages/inbox?pending_only=false`, 'Team access':`${base}/members`,Imports:`${base}/imports/patients`,'Clinic setup':`${base}/setup/profile`,'Audit log':`${base}/audit-log`})[page]||null;
    if(role==='doctor')return ({Overview:`${base}/doctor/dashboard`, 'My patients':`${base}/doctor/patients?limit=100`,Appointments:`${base}/doctor/appointments`,Messages:`${base}/messages/inbox`, 'Visit notes':`${base}/doctor/dashboard`})[page]||null;
    if(role==='nurse')return ({Overview:`${base}/nurse/dashboard`,'My patients':`${base}/patients?limit=100`,Appointments:`${base}/nurse/dashboard`,Messages:`${base}/messages/inbox`,Vitals:`${base}/nurse/dashboard`})[page]||null;
    if(role==='receptionist')return ({Overview:`${base}/reception/dashboard`,Patients:`${base}/patients?limit=100`,Appointments:`${base}/reception/appointments`,'Waiting room':`${base}/reception/waiting-room`,Waitlist:`${base}/reception/waitlist`,Messages:`${base}/messages/inbox?pending_only=false`})[page]||null;
    if(role==='billing_staff')return ({Overview:`${base}/billing/dashboard`,Claims:`${base}/billing/claims`,Messages:`${base}/messages/internal-recipients`})[page]||null;
    if(role==='patient')return ({'My care':`${base}/portal/me`,Appointments:`${base}/portal/appointments`,Messages:`${base}/portal/messages`,'Health records':`${base}/portal/me`})[page]||null;
    return null;
  },[role,page,clinicId]);
  const load=useCallback(async()=>{if(role==='super_admin'&&page==='Overview'){setBusy(true);setError('');try{const [clinics,users]=await Promise.all([request('/auth/platform/clinics?limit=200'),request('/auth/platform/users?limit=200')]);setData({clinics,users})}catch(e){setError(e.message)}finally{setBusy(false)}return}if(!path){setBusy(false);return}setBusy(true);setError('');try{setData(await request(path))}catch(e){setError(e.message)}finally{setBusy(false)}},[path,role,page]);
  useEffect(()=>{load()},[load]);
  const filtered=useMemo(()=>{const q=(search||query).trim().toLowerCase();if(!q)return data;const array=Array.isArray(data)?data:Array.isArray(data?.items)?data.items:null;if(!array)return data;return Array.isArray(data)?array.filter(item=>JSON.stringify(item).toLowerCase().includes(q)):{...data,items:array.filter(item=>JSON.stringify(item).toLowerCase().includes(q))}},[data,search,query]);
  if(busy)return <div className="page-loading"><span className="spinner dark"/>Loading your workspace…</div>;
  if(error)return <div className="page-error"><div className="error-symbol">!</div><h2>We couldn’t load this view</h2><p>{error}</p><button className="button button-primary" onClick={load}>Try again</button></div>;
  if(page==='Overview'&&role==='billing_staff')return <BillingDashboard data={data} setPage={name=>window.dispatchEvent(new CustomEvent('careflow:navigate',{detail:name}))}/>;
  if(page==='Overview')return <Overview role={role} data={data} setPage={name=>window.dispatchEvent(new CustomEvent('careflow:navigate',{detail:name}))} setModal={setModal} clinicId={clinicId} notify={notify} reload={reload}/>;
  if(page==='Patients'||page==='My patients')return <PatientPage role={role} data={filtered} search={search} setSearch={setSearch} setModal={setModal} clinicId={clinicId} reload={reload} notify={notify}/>;
  if(page==='Appointments')return <AppointmentPage role={role} data={data} setModal={setModal} clinicId={clinicId} reload={reload} notify={notify}/>;
  if(page==='Messages')return <MessagePage role={role} data={data} clinicId={clinicId} session={session} notify={notify} reload={reload}/>;
  if(page==='Imports')return <ImportPage data={data} clinicId={clinicId} notify={notify} reload={reload}/>;
  if(page==='Team access')return <TeamPage data={data} setModal={setModal} clinicId={clinicId} reload={reload} notify={notify}/>;
  if(page==='Clinic setup')return <SetupPage data={data} clinicId={clinicId} notify={notify} reload={reload}/>;
  if(page==='Waiting room')return <WaitingRoom data={data} clinicId={clinicId} notify={notify} reload={reload}/>;
  if(page==='Waitlist')return <ReceptionWaitlist data={data} clinicId={clinicId} notify={notify}/>;
  if(page==='Audit log')return <AuditLogPage data={data} clinicId={clinicId} notify={notify}/>;
  if(page==='Claims')return <ClaimsPage data={data} clinicId={clinicId} notify={notify} reload={reload}/>;
  if(page==='Health records'||page==='My care')return <PatientCarePage data={data} page={page} clinicId={clinicId} notify={notify} reload={reload}/>;
  if(page==='Visit notes'||page==='Vitals')return <VisitTools role={role} data={data} clinicId={clinicId} notify={notify} reload={reload}/>;
  if(role==='super_admin')return <PlatformPage page={page} data={filtered} setSearch={setSearch} search={search} clinicId={clinicId} notify={notify} reload={reload}/>;
  return <EmptyState title={page} description="This part of your workspace is ready to be connected."/>;
}
