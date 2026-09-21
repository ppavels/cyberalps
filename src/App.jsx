import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, ShieldCheck, Search, Gauge, Code2, Globe2, Menu, X, Mountain, Check, CircleAlert, ChevronDown, LoaderCircle, FileCheck2, Mail, Minus, CheckCircle2 } from 'lucide-react';
import { content, checks } from './content.js';

const demo = { url: 'https://example.com', scores: { security: 82, seo: 67, ai: 41 }, checks: [
  { code: 'hsts', category: 'security', status: 'attention', evidence: 'Demonstration only', weight: 2 },
  { code: 'description', category: 'seo', status: 'attention', evidence: 'Demonstration only', weight: 1 },
  { code: 'structured', category: 'ai', status: 'attention', evidence: 'Demonstration only', weight: 2 },
] };
const sections = ['services', 'process', 'check', 'contact'];
const serviceIcons = [Code2, ShieldCheck, Search, Gauge];
function Brand() { return <a className="brand" href="/"><span className="brand-mark"><Mountain size={23} strokeWidth={1.8}/></span>CyberAlps</a>; }
function scoreColor(value) { return value === null ? 'muted' : value >= 80 ? 'green' : value >= 55 ? 'amber' : 'red'; }

function Report({ t, report, isDemo, busy, stage, onPlan }) {
  let host;
  try { host = new URL(report.url).hostname; } catch { host = report.url; }
  return <div className="report" aria-busy={busy}>
    <div className="report-heading"><div><div className="report-title">{isDemo ? t.example : t.live}<span className={'badge ' + (isDemo ? '' : 'verified')}>{isDemo ? t.demo : 'CHECK'}</span></div><span className="report-host">{host}</span></div><FileCheck2 size={22} className="muted"/></div>
    {busy ? <div className="scan-state" role="status"><LoaderCircle className="spin" size={34}/><strong>{t.checking}</strong><span>{t.stages[stage] || t.stages.queued}</span><div className="scan-track"><span/></div></div> : <>
      <div className="scores">{Object.entries(report.scores).map(([key, value]) => <div className={'score ' + scoreColor(value)} key={key}>
        <div className="gauge" style={{ '--value': value ?? 0 }}><span className="score-number">{value ?? '—'}<small>/100</small></span></div>
        <span className="score-label">{t.categories[key]}</span><span className="score-status">{value === null ? t.unknown : value >= 80 ? t.good : value >= 55 ? t.improve : t.low}</span>
        <div className="mobile-meter"><span style={{ width: `${value ?? 0}%` }}/></div>
      </div>)}</div>
      <div className="findings"><h3>{t.next}</h3>{report.checks.filter(c => c.status !== 'pass').slice(0,3).map(c => <div className="finding" key={c.code}><CircleAlert size={15} className={c.category === 'seo' ? 'amber' : 'red'}/><span>{checks[c.code]?.[t === content.de ? 1 : 0] || c.code}</span><small>{t.categories[c.category]}</small></div>)}
        {!report.checks.some(c => c.status !== 'pass') && <div className="finding"><CheckCircle2 className="green" size={18}/>{t.good}</div>}
      </div>
      <button className="report-action" onClick={onPlan}><span>{t.turn}</span><span>{t.plan}<ArrowRight size={16}/></span></button>
    </>}
  </div>;
}

