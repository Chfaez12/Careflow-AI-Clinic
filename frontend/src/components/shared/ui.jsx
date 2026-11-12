"use client";

import React from 'react';

const iconPaths = {
  grid:<><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  users:<><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
  calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/></>,
  message:<><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/></>,
  team:<><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/></>,
  upload:<><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5M12 3v12"/></>,
  settings:<><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.8 1l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.8-1l-1.7.7-1.4-2.4L7.1 15a8 8 0 0 1 0-2l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.8-1l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.8 1l1.7-.7 1.4 2.4L19.4 13a8 8 0 0 1 0 2Z" transform="translate(-1 -1)"/></>,
  note:<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/></>,
  pulse:<><path d="M3 12h4l3-8 4 16 3-8h4"/></>,
  room:<><path d="M3 21V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v16"/><path d="M3 10h18M9 21v-6h6v6M7 7h.01M12 7h.01M17 7h.01"/></>,
  receipt:<><path d="M4 2v20l4-2 4 2 4-2 4 2V2l-4 2-4-2-4 2z"/><path d="M8 9h8M8 13h6"/></>,
  building:<><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 21V9h6v12M8 7h.01M12 7h.01M16 7h.01M8 12h.01M16 12h.01"/></>,
  search:<><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  plus:<><path d="M12 5v14M5 12h14"/></>,
  arrow:<><path d="M7 17 17 7M7 7h10v10"/></>,
  bell:<><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
  close:<><path d="m18 6-12 12M6 6l12 12"/></>,
  logout:<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></>,
  chevron:<path d="m9 18 6-6-6-6"/>,
};
export function Icon({name,size=19}) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name]||iconPaths.grid}</svg>; }
export const initials = (name='') => name.split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase() || 'CF';
export const dateLabel = value => value ? new Intl.DateTimeFormat('en',{month:'short',day:'numeric',year:'numeric'}).format(new Date(value)) : '—';
export const timeLabel = value => value ? new Intl.DateTimeFormat('en',{hour:'numeric',minute:'2-digit'}).format(new Date(value)) : '—';
export const pretty = value => String(value||'').replaceAll('_',' ').replace(/\b\w/g,m=>m.toUpperCase());
export function HeaderIntro({eyebrow,title,description,action}){return <div className="page-intro"><div><div className="eyebrow muted-eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>}
export function Button({children,onClick,quiet=false,icon,disabled=false,type='button'}){return <button type={type} disabled={disabled} className={`button ${quiet?'button-quiet':'button-primary'}`} onClick={onClick}>{icon&&<Icon name={icon} size={17} />}{children}</button>}
export function Panel({title,subtitle,action,children,className=''}){return <section className={`panel ${className}`}><div className="panel-heading"><div><h3>{title}</h3>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>{children}</section>}
export function StatusBadge({value}){const v=String(value||'unknown').toLowerCase().replaceAll(' ','_');return <span className={`status-badge status-${v}`}>{pretty(value||'Unknown')}</span>}
export function Metric({label,value,change,icon,tone='mint'}){return <div className="metric-card"><div className={`metric-icon ${tone}`}><Icon name={icon}/></div><div className="metric-label">{label}</div><div className="metric-bottom"><strong>{value??'—'}</strong>{change&&<span>{change}</span>}</div></div>}
export function EmptyInline({text}){return <div className="empty-inline"><span>✳</span>{text}</div>}
export function EmptyState({title,description}){return <div className="page-error"><div className="error-symbol">✳</div><h2>{title}</h2><p>{description}</p></div>}
export function SearchTools({value,onChange,placeholder='Search records'}){return <label className="table-search"><Icon name="search" size={17}/><input value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/></label>}
export function Field({label,name,type='text',required=false,defaultValue,placeholder}){return <label className="field"><span>{label}</span><input name={name} type={type} required={required} defaultValue={defaultValue} placeholder={placeholder}/></label>}
