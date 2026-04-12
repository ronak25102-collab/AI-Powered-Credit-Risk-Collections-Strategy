import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import AnimatedCounter from "../components/AnimatedCounter";
import ParticleBackground from "../components/ParticleBackground";
import TypingEffect from "../components/TypingEffect";

const features = [
  {
    icon: "⟡",
    title: "Real-Time Risk Scoring",
    description:
      "Multi-model ensemble with calibrated probability, business-risk overrides, and severity-aware categorisation — scoring thousands of borrowers in seconds.",
  },
  {
    icon: "◉",
    title: "Smart Collections Workflow",
    description:
      "Auto-orchestration engine that assigns accounts, schedules follow-ups, escalates severe profiles, and balances agent workload by policy rules.",
  },
  {
    icon: "◎",
    title: "Predictive Analytics Studio",
    description:
      "What-if scenario simulation with explainable driver impacts, human-readable rationale, and collections strategy recommendations per borrower.",
  },
  {
    icon: "▦",
    title: "Model Governance & Monitoring",
    description:
      "Drift detection, override-rate tracking, candidate model comparison, version history, and role-based promotion — all from a single pane of glass.",
  },
];

const steps = [
  {
    number: "01",
    title: "Ingest & Normalise",
    description:
      "Upload CSV/XLSX data — the pipeline auto-maps columns, derives missing ratios, imputes gaps, and validates schema integrity.",
  },
  {
    number: "02",
    title: "Score & Classify",
    description:
      "Train Logistic Regression, Random Forest, and Gradient Boosting candidates. The best model is auto-selected and calibrated with business logic.",
  },
  {
    number: "03",
    title: "Act & Monitor",
    description:
      "Operationalise collections via queue management, auto-assignment, SLA scheduling, and continuous model-health monitoring with drift alerts.",
  },
];

const techStack = [
  "FastAPI",
  "React 18",
  "scikit-learn",
  "Chart.js",
  "Tailwind CSS",
  "Pandas",
  "Vite",
  "Pydantic v2",
];

export default function LandingPage() {
  const observerRef = useRef(null);

  useEffect(() => {
    const targets = document.querySelectorAll(".landing-reveal");
    if (!targets.length) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("landing-visible");
            observerRef.current?.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );

    targets.forEach((el) => observerRef.current.observe(el));

    return () => observerRef.current?.disconnect();
  }, []);

  return (
    <div className="landing-page">
      {/* ─── Hero ─────────────────────────────────────────── */}
      <section className="landing-hero">
        <ParticleBackground />
        <div className="landing-hero-glow" aria-hidden="true" />
        <div className="landing-hero-glow-2" aria-hidden="true" />

        <div className="landing-hero-content">
          <span className="landing-eyebrow">Enterprise-Grade Risk Analytics</span>
          <h1 className="landing-headline display-font">
            AI-Powered Credit Risk
            <br />
            <span className="landing-headline-accent">&amp; Collections Strategy</span>
          </h1>
          <p className="landing-subhead">
            <TypingEffect
              text="End-to-end delinquency prediction, borrower scoring, and operations-ready collections workflow — powered by machine learning and explainable AI."
              speed={22}
            />
          </p>

          <div className="landing-hero-actions">
            <Link to="/dashboard" className="landing-cta-primary">
              Enter Dashboard
              <span className="landing-cta-arrow" aria-hidden="true">→</span>
            </Link>
            <Link to="/prediction" className="landing-cta-secondary">
              Try Prediction Studio
            </Link>
          </div>

          <div className="landing-hero-badges">
            <span className="landing-stat-chip">
              <AnimatedCounter end={3} suffix=" ML Models" />
            </span>
            <span className="landing-stat-chip">
              <AnimatedCounter end={95} suffix="% Accuracy" />
            </span>
            <span className="landing-stat-chip">
              <AnimatedCounter end={5000} suffix="+" prefix="" /> Borrowers
            </span>
            <span className="landing-stat-chip">
              <AnimatedCounter end={100} suffix="% Explainable" />
            </span>
          </div>
        </div>
      </section>

      {/* ─── Features ─────────────────────────────────────── */}
      <section className="landing-section landing-reveal">
        <div className="landing-section-inner">
          <p className="landing-section-eyebrow">Core Capabilities</p>
          <h2 className="landing-section-title display-font">
            Everything You Need to Manage Credit Risk
          </h2>

          <div className="landing-features-grid">
            {features.map((f, i) => (
              <article
                key={f.title}
                className="landing-feature-card glass-card"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <span className="landing-feature-icon">{f.icon}</span>
                <h3 className="landing-feature-title">{f.title}</h3>
                <p className="landing-feature-desc">{f.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ─── How It Works ─────────────────────────────────── */}
      <section className="landing-section landing-section-dark landing-reveal">
        <div className="landing-section-inner">
          <p className="landing-section-eyebrow landing-section-eyebrow-light">
            Workflow
          </p>
          <h2 className="landing-section-title landing-section-title-light display-font">
            How It Works
          </h2>

          <div className="landing-steps-grid">
            {steps.map((s) => (
              <div key={s.number} className="landing-step-card">
                <span className="landing-step-number display-font">{s.number}</span>
                <h3 className="landing-step-title">{s.title}</h3>
                <p className="landing-step-desc">{s.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Tech Stack ───────────────────────────────────── */}
      <section className="landing-section landing-reveal">
        <div className="landing-section-inner">
          <p className="landing-section-eyebrow">Built With</p>
          <h2 className="landing-section-title display-font">
            Modern, Production-Ready Stack
          </h2>

          <div className="landing-tech-strip">
            {techStack.map((t) => (
              <span key={t} className="landing-tech-chip">{t}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA Banner ───────────────────────────────────── */}
      <section className="landing-cta-banner landing-reveal">
        <div className="landing-section-inner landing-cta-banner-inner">
          <h2 className="landing-cta-banner-title display-font">
            Ready to Take Control of Your Portfolio?
          </h2>
          <p className="landing-cta-banner-sub">
            Explore the dashboard, run predictions, and manage collections — all in one platform.
          </p>
          <Link to="/dashboard" className="landing-cta-primary">
            Get Started
            <span className="landing-cta-arrow" aria-hidden="true">→</span>
          </Link>
        </div>
      </section>

      {/* ─── Footer ───────────────────────────────────────── */}
      <footer className="landing-footer">
        <div className="landing-section-inner landing-footer-inner">
          <p className="landing-footer-brand display-font">
            <span className="landing-footer-badge">✦</span>
            Credit Risk Analytics
          </p>

          <nav className="landing-footer-links" aria-label="Footer">
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/risk-queue">Risk Queue</Link>
            <Link to="/prediction">Prediction Studio</Link>
            <Link to="/insights">Model Insights</Link>
          </nav>

          <p className="landing-footer-copy">
            © {new Date().getFullYear()} AI-Powered Credit Risk &amp; Collections Strategy. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
