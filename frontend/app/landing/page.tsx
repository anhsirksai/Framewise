import type { Metadata } from "next";
import Link from "next/link";
import styles from "./landing.module.css";

export const metadata: Metadata = {
  title: "Framewise — every video, every receipt, remembered forever",
  description:
    "Framewise turns unstructured video and documents into a permanent, searchable evidence graph. Retrieve a bill from 20 years ago with one search.",
};

export default function LandingPage() {
  return (
    <div className={styles.page}>
      {/* ---- Nav ---- */}
      <nav className={styles.nav}>
        <div className={styles.navInner}>
          <Link href="/landing" className={styles.wordmark}>
            Framewise
          </Link>
          <Link href="/" className={styles.btnPrimary}>
            Try it out
          </Link>
        </div>
      </nav>

      {/* ---- Hero ---- */}
      <header className={styles.hero}>
        <div className={styles.container}>
          <span className={styles.kicker}>Video Intelligence Platform</span>
          <h1 className={styles.heroTitle}>
            Every video, every receipt —{" "}
            <em className={styles.accent}>remembered forever.</em>
          </h1>
          <p className={styles.heroSub}>
            Framewise turns unstructured video and documents into a permanent,
            searchable evidence graph. Ask a question in plain language and get
            the exact moment, document, or pattern back — with the proof
            attached.
          </p>
          <div className={styles.heroActions}>
            <Link href="/" className={styles.btnClay}>
              Try it out
            </Link>
            <a href="#use-cases" className={styles.btnGhost}>
              See use cases
            </a>
          </div>
          <div className={styles.pills}>
            <span className={styles.pillHero}>Claude</span>
            <span className={styles.pill}>TwelveLabs</span>
            <span className={styles.pill}>Strands</span>
            <span className={styles.pill}>Neo4j / AuraDB</span>
          </div>
        </div>
      </header>

      {/* ---- Problem ---- */}
      <section className={styles.section}>
        <div className={styles.container}>
          <span className={styles.kicker}>The problem</span>
          <h2 className={styles.sectionTitle}>
            Rich media is full of answers. Its intelligence is{" "}
            <em className={styles.accent}>trapped in a timeline.</em>
          </h2>
          <p className={styles.sectionSub}>
            Organizations — and households — have more recorded evidence than
            anyone can watch, compare, or find again.
          </p>
          <div className={styles.grid}>
            <div className={styles.card}>
              <h3>Creative knowledge disappears</h3>
              <p>
                Teams reinvent hooks, pacing, CTAs, and brand decisions already
                present in prior campaigns.
              </p>
            </div>
            <div className={styles.card}>
              <h3>Events are hard to connect</h3>
              <p>
                A single incident may span multiple cameras, clips, people,
                objects, and locations.
              </p>
            </div>
            <div className={styles.card}>
              <h3>Search is not enough</h3>
              <p>
                Users need relationships, timelines, patterns, and the exact
                evidence behind an answer.
              </p>
            </div>
            <div className={styles.card}>
              <h3>Generative answers need trust</h3>
              <p>
                Every recommendation should be traceable to a source document
                and timestamp.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- How it works ---- */}
      <section className={styles.section}>
        <div className={styles.container}>
          <span className={styles.kicker}>How it works</span>
          <h2 className={styles.sectionTitle}>
            Two paths. <em className={styles.accent}>One evidence graph.</em>
          </h2>
          <p className={styles.sectionSub}>
            TwelveLabs watches and indexes your media, Claude structures it
            into entities, topics, and time-coded segments, and everything
            persists in a Neo4j graph with full provenance. A Strands agent
            answers your questions with evidence — not just answers.
          </p>
          <div className={styles.pipeline}>
            <div className={styles.pipeBox}>
              <div>
                <strong>Capture</strong>
                <small>videos, bills, receipts, footage</small>
              </div>
            </div>
            <div className={styles.pipeArrow}>→</div>
            <div className={styles.pipeBox}>
              <div>
                <strong>Understand</strong>
                <small>index, structure, embed, persist</small>
              </div>
            </div>
            <div className={styles.pipeArrow}>→</div>
            <div className={styles.pipeBox}>
              <div>
                <strong>Retrieve</strong>
                <small>ask in plain language, get evidence</small>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Product layers ---- */}
      <section className={styles.section}>
        <div className={styles.container}>
          <span className={styles.kicker}>The platform</span>
          <h2 className={styles.sectionTitle}>
            Three product layers.{" "}
            <em className={styles.accent}>One compounding foundation.</em>
          </h2>
          <div className={styles.layer}>
            <div className={styles.layerNum}>1</div>
            <div>
              <h3>Understand media</h3>
              <p>
                Analyze segments, people, objects, actions, speech, text,
                style, topics, and relationships.
              </p>
            </div>
            <div className={styles.layerOutcome}>
              <strong>Foundation:</strong> searchable, time-coded intelligence.
            </div>
          </div>
          <div className={styles.layer}>
            <div className={styles.layerNum}>2</div>
            <div>
              <h3>Act on the intelligence</h3>
              <p>
                Generate marketing briefs and templates, answer questions,
                retrieve decades-old receipts, and validate brand rules.
              </p>
            </div>
            <div className={styles.layerOutcome}>
              <strong>Workflow:</strong> turn past records into reusable
              decisions and claims.
            </div>
          </div>
          <div className={styles.layer}>
            <div className={styles.layerNum}>3</div>
            <div>
              <h3>Discover patterns across domains</h3>
              <p>
                Reuse the same graph and agent primitives for security
                incidents, investigations, and operational vigilance.
              </p>
            </div>
            <div className={styles.layerOutcome}>
              <strong>Platform:</strong> one intelligence layer, multiple
              vertical products.
            </div>
          </div>
        </div>
      </section>

      {/* ---- Use cases ---- */}
      <section className={styles.section} id="use-cases">
        <div className={styles.container}>
          <span className={styles.kicker}>Use cases</span>
          <h2 className={styles.sectionTitle}>
            One memory. <em className={styles.accent}>Many products.</em>
          </h2>

          {/* Featured: HSA */}
          <div className={styles.featured}>
            <span className={styles.badge}>Featured use case</span>
            <h3>
              HSA Receipt Recall — fetch a bill from{" "}
              <em className={styles.accent}>20 years ago</em> with one search.
            </h3>
            <blockquote>
              HSA reimbursements have no deadline. The receipt that proves your
              claim shouldn&apos;t have one either.
            </blockquote>
            <p>
              The IRS lets you claim an HSA medical expense years — even
              decades — after you paid it, tax-free, as long as you can produce
              the bill. Almost no one keeps a searchable record that long, so
              the savings are left on the table. With Framewise, every medical
              bill and receipt is ingested, understood, and stored in the
              evidence graph with full provenance. Ask{" "}
              <em>&ldquo;fetch the bill for my knee MRI from 2005&rdquo;</em>{" "}
              and get the exact document back — ready to claim.
            </p>
          </div>

          {/* Other use cases */}
          <div className={styles.grid3}>
            <div className={styles.card}>
              <h3>Marketing Video Studio</h3>
              <p>
                Learn a company&apos;s style DNA — hooks, pacing, tone, CTA —
                from past campaigns, then draft new storyboards in that voice.
                Every generated scene cites the source segments that influenced
                it.
              </p>
            </div>
            <div className={styles.card}>
              <h3>Security Vigilance</h3>
              <p>
                Stitch clips from many cameras into one time-ordered incident
                story. Find recurring patterns — distraction, vehicle exit,
                location, time of day — across cases, with linked evidence.
              </p>
            </div>
            <div className={styles.card}>
              <h3>Household &amp; personal records</h3>
              <p>
                Warranties, home repairs, insurance claims, tax documents — the
                same pipeline that recalls a 20-year-old HSA bill keeps every
                household record one question away.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Final CTA ---- */}
      <section className={styles.cta}>
        <div className={styles.container}>
          <h2 className={styles.ctaTitle}>
            Turn every video into{" "}
            <em className={styles.accent}>reusable intelligence.</em>
          </h2>
          <p className={styles.ctaSub}>
            Chat with your evidence graph, explore the visualization, and see
            provenance-backed answers in action.
          </p>
          <div className={styles.ctaActions}>
            <Link href="/" className={styles.btnClay}>
              Try it out
            </Link>
          </div>
        </div>
      </section>

      <div className={styles.container}>
        <footer className={styles.footer}>
          <span>Framewise — Video Intelligence Platform</span>
          <span>TwelveLabs · Claude · Strands · Neo4j</span>
        </footer>
      </div>
    </div>
  );
}
