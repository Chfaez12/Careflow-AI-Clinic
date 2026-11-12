"use client";

import { useState, useEffect, useCallback } from 'react';
import { Icon, initials } from '../shared/ui';
import { request } from '../../lib/api';
import { AuthScreen, RecoveryScreen, PendingScreen } from '../auth/AuthScreens';
import { Modal } from '../dialogs/Modal';
import { LogoutConfirmation } from '../dialogs/LogoutConfirmation';
import { PageContent } from '../workspace/PageContent';
import { roleNames, navByRole } from '../shared/config.js';

function App(){
  const [session,setSession]=useState(null),[loading,setLoading]=useState(true),[authMode,setAuthMode]=useState('login'),[notice,setNotice]=useState('');
  const [recoveryPath,setRecoveryPath]=useState('');
  const [clinicId,setClinicId]=useState(''),[page,setPage]=useState('Overview'),[mobileOpen,setMobileOpen]=useState(false),[refresh,setRefresh]=useState(0),[modal,setModal]=useState(null),[query,setQuery]=useState(''),[clinicInfo,setClinicInfo]=useState(null);
  const [logoutPrompt,setLogoutPrompt]=useState(false),[logoutBusy,setLogoutBusy]=useState(false);
  const notify=useCallback((message)=>{setNotice(message);window.setTimeout(()=>setNotice(''),4500)},[]);
  const reload=useCallback(()=>setRefresh(v=>v+1),[]);
  useEffect(()=>{const path=window.location.pathname;if(['/auth/accept-invite','/auth/reset-password'].includes(path)){setRecoveryPath(path);setLoading(false);return}request('/auth/my-profile').then(data=>setSession(data)).catch(async()=>{try{await request('/auth/refresh',{method:'POST'});setSession(await request('/auth/my-profile'))}catch{setSession(null)}}).finally(()=>setLoading(false))},[]);
  useEffect(()=>{if(!session)return;const active=(session.memberships||[]).filter(m=>m.status==='active');const available=active.find(m=>m.clinic_id===clinicId)||active[0];if(available&&available.clinic_id!==clinicId)setClinicId(available.clinic_id);if(session.profile?.is_super_admin)setClinicId('')},[session,clinicId]);
  useEffect(()=>{if(!clinicId){setClinicInfo(null);return}request(`/auth/clinics/${clinicId}/setup/profile`).then(setClinicInfo).catch(()=>setClinicInfo(null))},[clinicId]);
  useEffect(()=>{const onNavigate=e=>setPage(e.detail);window.addEventListener('careflow:navigate',onNavigate);return()=>window.removeEventListener('careflow:navigate',onNavigate)},[]);
  const membership=(session?.memberships||[]).find(m=>m.clinic_id===clinicId&&m.status==='active');
  const role=session?.profile?.is_super_admin?'super_admin':membership?.role||((session?.memberships||[]).find(m=>m.status==='invited')?.role);
  const clinic=clinicInfo||session?.memberships?.find(m=>m.clinic_id===clinicId)?.clinic;
  const setAuth=(data)=>{setSession(data);setAuthMode('login');setPage('Overview');setNotice('');};
  const logout=()=>setLogoutPrompt(true);
  const confirmLogout=async()=>{setLogoutBusy(true);try{await request('/auth/logout',{method:'POST'});setSession(null);setClinicId('');setPage('Overview');setLogoutPrompt(false)}catch(e){notify(`Could not sign out. Please try again. ${e.message}`)}finally{setLogoutBusy(false)}};
  if(recoveryPath)return <RecoveryScreen invite={recoveryPath.endsWith('accept-invite')} onComplete={data=>{window.history.replaceState({},'', '/');setRecoveryPath('');setAuth(data)}}/>;
  if(loading)return <div className="boot"><div className="brand-mark"><Icon name="pulse" size={22}/></div><span>CareFlow</span><div className="loading-line"/></div>;
  if(!session)return <AuthScreen mode={authMode} setMode={setAuthMode} onAuth={setAuth} notify={notify} notice={notice}/>;
  if(!role)return <><PendingScreen session={session} onLogout={logout}/>{logoutPrompt&&<LogoutConfirmation onCancel={()=>setLogoutPrompt(false)} onConfirm={confirmLogout} busy={logoutBusy}/>}</>;
  const nav=navByRole[role]||navByRole.clinic_admin;
  return <div className="app-shell">
    {mobileOpen&&<button className="mobile-scrim" onClick={()=>setMobileOpen(false)} aria-label="Close navigation"/>}
    <aside className={`sidebar ${mobileOpen?'open':''}`}>
      <div className="brand-lockup"><div className="brand-mark"><Icon name="pulse" size={21}/></div><div className="brand-type">CareFlow<span>CLINIC </span></div><button className="mobile-close icon-button" onClick={()=>setMobileOpen(false)}><Icon name="close"/></button></div>
      <div className="clinic-switcher">{clinicId?<><span className="clinic-avatar">{initials(clinic?.name||'Care')}</span><span className="clinic-switch-label"><strong>{clinic?.name||'Your clinic'}</strong><small>{roleNames[role]}</small></span></>:<><span className="clinic-avatar owner">✳</span><span className="clinic-switch-label"><strong>CareFlow platform</strong><small>{roleNames[role]}</small></span></>}<span className="switch-chev"><Icon name="chevron" size={16}/></span></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav className="primary-nav">{nav.map(([label,icon])=><button key={label} onClick={()=>{setPage(label);setMobileOpen(false)}} className={`nav-item ${page===label?'selected':''}`}><Icon name={icon}/><span>{label}</span>{label==='Messages'&&role!=='patient'&&<i className="nav-dot"/>}</button>)}</nav>
      {clinicId&&role==='clinic_admin'&&<div className="sidebar-bottom-card"><div className="sidebar-card-icon"><Icon name="pulse"/></div><strong>Care, in sync.</strong><p>Your clinic workspace is ready for the next step.</p><button onClick={()=>setPage('Clinic setup')}>View setup <Icon name="arrow" size={14}/></button></div>}
      <div className="sidebar-footer"><div className="user-mini"><div className="avatar avatar-small">{initials(session.profile?.full_name)}</div><span><strong>{session.profile?.full_name||'CareFlow user'}</strong><small>{roleNames[role]}</small></span><button className="icon-button signout" title="Sign out" onClick={logout}><Icon name="logout" size={17}/></button></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" onClick={()=>setMobileOpen(true)}><span className="hamburger">☰</span></button><div className="breadcrumb">{role==='super_admin'?'Platform':clinic?.name||'CareFlow'} <Icon name="chevron" size={14}/> <strong>{page}</strong></div></div><div className="topbar-actions"><label className="search-box"><Icon name="search" size={17}/><input placeholder="Search anything" value={query} onChange={e=>setQuery(e.target.value)}/><kbd>⌘ K</kbd></label>{session.memberships?.filter(m=>m.status==='active').length>1&&<select className="clinic-select" value={clinicId} onChange={e=>{setClinicId(e.target.value);setPage('Overview')}}>{session.memberships.filter(m=>m.status==='active').map(m=><option key={m.clinic_id} value={m.clinic_id}>{m.clinic?.name||m.clinic_id.slice(0,8)}</option>)}</select>}<button className="icon-button notification"><Icon name="bell" size={19}/><i/></button><button className="avatar top-avatar" onClick={()=>setModal({type:'profile'})}>{initials(session.profile?.full_name)}</button></div></header>
      <div className="page-content"><PageContent key={`${role}-${page}-${clinicId}-${refresh}`} role={role} page={page} clinicId={clinicId} session={session} notify={notify} reload={reload} setModal={setModal} query={query}/></div>
    </main>
    {notice&&<div className="toast"><span className="toast-check">✓</span>{notice}</div>}
    {modal&&<Modal modal={modal} onClose={()=>setModal(null)} clinicId={clinicId} role={role} reload={reload} notify={notify} session={session}/>}
    {logoutPrompt&&<LogoutConfirmation onCancel={()=>setLogoutPrompt(false)} onConfirm={confirmLogout} busy={logoutBusy}/>}
  </div>
}

export default App;
