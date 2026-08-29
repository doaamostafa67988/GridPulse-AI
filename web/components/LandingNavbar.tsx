import Link from "next/link";

export function LandingNavbar() {
  return (
    <header className="sticky top-0 z-30 border-b border-panel-border bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-icon.png" alt="GridPulse AI" className="h-8 w-8 rounded-lg object-cover" />
          <span className="text-sm font-semibold text-foreground">GridPulse AI</span>
        </Link>

        <nav className="hidden items-center gap-8 text-sm font-medium text-muted md:flex">
          <a href="#how-it-works" className="hover:text-foreground">
            How it works
          </a>
          <a href="#features" className="hover:text-foreground">
            Features
          </a>
          <a href="#pilot" className="hover:text-foreground">
            Pilot data
          </a>
        </nav>

        <Link
          href="/dashboard/overview"
          className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
        >
          Launch Dashboard
        </Link>
      </div>
    </header>
  );
}
