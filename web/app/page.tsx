import Link from "next/link";
import { Flame, Map as MapIcon, Wallet, Sparkles, ShieldCheck, GitBranch } from "lucide-react";

import { LandingNavbar } from "@/components/LandingNavbar";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <LandingNavbar />

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-panel-border bg-white">
        <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-6 py-12 md:grid-cols-2 md:py-16">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-panel-border bg-brand-light px-3 py-1 text-xs font-semibold text-brand-dark">
              <Flame size={14} /> Extreme-heat grid resilience
            </span>
            <h1 className="mt-5 text-4xl font-bold leading-tight text-foreground md:text-5xl">
              Know which zones of your grid will fail before the heat does.
            </h1>
            <p className="mt-5 text-lg text-muted">
              GridPulse AI combines heat, demand, infrastructure, outage history, and community
              vulnerability into one deterministic risk score per zone — then recommends a
              budget-optimal resilience plan, explained in plain language.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                href="/dashboard/overview"
                className="rounded-lg bg-brand px-6 py-3 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90"
              >
                Launch Dashboard
              </Link>
              <a
                href="#how-it-works"
                className="rounded-lg border border-panel-border bg-white px-6 py-3 text-sm font-semibold text-foreground hover:bg-gray-50"
              >
                See how it works
              </a>
            </div>
          </div>

          <div className="panel p-6">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm font-semibold text-foreground">Zone risk snapshot</p>
              <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-600">
                Live pilot
              </span>
            </div>
            <div className="space-y-2">
              {[
                { zone: "Z00014", risk: 78, level: "high" },
                { zone: "Z00007", risk: 61, level: "high" },
                { zone: "Z00021", risk: 48, level: "mid" },
                { zone: "Z00003", risk: 22, level: "low" },
              ].map((z) => (
                <div key={z.zone} className="flex items-center gap-3">
                  <span className="w-16 text-sm text-muted">{z.zone}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${z.risk}%`,
                        backgroundColor:
                          z.level === "high" ? "#dc2626" : z.level === "mid" ? "#f59e0b" : "#16a34a",
                      }}
                    />
                  </div>
                  <span className="w-8 text-right text-sm font-semibold text-foreground">{z.risk}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-b border-panel-border bg-background">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-2xl font-semibold text-foreground md:text-3xl">How it works</h2>
          <p className="mt-2 max-w-2xl text-muted">
            An agentic LangGraph pipeline pulls in five independent signals, computes a
            deterministic risk score, and hands off to a constrained-budget optimizer — every
            step traceable and explainable.
          </p>

          <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
            <StepCard
              step="01"
              icon={<Flame size={20} />}
              title="Score every zone"
              description="Heat, demand stress, transmission infrastructure, outage history, and vulnerability are weighted into one grid-heat risk score per zone."
            />
            <StepCard
              step="02"
              icon={<Wallet size={20} />}
              title="Optimize the response"
              description="An exact 0/1 knapsack optimizer picks the combination of actions — crew deployment, battery dispatch, demand response — that maximizes risk reduction under your budget."
            />
            <StepCard
              step="03"
              icon={<Sparkles size={20} />}
              title="Explain the decision"
              description="A guardrailed LLM layer explains why a zone was flagged or why a plan was chosen — grounded only in real numbers, never inventing data or claiming credit for the math."
            />
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-b border-panel-border bg-white">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-2xl font-semibold text-foreground md:text-3xl">Built for operators, not just dashboards</h2>

          <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <FeatureCard
              icon={<MapIcon size={20} />}
              title="Interactive risk map"
              description="Every grid cell colored by live risk score, overlaid with real transmission infrastructure."
            />
            <FeatureCard
              icon={<Wallet size={20} />}
              title="Budget-constrained planning"
              description="Slide the budget and watch the optimizer re-solve in real time — always the mathematically optimal allocation."
            />
            <FeatureCard
              icon={<ShieldCheck size={20} />}
              title="Guardrailed AI explanations"
              description="Every LLM explanation is checked for self-attribution and numeric grounding before it reaches you — no hallucinated figures."
            />
            <FeatureCard
              icon={<GitBranch size={20} />}
              title="Agentic, traceable pipeline"
              description="Built on LangGraph with optional LangSmith tracing — inspect every node's inputs, outputs, and latency."
            />
            <FeatureCard
              icon={<Flame size={20} />}
              title="Real public data"
              description="Heat, EPA EJScreen vulnerability, transmission lines, and EAGLE-I outage history — not synthetic placeholders."
            />
            <FeatureCard
              icon={<Sparkles size={20} />}
              title="Plain-language answers"
              description="Ask 'why' about any flagged zone or recommended plan and get a grounded, jargon-free explanation."
            />
          </div>
        </div>
      </section>

      {/* Pilot / CTA */}
      <section id="pilot" className="bg-background">
        <div className="mx-auto max-w-6xl px-6 py-20 text-center">
          <h2 className="text-2xl font-semibold text-foreground md:text-3xl">
            Currently piloting in Harris County (Houston), TX
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-muted">
            GridPulse AI&apos;s Texas deployment models extreme-heat grid risk across Harris County
            using real ERCOT demand data (EIA-930), transmission infrastructure, EAGLE-I outage
            history, and EPA EJScreen vulnerability scores.
          </p>
          <Link
            href="/dashboard/overview"
            className="mt-8 inline-block rounded-lg bg-brand px-6 py-3 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90"
          >
            Launch Dashboard
          </Link>
        </div>
      </section>

      <footer className="border-t border-panel-border bg-white">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 text-sm text-muted md:flex-row">
          <span>© {new Date().getFullYear()} GridPulse AI. Demonstration project, not an operational deployment.</span>
          <Link href="/dashboard/overview" className="font-medium text-brand hover:underline">
            Launch Dashboard →
          </Link>
        </div>
      </footer>
    </div>
  );
}

function StepCard({
  step,
  icon,
  title,
  description,
}: {
  step: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="panel p-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-light text-brand">
          {icon}
        </div>
        <span className="text-xs font-mono text-muted">{step}</span>
      </div>
      <h3 className="mt-4 font-semibold text-foreground">{title}</h3>
      <p className="mt-2 text-sm text-muted">{description}</p>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-panel-border p-5 transition-shadow hover:shadow-sm">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-light text-brand">
        {icon}
      </div>
      <h3 className="mt-3 text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1.5 text-sm text-muted">{description}</p>
    </div>
  );
}