export default function App({ lang = 'de', page = 'home' }) {
  const t = content[lang];
  const [menu, setMenu] = useState(false);
  const [url, setUrl] = useState('');
  const [consent, setConsent] = useState(false);
  const [job, setJob] = useState(null);
  const [report, setReport] = useState(demo);
  const [showDetails, setShowDetails] = useState(false);
  const [error, setError] = useState('');
  const [contact, setContact] = useState(false);
  const [leadStatus, setLeadStatus] = useState('');
  const [leadError, setLeadError] = useState('');
  const dialog = useRef(null);
  const polling = useRef(null);
  const busy = job && !['done', 'error'].includes(job.status);
  const isDemo = report === demo;

  useEffect(() => {
    if (!job?.id || ['done', 'error'].includes(job.status)) return;
    let disposed = false;
    let failures = 0;
    const started = Date.now();
    const poll = async () => {
      try {
        if (Date.now() - started > 15 * 60 * 1000) {
          setError(lang === 'de' ? 'Die Wartezeit wurde überschritten. Bitte versuchen Sie es erneut.' : 'The check timed out. Please try again.');
          setJob(j => ({ ...j, status: 'error' }));
          return;
        }
        const response = await fetch(`/api/audits/${job.id}`, { signal: AbortSignal.timeout(10000) });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Request failed');
        if (disposed) return;
        failures = 0;
        setJob(data);
        if (data.status === 'done') { setReport(data.result); setShowDetails(true); return; }
        if (data.status === 'error') { setError(data.error); return; }
      } catch (e) {
        if (disposed) return;
        if (++failures >= 3 || Date.now() - started > 15 * 60 * 1000) { setError(lang === 'de' ? 'Verbindung unterbrochen. Bitte versuchen Sie es erneut.' : 'Connection interrupted. Please try again.'); setJob(j => ({ ...j, status: 'error' })); return; }
      }
      if (!disposed) polling.current = setTimeout(poll, 1500);
    };
    poll();
    return () => { disposed = true; clearTimeout(polling.current); };
  }, [job?.id, lang]);

  useEffect(() => { if (contact) dialog.current?.showModal(); else dialog.current?.close(); }, [contact]);
  async function submit(event) {
    event.preventDefault(); setError(''); setShowDetails(false); setJob({status:'queued'});
    try {
      const response = await fetch('/api/audits', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({url, consent}), signal: AbortSignal.timeout(15000) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setJob(data);
    } catch (e) { setError(e.message); setJob({status:'error'}); }
  }
  async function sendLead(event) {
    event.preventDefault(); setLeadStatus('sending'); setLeadError('');
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const response = await fetch('/api/leads', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...data, consent:data.consent === 'on', language:lang, auditId:!isDemo ? job?.id : ''}), signal:AbortSignal.timeout(15000) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      setLeadStatus('done');
    } catch(e) { setLeadError(e.message); setLeadStatus(''); }
  }
  function openContact() { setContact(true); setMenu(false); }
  function showPlan() { setShowDetails(true); setTimeout(() => document.getElementById('report-details')?.scrollIntoView({behavior:'smooth', block:'start'}), 30); }
  const pageSuffix = page === 'home' ? '' : page + '/';

  return <>
    <a href="#main" className="skip-link">{lang === 'de' ? 'Zum Inhalt' : 'Skip to content'}</a>
    <header><div className="container header-inner"><Brand/>
      <nav aria-label={lang === 'de' ? 'Hauptnavigation' : 'Main navigation'} className={menu ? 'open' : ''}>{t.nav.map((item,index) => index === 3 ? <button key={item} onClick={openContact}>{item}</button> : <a href={`/${lang}/#${sections[index]}`} onClick={() => setMenu(false)} key={item}>{item}</a>)}</nav>
      <div className="header-actions"><a className="language" href={`/${lang === 'en' ? 'de' : 'en'}/${pageSuffix}`} aria-label={lang === 'en' ? 'Auf Deutsch wechseln' : 'Switch to English'}>{lang.toUpperCase()}<ChevronDown size={13}/></a><button className="button header-cta" onClick={openContact}>{t.project}</button><button className="menu-button" aria-label={menu ? t.close : 'Menu'} aria-expanded={menu} onClick={() => setMenu(!menu)}>{menu ? <X/> : <Menu/>}</button></div>
    </div></header>
    <main id="main">{page !== 'home' ? <article className="container legal"><a href={`/${lang}/`} className="text-link">← {t.back}</a><h1>{page === 'privacy' ? t.privacyTitle : t.termsTitle}</h1>{(page === 'privacy' ? t.privacyText : t.termsText).map(text => <p key={text}>{text}</p>)}<button className="button" onClick={openContact}>{t.contact}<ArrowRight size={17}/></button></article> : <>
      <section className="hero"><img className="hero-image" src="/alps.webp" alt="" fetchPriority="high"/><div className="hero-shade"/>
        <div className="container hero-layout"><div className="hero-copy"><div className="eyebrow">{t.eyebrow}</div><h1>{t.hero1}<br/>{t.hero2}</h1><p>{t.intro}<br/>{t.intro2}</p>
          <div className="hero-buttons"><button className="button" onClick={openContact}>{t.project}<ArrowRight size={18}/></button><a className="button button-secondary" href="#services">{t.explore}</a></div>
          <a className="existing-link" href="#check">{t.existing}<ArrowUpRight size={16}/></a>
        </div><figure className="studio-panel swiss-visual"><img src="/swiss-development.webp" width="960" height="640" alt=""/><figcaption>{t.swissCaption}</figcaption></figure></div>
      </section>
      <section className="container section" id="services"><div className="eyebrow">{t.servicesEyebrow}</div><h2>{t.servicesTitle}</h2><div className="services">{t.services.map(([title, subtitle, detail], index) => {const Icon=serviceIcons[index];return <article key={title}><div className="service-top"><span className="icon-circle"><Icon size={23} strokeWidth={1.5}/></span><h3>{title}</h3></div><h4>{subtitle}</h4><p>{detail}</p></article>;})}</div></section>
      <section className="audit-section" id="check"><div className="container hero-layout"><div className="audit-copy"><div className="eyebrow">{t.auditEyebrow}</div><h2>{t.auditTitle}</h2><p>{t.auditIntro}</p>
          <form className="audit-form" onSubmit={submit}><label className="sr-only" htmlFor="url">{t.website}</label><div className="url-control"><Globe2 size={20}/><input id="url" type="text" inputMode="url" autoComplete="url" placeholder={t.placeholder} required maxLength={2048} value={url} onChange={event => setUrl(event.target.value)} disabled={busy}/><button className="button" disabled={busy}>{busy ? <LoaderCircle size={18} className="spin"/> : <>{t.run}<ArrowRight size={17}/></>}</button></div>
            <label className="checkbox consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} required disabled={busy}/><span>{t.consent}</span></label>
          </form><div className="hero-meta"><span>{t.scope}</span><button className="text-link" onClick={() => {setReport(demo);setShowDetails(true);}} disabled={busy}>{t.exampleLink}<ArrowUpRight size={15}/></button></div>
          {error && <div className="error" role="alert"><CircleAlert size={19}/><span>{error}</span></div>}
        </div><Report t={t} report={report} isDemo={isDemo} busy={busy} stage={job?.stage || 'queued'} onPlan={showPlan}/></div></section>
      {showDetails && <section className="container report-details section" id="report-details"><div className="section-head"><div><div className="eyebrow">{isDemo ? t.example : t.live}</div><h2>{t.reportTitle}</h2><p>{t.reportIntro}</p></div><button className="button" onClick={openContact}>{t.cta}<ArrowRight size={16}/></button></div>
        {isDemo && <p className="notice">{lang === 'de' ? 'Demonstration: Diese Werte sind keine tatsächlichen Messergebnisse.' : 'Demonstration: these values are not actual measurement results.'}</p>}
        <div className="result-list">{report.checks.map(c => <details key={c.code} className={'result ' + c.status}><summary><span className={'status-dot ' + (c.status === 'pass' ? 'green' : c.status === 'unknown' ? 'muted' : 'amber')}>{c.status === 'pass' ? <Check size={15}/> : c.status === 'unknown' ? <Minus size={15}/> : <CircleAlert size={15}/>}</span><span>{checks[c.code]?.[lang === 'de' ? 1 : 0] || c.code}</span><span className="result-category">{t.categories[c.category]}</span><span className="result-status">{c.status === 'pass' ? t.checked : c.status === 'unknown' ? t.unknown : t.issues}</span><ChevronDown size={17}/></summary><div className="result-body"><b>{t.evidence}</b><code>{c.evidence}</code><b>{t.action}</b><p>{checks[c.code]?.[lang === 'de' ? 3 : 2]}</p><small>{t.weight}: {c.weight}</small></div></details>)}</div><p className="limitation"><ShieldCheck size={17}/>{t.limitation}</p>
      </section>}
      <section className="container section process" id="process"><div className="eyebrow">{t.processEyebrow}</div><h2>{t.processTitle}</h2><ol className="steps">{t.steps.map(([title, text], index) => <li key={title}><div className="step-top"><span>0{index + 1}</span><i/></div><h3>{title}</h3><p>{text}</p></li>)}</ol></section>
      <section className="container section approach" id="approach"><div className="approach-intro"><h2>{t.approachTitle}</h2><p>{t.approachIntro}</p></div><div className="approach-grid">{t.approachItems.map(([title,text])=><article key={title}><ShieldCheck size={23}/><h3>{title}</h3><p>{text}</p></article>)}</div></section>
      <section className="container" id="contact"><div className="cta"><span className="icon-circle large"><Mountain size={31}/></span><div><h2>{t.ctaTitle}</h2><p>{t.ctaText}</p></div><button className="button" onClick={openContact}>{t.cta}<ArrowRight size={18}/></button></div></section>
      <section className="container section faq"><h2>{t.faqTitle}</h2><div>{t.faq.map(([question, answer]) => <details key={question}><summary>{question}<ChevronDown size={18}/></summary><p>{answer}</p></details>)}</div></section>
    </>}</main>
    <footer className="container"><Brand/><span className="footer-line">{t.footerLine}</span><div><button onClick={openContact}>{t.contact}</button><a href={`/${lang}/privacy/`}>{t.privacy}</a><a href={`/${lang}/terms/`}>{t.terms}</a></div></footer>
    <dialog ref={dialog} onCancel={() => setContact(false)} onClick={event => {if(event.target===dialog.current) setContact(false);}}><div className="contact-dialog"><button className="dialog-close" aria-label={t.close} onClick={() => setContact(false)}><X size={22}/></button><div className="eyebrow">CYBERALPS</div><h2>{t.requestTitle}</h2><p>{t.requestIntro}</p>
      {leadStatus === 'done' ? <div className="success" role="status"><CheckCircle2 size={28}/><p>{t.success}</p><button className="button" onClick={() => setContact(false)}>{t.close}</button></div> : <form onSubmit={sendLead} className="contact-form"><div className="form-row"><label>{t.name}<input name="name" autoComplete="name" minLength={2} maxLength={100} required/></label><label>{t.email}<input name="email" type="email" autoComplete="email" maxLength={254} required/></label></div><label>{t.optionalWebsite}<input name="url" autoComplete="url" defaultValue={url} maxLength={2048}/></label><label>{t.message}<textarea name="message" rows={4} minLength={10} maxLength={3000} required/></label><label className="honeypot" aria-hidden="true">Leave empty<input name="website" autoComplete="off" tabIndex={-1}/></label><label className="checkbox"><input type="checkbox" name="consent" required/><span>{t.contactConsent} <a href={`/${lang}/privacy/`}>{t.privacy}</a></span></label>{leadError && <p role="alert" className="error">{leadError}</p>}<button className="button" disabled={leadStatus === 'sending'}>{leadStatus === 'sending' ? t.sending : t.send}<ArrowRight size={18}/></button></form>}
    </div></dialog>
  </>;
}
