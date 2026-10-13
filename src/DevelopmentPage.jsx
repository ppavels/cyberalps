import React, { useState } from 'react';
import { ArrowRight, Check, Code2, Wrench, Layers3, ShieldCheck } from 'lucide-react';
import { developmentCopy, engineeringRates, budgetRates } from './developmentCopy.js';

const workIcons = [Code2, Wrench, Layers3];
const budgetHours = {hour:'1h',week:'25h',month:'80h',month100:'100h'};
function money(value, currency) {
  return currency === 'CHF' ? 'CHF ' + value.toLocaleString('de-CH') : '$' + value.toLocaleString('en-US');
}

export default function DevelopmentPage({ lang, onChoose }) {
  const t = developmentCopy[lang];
  const [currency, setCurrency] = useState(lang === 'de' ? 'CHF' : 'USD');
  const key = currency.toLowerCase();
  const budget = budgetRates.map(rate => ({...rate, price:money(rate[key],currency)}));
  function enquire(label, rate, hours) {
    const intro = lang === 'de' ? 'Ich möchte folgende Leistung anfragen' : 'I would like to enquire about';
    onChoose(`${intro}: ${label} — ${money(rate[key], currency)}${hours ? ' / '+hours : ' / '+(lang==='de'?'Stunde':'hour')}.\n${lang === 'de' ? 'Meine Aufgaben' : 'My requirements'}: `);
  }
  return <div className="dev-page">
    <section className="dev-hero"><div className="container dev-hero-inner">
      <a href={'/' + lang + '/'} className="text-link dev-back">← {lang === 'de' ? 'Zur Startseite' : 'Back to home'}</a>
      <div className="eyebrow">{t.eyebrow}</div><h1>{t.heading}</h1>
      <p className="dev-lead">{t.lead}</p><p className="dev-detail">{t.detail}</p>
      <div className="dev-hero-actions"><a href="#senior-rates" className="button">{t.seePlans}<ArrowRight size={18}/></a></div>
      <div className="dev-highlights">{t.highlights.map(item => <span key={item}><Check size={16}/>{item}</span>)}</div>
    </div></section>
    <div className="container dev-currency-bar"><span>{t.currencyLabel}</span><div className="dev-currency-switch" role="group" aria-label={t.currencyLabel}>
      {['CHF','USD'].map(code => <button type="button" key={code} aria-pressed={currency === code} className={currency === code ? 'active' : ''} onClick={() => setCurrency(code)}>{code}</button>)}
    </div></div>
    <section className="container dev-senior-section" id="senior-rates">
      <div className="eyebrow">{t.seniorEyebrow}</div><div className="dev-section-intro"><h2>{t.seniorTitle}</h2><p>{t.seniorIntro}</p></div>
      <div className="dev-senior-grid">{engineeringRates.map(rate => <article className="dev-senior-card" key={rate.id}>
        <div><h3>{rate[lang][0]}</h3><p>{rate[lang][1]}</p></div>
        <div className="dev-senior-side"><strong>{money(rate[key],currency)}<small> / {lang === 'de' ? 'Std.' : 'hr'}</small></strong><button type="button" className="text-link" onClick={() => enquire(rate[lang][0],rate)}>{t.seniorAction}<ArrowRight size={15}/></button></div>
      </article>)}</div>
      <p className="dev-price-note">{t.seniorNote}</p>
    </section>
    <section className="dev-budget-band"><div className="container dev-plans-section" id="plans">
      <div className="eyebrow">{t.budgetEyebrow}</div><div className="dev-section-intro"><div><h2>{t.plansTitle}</h2><p className="dev-budget-lead">{t.budgetIntro}</p></div><p>{t.plansIntro}</p></div>
      <div className="dev-plan-grid">{t.plans.map((plan,index) => <article className={'dev-plan-card ' + (index === 1 ? 'dev-plan-featured' : '')} key={plan.id}>
        <div className="dev-plan-kicker">{plan.name}</div>
        <div className="dev-plan-price"><strong>{budget[index].price}</strong><span>{plan.unit}</span></div>
        <div className="dev-plan-subtitle">{plan.subtitle}</div><p className="dev-plan-description">{plan.description}</p>
        <ul>{plan.points.map(point => <li key={point}><Check size={16}/><span>{point}</span></li>)}</ul>
        <button className={index===1?'button':'button button-secondary'} onClick={() => enquire(plan.name,budget[index],budgetHours[plan.id])}>{plan.cta}<ArrowRight size={17}/></button>
      </article>)}</div>
      <div className="dev-month-extra">{lang === 'de' ? '100 Stunden pro Monat' : '100 hours per month'} <strong>{budget[3].price}</strong><button className="text-link" type="button" onClick={() => enquire(lang === 'de'?'Monatspaket 100 Stunden':'Monthly 100 hours',budget[3],'100h')}>{lang === 'de'?'Anfragen':'Enquire'}<ArrowRight size={15}/></button></div>
      <p className="dev-price-note">{t.conditions}</p>
    </div></section>
    <section className="dev-work-band"><div className="container dev-work-inner"><div className="eyebrow">{t.workEyebrow}</div><h2>{t.workTitle}</h2>
      <div className="dev-work-grid">{t.work.map(([title,detail],index)=>{const Icon=workIcons[index];return <article key={title}><span className="icon-circle"><Icon size={21}/></span><h3>{title}</h3><p>{detail}</p></article>;})}</div>
    </div></section>
    <section className="container dev-process"><div className="eyebrow">{t.processEyebrow}</div><h2>{t.processTitle}</h2>
      <ol>{t.steps.map(([title,detail],index)=><li key={title}><span className="dev-step-number">0{index+1}</span><h3>{title}</h3><p>{detail}</p></li>)}</ol>
      <div className="dev-note"><ShieldCheck size={24}/><div><h3>{t.caveatTitle}</h3><p>{t.caveat}</p></div></div>
    </section>
    <section className="container dev-bottom"><div className="cta"><div><h2>{t.endTitle}</h2><p>{t.endText}</p></div><button className="button" onClick={() => enquire(t.plans[0].name,budget[0],budgetHours.hour)}>{t.endCta}<ArrowRight size={18}/></button></div></section>
  </div>;
}
