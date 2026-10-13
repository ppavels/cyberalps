import React from 'react';
import { ArrowRight, Check, Code2, Wrench, Layers3, ShieldCheck } from 'lucide-react';
import { developmentCopy } from './developmentCopy.js';

const workIcons = [Code2, Wrench, Layers3];

export default function DevelopmentPage({ lang, onChoose }) {
  const t = developmentCopy[lang];
  return <div className="dev-page">
    <section className="dev-hero">
      <div className="container dev-hero-inner">
        <a href={'/' + lang + '/'} className="text-link dev-back">← {lang === 'de' ? 'Zur Startseite' : 'Back to home'}</a>
        <div className="eyebrow">{t.eyebrow}</div>
        <h1>{t.heading}</h1>
        <p className="dev-lead">{t.lead}</p>
        <p className="dev-detail">{t.detail}</p>
        <div className="dev-hero-actions"><a href="#plans" className="button">{t.seePlans}<ArrowRight size={18}/></a><span className="dev-from">{lang === 'de' ? 'Ab' : 'From'} <strong>$20</strong> / {lang === 'de' ? 'Std.' : 'hour'}</span></div>
        <div className="dev-highlights">{t.highlights.map(item => <span key={item}><Check size={16}/>{item}</span>)}</div>
      </div>
    </section>
    <section className="container dev-plans-section" id="plans">
      <div className="eyebrow">{t.plansEyebrow}</div>
      <div className="dev-section-intro"><h2>{t.plansTitle}</h2><p>{t.plansIntro}</p></div>
      <div className="dev-plan-grid">{t.plans.map((plan, index) => <article className={'dev-plan-card ' + (index === 1 ? 'dev-plan-featured' : '')} key={plan.id}>
        <div className="dev-plan-kicker">{plan.name}</div>
        <div className="dev-plan-price"><strong>{plan.price}</strong><span>{plan.unit}</span></div>
        <div className="dev-plan-subtitle">{plan.subtitle}</div>
        <p className="dev-plan-description">{plan.description}</p>
        <ul>{plan.points.map(point => <li key={point}><Check size={16}/><span>{point}</span></li>)}</ul>
        <button className={index === 1 ? 'button' : 'button button-secondary'} onClick={() => onChoose(plan.enquiry)}>{plan.cta}<ArrowRight size={17}/></button>
      </article>)}</div>
      <p className="dev-price-note">{t.conditions}</p>
    </section>
    <section className="dev-work-band"><div className="container dev-work-inner">
      <div className="eyebrow">{t.workEyebrow}</div><h2>{t.workTitle}</h2>
      <div className="dev-work-grid">{t.work.map(([title, detail], index) => {const Icon=workIcons[index];return <article key={title}><span className="icon-circle"><Icon size={21}/></span><h3>{title}</h3><p>{detail}</p></article>;})}</div>
    </div></section>
    <section className="container dev-process">
      <div className="eyebrow">{t.processEyebrow}</div><h2>{t.processTitle}</h2>
      <ol>{t.steps.map(([title, detail], index) => <li key={title}><span className="dev-step-number">0{index + 1}</span><h3>{title}</h3><p>{detail}</p></li>)}</ol>
      <div className="dev-note"><ShieldCheck size={24}/><div><h3>{t.caveatTitle}</h3><p>{t.caveat}</p></div></div>
    </section>
    <section className="container dev-bottom"><div className="cta"><div><h2>{t.endTitle}</h2><p>{t.endText}</p></div><button className="button" onClick={() => onChoose(t.plans[0].enquiry)}>{t.endCta}<ArrowRight size={18}/></button></div></section>
  </div>;
}
